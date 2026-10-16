"""Fast edit: one Claude call writes the plan, the style's scripts do the rest.

A full agent run spends most of its tokens running scripts, reading docs and
re-reading its own growing context (17-86 turns, $1-3 a reel). The creative
decisions of a style engine are a handful of plan files (caption phrases,
keywords, beats, style, sounds). Styles that ship a ``fast.json`` manifest
are edited here instead: the worker runs setup, build and render itself and
asks Claude once for the plan (plus a cheap repair call if a script rejects
it). The transcript is the user's reviewed one and is never altered.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from .agent_tools import describe_resource, load_project_media
from .project_bootstrap import bootstrap_project

Emit = Callable[[dict[str, Any]], Awaitable[None]]
MANIFEST = "fast.json"
MAX_REPAIRS = 2


# Styles without their own engine: one call writes the whole composition.
GENERIC_DIR = Path(__file__).resolve().parent / "fast_generic"
HELPER_SKILLS = {"media-use"}
MAX_DOC_CHARS = 60_000


@dataclass
class FastManifest:
    skill_dir: Path
    data: dict[str, Any]
    # Where "@style/..." spec entries resolve: the style itself for the generic engine.
    style_dir: Path | None = None

    @classmethod
    def load(cls, skill_dir: Path) -> FastManifest | None:
        path = skill_dir / MANIFEST
        if not path.is_file():
            return None
        return cls(skill_dir, json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def for_style(cls, style_dir: Path) -> FastManifest | None:
        """The style's own engine, else the generic one for any real style."""

        if own := cls.load(style_dir):
            return own
        if not is_style(style_dir):
            return None
        generic = cls.load(GENERIC_DIR)
        return cls(generic.skill_dir, generic.data, style_dir) if generic else None

    @property
    def generic(self) -> bool:
        return self.style_dir is not None

    @property
    def plan_files(self) -> dict[str, dict[str, str]]:
        return self.data["plan_files"]

    def spec(self) -> str:
        parts = []
        for entry in self.data.get("spec", ["SKILL.md"]):
            # "scripts/x.py:doc" includes only the script's docstring (its plan schema).
            relative, _, part = entry.partition(":")
            if relative.startswith("@style/") and self.style_dir is not None:
                path = self.style_dir / relative.removeprefix("@style/")
            else:
                path = self.skill_dir / relative
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if part == "doc":
                text = ast.get_docstring(ast.parse(text)) or ""
            text = text[:MAX_DOC_CHARS]
            parts.append(f'<doc path="{relative}">\n{text}\n</doc>')
        return "\n\n".join(parts)


def is_style(skill_dir: Path) -> bool:
    name = skill_dir.name
    return (skill_dir / "SKILL.md").is_file() and not name.startswith("hyperframes") and name not in HELPER_SKILLS


def fast_engine(skill_dir: Path) -> str | None:
    """"style" when the style ships its own fast.json, "generic" for any other style."""

    if (skill_dir / MANIFEST).is_file():
        return "style"
    return "generic" if is_style(skill_dir) else None


def skill_supports_fast(project: Path, skill: str | None) -> bool:
    """Every style edits fast: through its own fast.json or the generic engine."""

    if not skill:
        return False
    style = project / ".claude" / "skills" / str(skill)
    if not style.is_dir():
        # Not installed in this project yet: look where bootstrap copies from.
        from .project_bootstrap import SKILLS_ROOT

        style = next((root / str(skill) for root in (SKILLS_ROOT / "library", SKILLS_ROOT / "builtin", project.parent / "_skills") if (root / str(skill)).is_dir()), style)
    return FastManifest.for_style(style) is not None


# --- running the engine's scripts ---------------------------------------------------------------

def _resolve(argv: list[str], *, skill_dir: Path, clip: Path, folder: Path) -> list[str]:
    subject = {}
    subject_file = folder / "edit" / "subject.json"
    if subject_file.is_file():
        subject = json.loads(subject_file.read_text(encoding="utf-8"))
    resolved = []
    for part in argv:
        part = part.replace("{skill}", str(skill_dir)).replace("{clip}", str(clip))
        if part.startswith("{subject.") and part.endswith("}"):
            part = str(subject.get(part[9:-1], ""))
        resolved.append(part)
    program = resolved[0]
    if program in {"python", "python3"}:
        resolved[0] = sys.executable
    elif program in {"npx", "npm"}:
        resolved[0] = shutil.which(program) or program
    return resolved


def _run(argv: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return completed.returncode, (completed.stdout + "\n" + completed.stderr).strip()


async def _step(emit: Emit, step: str, label: str, argv: list[str], cwd: Path, timeout: int = 3600) -> str:
    await emit({"type": "fast.step", "step": step, "label": label, "status": "running"})
    code, output = await asyncio.to_thread(_run, argv, cwd, timeout)
    if code != 0:
        await emit({"type": "fast.step", "step": step, "label": label, "status": "failed", "detail": output[-1500:]})
        raise RuntimeError(f"{label} failed: {output[-1500:]}")
    await emit({"type": "fast.step", "step": step, "label": label, "status": "done"})
    return output


# --- the planning call ---------------------------------------------------------------------------

PLAN_SYSTEM = """You plan edits for the HyperFrames style engine `{skill}`. You do not run tools: you write the plan files the engine's scripts read, and the studio runs setup, build and render.

Rules:
- The transcript is final; the user reviewed it. Never change, add, drop or reorder words; you only group them. Time every beat field (`t`, `s`, `hotAt`, `lineTimes`, `items[].t`, `hl[].t` ...) from the word onsets given.
- Every scene switch, card, graphic and sound starts on a word onset and illustrates what is said at that moment; numbers, names, tools and lists get their matching visual; pacing follows the speaker's energy.
- Use only the beat types, fields and style keys the engine documentation defines; respect its layout rules and safe zones.
- Follow the user's request; when it does not say, use the engine's defaults.

Answer with ONE JSON object and nothing else, with exactly these keys:
{files}
- "notes": one or two sentences telling the user what you did.

Engine documentation:
{spec}
"""


def _files_doc(manifest: FastManifest) -> str:
    lines = []
    for key, spec in manifest.plan_files.items():
        shape = {"lines": "a list of strings, one per line", "text": "a string holding the whole file"}.get(spec.get("format", ""), "JSON")
        lines.append(f'- "{key}": {shape} for `{spec["path"]}`: {spec["doc"]}')
    return "\n".join(lines)


def _transcript_lines(words: list[dict[str, Any]]) -> str:
    return "\n".join(f"{index}\t{word['s']:.2f}-{word['e']:.2f}\t{word['t']}" for index, word in enumerate(words))


def _parse_plan(text: str, manifest: FastManifest) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the plan is not JSON")
    plan = json.loads(text[start : end + 1])
    missing = [key for key in manifest.plan_files if key not in plan]
    if missing:
        raise ValueError(f"the plan is missing {', '.join(missing)}")
    return plan


async def _ask(system: str, prompt: str) -> tuple[str, float]:
    from claude_agent_sdk import ClaudeAgentOptions, query

    options = ClaudeAgentOptions(
        model=os.getenv("FAST_EDIT_MODEL") or os.getenv("AGENT_MODEL", "claude-opus-5-5"),
        system_prompt=system,
        setting_sources=[],
        tools=[],
        allowed_tools=[],
        max_turns=1,
        effort=os.getenv("FAST_EDIT_EFFORT", "medium"),
        # The system prompt is the style's docs, identical for every video in
        # that style: an hour-long cache makes repeat plans read it at 10%.
        env={"ENABLE_PROMPT_CACHING_1H": "1"} if os.getenv("PROMPT_CACHE_1H", "1") != "0" else {},
    )
    answer, cost = "", 0.0
    async for message in query(prompt=prompt, options=options):
        if getattr(message, "total_cost_usd", None) is not None:
            cost = float(message.total_cost_usd)
        if getattr(message, "result", None):
            answer = str(message.result)
        if getattr(message, "is_error", False):
            raise RuntimeError(answer or "the planning call failed")
    return answer, cost


def _write_plan(folder: Path, manifest: FastManifest, plan: dict[str, Any], duration: float) -> None:
    for key, spec in manifest.plan_files.items():
        target = folder / spec["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        value = plan[key]
        if key == "sfx" and isinstance(value, dict):
            value.setdefault("duration", round(duration, 3))
        if spec.get("format") == "lines":
            text = "\n".join(str(line) for line in value) if isinstance(value, list) else str(value)
            target.write_text(text.strip() + "\n", encoding="utf-8")
        elif spec.get("format") == "text":
            target.write_text(str(value), encoding="utf-8")
        else:
            target.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_plan(folder: Path, manifest: FastManifest) -> dict[str, Any]:
    plan: dict[str, Any] = {}
    for key, spec in manifest.plan_files.items():
        path = folder / spec["path"]
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        plan[key] = text.splitlines() if spec.get("format") == "lines" else text if spec.get("format") == "text" else json.loads(text)
    return plan


# --- the run --------------------------------------------------------------------------------------

def _pick_clip(project: Path, asset_id: str | None, *, optional: bool = False) -> tuple[str | None, dict[str, Any]]:
    assets, _ = load_project_media(project)
    videos = {key: value for key, value in assets.items() if (value.get("probe") or {}).get("width") and value.get("role") != "resource"}
    if asset_id and asset_id in videos:
        return asset_id, videos[asset_id]
    if not videos:
        if optional:
            return None, {}
        raise FileNotFoundError("Upload a video clip first")
    newest = max(videos, key=lambda key: (project / "proxies" / key / "asset.json").stat().st_mtime)
    return newest, videos[newest]


def _attach_resources(project: Path, folder: Path, ids: list[str]) -> list[str]:
    """Copy the attached files into the composition; returns lines for the plan prompt."""

    assets, _ = load_project_media(project)
    lines = []
    for asset_id in ids:
        asset = assets.get(asset_id)
        source = Path(str((asset or {}).get("path", "")))
        if not asset or not source.is_file():
            continue
        target = folder / "assets" / "resources"
        target.mkdir(parents=True, exist_ok=True)
        name = str(asset.get("filename") or source.name).replace(" ", "-")
        shutil.copyfile(source, target / name)
        lines.append(f"- `assets/resources/{name}`: {describe_resource(asset)}")
    return lines


async def run_fast_edit(project: Path, *, run_id: str, skill: str, request: str, emit: Emit, asset_id: str | None = None, quick: bool = False, resources: list[str] | None = None) -> dict[str, Any]:
    """Run (or continue) a fast edit; returns usage and the rendered file."""

    bootstrap_project(project)
    skill_dir = project / ".claude" / "skills" / skill
    manifest = FastManifest.for_style(skill_dir)
    if manifest is None:
        raise ValueError(f"{skill} is not an editing style")
    engine_dir = manifest.skill_dir
    state_path = project / ".agent-context" / "fast" / f"{run_id}.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    # The generic engine also makes videos with no footage (product launches, explainers).
    clip_id, clip = _pick_clip(project, state.get("asset_id") or asset_id, optional=manifest.generic)
    words_file = project / "proxies" / str(clip_id) / "words.json"
    if clip_id and not words_file.is_file() and not manifest.generic:
        raise FileNotFoundError("This clip has no transcript yet; wait for it in Transcripts")
    folder = project / "compositions" / f"{skill}-{(clip_id or run_id)[:8]}"
    raw = Path(str(clip.get("path", "")))
    if clip_id and not raw.is_absolute():
        raw = project / "raw" / raw.name

    if not (folder / "index.html").is_file():
        await _step(emit, "init", "Creating the HyperFrames project", [shutil.which("npx") or "npx", "hyperframes", "init", str(folder.relative_to(project)), "--non-interactive", "--example=blank"], project, 600)
    ready = all((folder / path).exists() for path in manifest.data.get("ready_when", []))
    needs_cutout = not quick and not (folder / "assets" / "subject.webm").exists() and any("cutout" in " ".join(cmd) or "prep_subject" in " ".join(cmd) for cmd in manifest.data["setup"])
    if clip_id and (not ready or needs_cutout):
        steps = manifest.data.get("setup_quick") if quick and manifest.data.get("setup_quick") else manifest.data["setup"]
        for index, argv in enumerate(steps):
            label = "Preparing the footage" + ("" if quick else " and cutting out the speaker (a few minutes, runs on your machine)")
            await _step(emit, f"setup-{index}", label, _resolve(argv, skill_dir=engine_dir, clip=raw, folder=folder), folder)
    (folder / "edit").mkdir(parents=True, exist_ok=True)
    words: list[dict[str, Any]] = []
    if words_file.is_file():
        shutil.copyfile(words_file, folder / "edit" / "words.json")
        words = json.loads(words_file.read_text(encoding="utf-8"))
    duration = float((clip.get("probe") or {}).get("duration_ms") or 0) / 1000 or (words[-1]["e"] + 1 if words else 1)

    # Attached files stay available to every later turn of this edit.
    attached = list(dict.fromkeys([*state.get("resources", []), *(resources or [])]))
    resource_lines = _attach_resources(project, folder, attached)
    subject = (folder / "edit" / "subject.json").read_text(encoding="utf-8") if (folder / "edit" / "subject.json").is_file() else "{}"
    system = PLAN_SYSTEM.format(skill=skill, files=_files_doc(manifest), spec=manifest.spec())
    context = "No footage: build the whole video from the request." if not clip_id else f"Clip: {clip.get('filename')}, {duration:.1f}s, {(clip.get('probe') or {}).get('width')}x{(clip.get('probe') or {}).get('height')}\nedit/subject.json: {subject}\n\nTranscript (index, seconds, word):\n{_transcript_lines(words)}"
    if resource_lines:
        context += "\n\nFiles the user attached (paths relative to the composition). Use each where the request says, through the engine's fields for images, b-roll or sounds (image/screenshot/media cards, img fields, sfx cues by path):\n" + "\n".join(resource_lines)
    # The generic engine's plan is the composition itself: start from the file, which
    # keeps any hand edits made in Studio since the last turn.
    current = (_read_plan(folder, manifest) or None) if manifest.generic and state.get("plan") else state.get("plan")
    if current:
        prompt = f"{context}\n\nCurrent plan:\n{json.dumps(current, ensure_ascii=False)}\n\nChange request from the user:\n{request}\n\nReturn the complete updated plan."
        await emit({"type": "fast.step", "step": "plan", "label": "Revising the edit plan", "status": "running"})
    else:
        prompt = f"{context}\n\nThe user's request:\n{request or 'Edit this clip in the style.'}"
        await emit({"type": "fast.step", "step": "plan", "label": "Planning the edit (one Claude call)", "status": "running"})

    total_cost = float(state.get("cost", 0.0))
    answer, cost = await _ask(system, prompt)
    total_cost += cost
    plan = _parse_plan(answer, manifest)
    await emit({"type": "fast.step", "step": "plan", "label": "Edit plan ready", "status": "done", "cost": cost})
    await emit({"type": "fast.plan", "notes": plan.get("notes", ""), "beats": len(plan.get("beats") or [])})

    for attempt in range(MAX_REPAIRS + 1):
        _write_plan(folder, manifest, plan, duration)
        try:
            for index, argv in enumerate(manifest.data["build"]):
                await _step(emit, f"build-{index}", f"Building: {Path(argv[1]).name if len(argv) > 1 else argv[0]}", _resolve(argv, skill_dir=engine_dir, clip=raw, folder=folder), folder, 900)
            break
        except RuntimeError as exc:
            if attempt == MAX_REPAIRS:
                raise
            await emit({"type": "fast.step", "step": "repair", "label": "Fixing the plan after a build error", "status": "running"})
            answer, cost = await _ask(system, f"{prompt}\n\nYour plan:\n{json.dumps(plan, ensure_ascii=False)}\n\nThe build failed:\n{exc}\n\nReturn the complete corrected plan.")
            total_cost += cost
            plan = _parse_plan(answer, manifest)

    turn = int(state.get("turns", 0)) + 1
    output = project / "renders" / f"{folder.name}-{run_id[:8]}-v{turn}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    await _step(emit, "render", "Rendering the video", [shutil.which("npx") or "npx", "hyperframes", "render", "-q", "delivery", "-o", str(output)], folder, 3600)

    state.update(resources=attached, asset_id=clip_id, composition=f"compositions/{folder.name}", skill=skill, plan=plan, cost=total_cost, turns=turn)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return {"output": str(output), "composition": state["composition"], "usage": {"total_cost_usd": round(total_cost, 4), "mode": "fast", "turns": turn}}
