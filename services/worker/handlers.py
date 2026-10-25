"""Job handlers shared by local and Postgres worker loops."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from .agent_runtime import AgentSessionRunner
from .agent_tools import TRANSCRIBING_MARKER, media_brief, pending_transcripts, resource_brief
from .catalog import record_manual, record_render, record_turn, snapshot
from .fast_edit import _ask as plan_call, run_fast_edit
from . import style_notes
from .assembly import assemble
from .edit_brief import compose_request
from .ingest import ingest_asset, ingest_resource
from .transcription import DEFAULT_LANGUAGE, TUNISIAN, clean_mixed, transcribe_to_folder, write_transcript
from .jobs import JobRecord

logger = logging.getLogger("video-editor-worker")
from .quality_harness.models import ReviewInput, TimelineSpec
from .quality_harness.verification import verify_render
from .quality_harness.review import run_blind_sdk_review
from .project_bootstrap import SKILLS_ROOT
from .style_extraction import BASE_STYLES, STYLES_DIR, download_references, fork_base, install_user_skill, skill_summary, split_urls, style_brief, validate_user_urls, write_fork_tool


@dataclass
class WorkerContext:
    projects_root: Path
    storage_root: Path
    event_sink: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None
    agent_persistence: Any = None
    studio: Any = None

    def project_dir(self, project_id: str) -> Path:
        root = (self.projects_root / project_id).resolve()
        if not root.is_relative_to(self.projects_root.resolve()):
            raise ValueError("Project path escapes worker root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def emit(self, stream_id: str, event: dict[str, Any]) -> None:
        if self.event_sink:
            result = self.event_sink(stream_id, event)
            if asyncio.iscoroutine(result):
                await result


def _storage_path(context: WorkerContext, key: str) -> Path:
    path = (context.storage_root / key).resolve()
    if not path.is_relative_to(context.storage_root.resolve()):
        raise ValueError("Storage path escapes storage root")
    if not path.is_file():
        raise FileNotFoundError(key)
    return path


def failure_event(job: JobRecord, error: str) -> tuple[str, dict[str, Any]] | None:
    """The event a failed job reports, so the studio stops waiting on it."""

    payload, error = job.payload, error[:2000]
    if job.type == "ingest":
        return str(payload.get("project_id", "")), {"type": "ingest.failed", "asset_id": payload.get("asset_id"), "error": error}
    if job.type == "agent_run":
        return str(payload["run_id"]), {"type": "agent.failed", "reason": error}
    if job.type in ("render", "manual_render"):
        return str(payload["render_id"]), {"type": "render.failed", "error": error}
    if job.type == "studio_open":
        return str(payload.get("project_id", "")), {"type": "studio.failed", "error": error}
    if job.type == "transcribe":
        return str(payload.get("project_id", "")), {"type": "transcribe.failed", "asset_id": payload.get("asset_id"), "error": error}
    if job.type in ("style_extraction", "skill_edit"):
        return str(payload["extraction_id"]), {"type": "style.failed", "error": error}
    return None


async def handle_job(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    payload = job.payload
    project_id = str(payload.get("project_id", ""))
    if job.type == "ingest":
        source = _storage_path(context, str(payload["storage_key"]))
        project = context.project_dir(project_id)
        raw_dir = project / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_copy = raw_dir / source.name
        if not raw_copy.exists():
            shutil.copyfile(source, raw_copy)
        if payload.get("role") == "resource" or "/resources/" in str(payload["storage_key"]):
            metadata = {"id": str(payload["asset_id"]), "filename": str(payload.get("filename") or source.name), "mime_type": payload.get("mime_type")}
            await context.emit(project_id, {"type": "ingest.started", "asset_id": payload["asset_id"]})
            result = await asyncio.to_thread(ingest_resource, raw_copy, project / "proxies" / str(payload["asset_id"]), asset=metadata)
            await context.emit(project_id, {"type": "ingest.completed", "asset_id": payload["asset_id"], "probe": result["manifest"]["probe"]})
            return result
        # The marker tells agent runs a transcript is on its way.
        marker = project / "proxies" / str(payload["asset_id"]) / TRANSCRIBING_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        await context.emit(project_id, {"type": "ingest.started", "asset_id": payload["asset_id"]})
        metadata = {"id": str(payload["asset_id"]), "filename": str(payload.get("filename") or source.name), "mime_type": payload.get("mime_type")}
        # ffmpeg is CPU-bound and blocking; keep the event loop (and the API
        # when the worker runs in-process) responsive.
        result = await asyncio.to_thread(ingest_asset, raw_copy, project / "proxies" / str(payload["asset_id"]), asset=metadata)
        await context.emit(project_id, {"type": "ingest.completed", "asset_id": payload["asset_id"], "probe": result["manifest"]["probe"]})
        try:
            if result["manifest"]["probe"].get("has_audio"):
                # Transcribe right away so the user can correct the words
                # before any edit; a failure here never undoes the upload.
                await transcribe_asset(context, project_id, str(payload["asset_id"]), payload.get("language"))
        finally:
            marker.unlink(missing_ok=True)
        return result

    if job.type == "transcribe":
        return await transcribe_asset(context, project_id, str(payload["asset_id"]), payload.get("language"), vocabulary=str(payload.get("vocabulary") or ""), raise_errors=True)

    if job.type == "agent_run":
        prompt = str(payload.get("prompt") or payload.get("brief") or "Inspect the project and make the requested edit.")
        project = context.project_dir(project_id)
        runner = AgentSessionRunner(project)
        # Captions are built from the transcript: wait for clips still being
        # transcribed, then hand the agent every clip with its transcript.
        for _ in range(180):
            if not pending_transcripts(project):
                break
            if _ == 0:
                await context.emit(str(payload["run_id"]), {"type": "agent.waiting", "reason": "transcription"})
            await asyncio.sleep(5)
        run_id = str(payload["run_id"])
        kind = str(payload.get("kind") or "people")
        guidance = {"kind": payload.get("kind"), "intensity": payload.get("intensity"), "script": payload.get("script"), "brand": payload.get("brand")}

        def with_guidance(text: str) -> str:
            # An After Effects export has its own complete brief: no editing guidance.
            return compose_request(text, **guidance) if any(guidance.values()) and not payload.get("ae_export") else text

        # Several clips (or "cut my takes"): join them into one clip first; the
        # style then edits that clip like any other. Follow-ups reuse it.
        asset_id, extra_cost = payload.get("asset_id"), 0.0
        clips = [str(clip) for clip in payload.get("clips") or []]
        if kind == "people" and clips and (len(clips) > 1 or payload.get("cut")):
            asset_id, extra_cost = await assemble(project, clips, cut=bool(payload.get("cut")), ask=plan_call, emit=lambda event: context.emit(run_id, event), run_id=run_id)

        if payload.get("mode") == "fast":
            # One planning call + the style's own scripts: see fast_edit.py.
            if context.agent_persistence:
                await context.agent_persistence.update_agent_run(run_id, {"status": "running"})
            await context.emit(run_id, {"type": "agent.started", "mode": "fast"})
            before = snapshot(project)
            try:
                fast = await run_fast_edit(project, run_id=run_id, skill=str(payload.get("skill")), request=with_guidance(str(payload.get("prompt") or payload.get("title") or "")), emit=lambda event: context.emit(run_id, event), asset_id=asset_id, quick=bool(payload.get("quick")), resources=list(payload.get("resources") or []), footage=kind == "people", caption_skill=payload.get("caption_skill"))
                fast["usage"]["total_cost_usd"] = round(fast["usage"]["total_cost_usd"] + extra_cost, 4)
            finally:
                record_turn(project, before, run_id=run_id, skill=payload.get("skill"), title=str(payload.get("title") or ""))
            await keep_as_preview(context, payload, Path(fast["output"]))
            if context.agent_persistence:
                await context.agent_persistence.update_agent_run(run_id, {"status": "succeeded", "budget_json": fast["usage"]})
            await context.emit(run_id, {"type": "agent.succeeded", "usage": fast["usage"], "output": fast["output"]})
            return {"status": "succeeded", **fast}

        prompt = with_guidance(prompt)
        caption_skill = payload.get("caption_skill")
        if caption_skill and caption_skill != payload.get("skill"):
            prompt += f"\n\nCombine two styles: make the captions exactly as the `{caption_skill}` skill does (font, size, colours, position, word timing, animation) and everything else (scenes, motion graphics, transitions, zooms, sounds) as `{payload.get('skill')}` does. Read both skills first."
        if asset_id and str(asset_id).startswith("asm-"):
            prompt += f"\n\nEdit the clip `{asset_id}` (`proxies/{asset_id}/assembled.mp4`, transcript in the same folder): the studio already cut the user's clips and joined them in their order."
        if attached := resource_brief(project, list(payload.get("resources") or [])):
            prompt = f"{prompt}\n\n{attached}"
        if notes := style_notes.prepare(project, payload.get("skill")):
            prompt = f"{prompt}\n\n{notes}"
        if payload.get("ae_export"):
            pass
        elif kind != "people":
            prompt += "\n\nThere is no footage for this video: build every scene."
        elif brief := media_brief(project):
            prompt = f"{brief}\n## Request\n\n{prompt}"
        async def on_agent_event(event: dict[str, Any]) -> None:
            await context.emit(str(payload["run_id"]), event)
            if context.agent_persistence and event.get("type") == "agent.message":
                await context.agent_persistence.add_agent_message(str(payload["run_id"]), "assistant", dict(event.get("message", {})))

        if context.agent_persistence:
            await context.agent_persistence.update_agent_run(str(payload["run_id"]), {"status": "running"})
        await context.emit(str(payload["run_id"]), {"type": "agent.started"})
        before = snapshot(project)
        try:
            result = await runner.run(prompt, event_sink=on_agent_event, resume=payload.get("resume") or None, skills=skills_for(project, payload.get("skill"), payload.get("caption_skill")))
        finally:
            # Tie the reels and videos this turn produced to its style.
            record_turn(project, before, run_id=str(payload["run_id"]), skill=payload.get("skill"), title=str(payload.get("title") or payload.get("brief") or ""))
        if extra_cost:
            result.usage["total_cost_usd"] = round(float(result.usage.get("total_cost_usd") or 0) + extra_cost, 4)
        if payload.get("ae_export") and result.status == "succeeded":
            from .ae_export import zip_export

            try:
                bundle = await asyncio.to_thread(zip_export, project, str(payload["ae_export"]))
                await context.emit(str(payload["run_id"]), {"type": "ae.export.ready", "path": bundle.relative_to(project).as_posix()})
            except FileNotFoundError as exc:
                await context.emit(str(payload["run_id"]), {"type": "ae.export.failed", "error": str(exc)})
        if context.agent_persistence:
            await context.agent_persistence.update_agent_run(str(payload["run_id"]), {"status": result.status, "sdk_session_id": result.session_id, "budget_json": result.usage})
        if result.status == "succeeded":
            style_notes.publish(project, payload.get("skill"))
        return {"status": result.status, "session_id": result.session_id, "usage": result.usage}

    if job.type == "style_extraction":
        return await clone_style(job, context)

    if job.type == "skill_edit":
        return await edit_skill(job, context)

    if job.type == "skill_preview":
        from .skill_previews import install_preview

        video = (context.project_dir(project_id) / str(payload["path"])).resolve()
        if not video.is_relative_to(context.project_dir(project_id).resolve()) or not video.is_file():
            raise FileNotFoundError(str(payload["path"]))
        folder = await asyncio.to_thread(install_preview, context.projects_root.resolve(), str(payload["name"]), video)
        return {"status": "succeeded", "preview": str(folder)}

    if job.type == "render":
        return await render_job(job, context)

    if job.type == "manual_render":
        return await manual_render_job(job, context)

    if job.type == "studio_open":
        project = context.project_dir(project_id)
        requested = (project / str(payload["composition"])).resolve() if payload.get("composition") else None
        composition = requested if requested and requested.is_relative_to(project / "compositions") and (requested / "index.html").is_file() else latest_composition(project)
        if composition is None:
            raise FileNotFoundError("This project has no HyperFrames composition yet: run an edit first")
        if context.studio is None:
            from .studio import StudioManager

            context.studio = StudioManager()
        session = await context.studio.open(project_id, composition)
        event = {"type": "studio.ready", "url": session.url, "composition": f"compositions/{composition.name}"}
        await context.emit(project_id, event)
        return event

    if job.type == "composition_preview":
        composition = Path(str(payload["composition_path"])).resolve()
        if not composition.is_relative_to(context.project_dir(project_id)):
            raise ValueError("Composition is outside the project folder")
        await context.emit(str(payload["job_id"]), {"type": "preview.queued", "composition_path": str(composition)})
        return {"status": "queued", "composition_path": str(composition)}

    if job.type in {"generate_image", "generate_voiceover"}:
        # Provider adapters are injected by the deployment worker; keeping the
        # job type explicit makes retries and usage accounting observable.
        return {"status": "queued", "provider": "openai" if job.type == "generate_image" else "voice"}

    raise ValueError(f"Unknown job type: {job.type}")


# Helpers a style calls into; only these load next to the chosen style.
SUPPORT_SKILLS = ("hyperframes", "hyperframes-core", "hyperframes-cli", "hyperframes-animation", "media-use")


async def keep_as_preview(context: WorkerContext, payload: dict[str, Any], output: Path) -> None:
    """A requested demo becomes its style's trailer; so does the first video made in a style."""

    from . import skill_previews

    name = payload.get("preview_for") or payload.get("skill")
    if not name or not output.is_file() or payload.get("caption_skill"):
        return
    root = context.projects_root.resolve()
    if payload.get("preview_for") or not skill_previews.has_preview(root, str(name)):
        try:
            await asyncio.to_thread(skill_previews.install_preview, root, str(name), output)
        except Exception:  # a trailer is a nicety: never fail the edit over it
            logger.exception("skill_preview_failed style=%s", name)


def skills_for(project: Path, skill: str | None, caption_skill: str | None = None) -> list[str] | str:
    """Load only the chosen style(s) and their helpers: every listed skill is re-read each turn."""

    if not skill:
        return "all"
    installed = project / ".claude" / "skills"
    names = dict.fromkeys(name for name in (skill, caption_skill, *SUPPORT_SKILLS) if name)
    return [name for name in names if (installed / name / "SKILL.md").is_file()]


async def transcribe_asset(context: WorkerContext, project_id: str, asset_id: str, language: str | None = None, *, vocabulary: str = "", raise_errors: bool = False) -> dict[str, Any]:
    folder = context.project_dir(project_id) / "proxies" / asset_id
    language = language or DEFAULT_LANGUAGE
    marker = folder / TRANSCRIBING_MARKER
    folder.mkdir(parents=True, exist_ok=True)
    marker.touch()
    try:
        return await _transcribe_asset(context, project_id, asset_id, folder, language, vocabulary, raise_errors)
    finally:
        marker.unlink(missing_ok=True)


async def _transcribe_asset(context: WorkerContext, project_id: str, asset_id: str, folder: Path, language: str, vocabulary: str, raise_errors: bool) -> dict[str, Any]:
    await context.emit(project_id, {"type": "transcribe.started", "asset_id": asset_id})
    try:
        result = await asyncio.to_thread(transcribe_to_folder, folder / "audio.wav", folder, language=language, vocabulary=vocabulary)
    except Exception as exc:
        await context.emit(project_id, {"type": "transcribe.failed", "asset_id": asset_id, "error": str(exc)[:2000]})
        if raise_errors:
            raise
        return {"status": "failed", "error": str(exc)}
    records = result.pop("records")
    if language == TUNISIAN and records and os.getenv("TRANSCRIPT_CLEANUP", "on") != "off":
        # Second pass: French/English back to Latin script, Darija spelling.
        await context.emit(project_id, {"type": "transcribe.cleaning", "asset_id": asset_id})
        try:
            cleaned = await asyncio.wait_for(clean_mixed(records, vocabulary=vocabulary), timeout=600)
            write_transcript(folder, cleaned, language=TUNISIAN, reviewed=False)
            result["words"] = len(cleaned)
        except Exception as exc:  # keep Whisper's words rather than nothing
            logger.warning("transcript_cleanup_failed asset=%s error=%s", asset_id, exc)
            result["cleanup_error"] = str(exc)[:500]
    await context.emit(project_id, {"type": "transcribe.completed", "asset_id": asset_id, **result})
    return {"status": "succeeded", **result}


async def edit_skill(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    """Let the agent change a copy of a style as the user asked, then install it."""

    from . import skill_editing

    payload = job.payload
    stream = str(payload["extraction_id"])
    source_name, target = str(payload["source"]), str(payload["name"])
    projects_root = context.projects_root.resolve()
    source = skill_editing.skill_source_dir(source_name, projects_root)
    if source is None:
        raise FileNotFoundError(f"Style {source_name} is not installed")
    workspace = context.project_dir(f"{STYLES_DIR}/{stream}")
    skill_editing.prepare_edit(workspace, source, target)
    await context.emit(stream, {"type": "agent.started", "base": source_name})
    brief = skill_editing.EDIT_BRIEF.format(target=target, source=source_name, request=str(payload["request"]).strip())
    result = await AgentSessionRunner(workspace).run(brief, event_sink=lambda event: context.emit(stream, event))
    if result.status != "succeeded":
        raise RuntimeError("The edit did not finish; see the run messages")
    skill_editing.backup_installed(projects_root, target)
    installed = install_user_skill(workspace, target, projects_root)
    summary = skill_summary(installed)
    await context.emit(stream, {"type": "style.completed", "skill": summary})
    return {"skill_path": str(installed), **summary}


async def clone_style(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    """Download references, let the agent write the style skill, install it."""

    payload = job.payload
    stream = str(payload["extraction_id"])
    name = str(payload["name"])
    workspace = context.project_dir(f"{STYLES_DIR}/{stream}")
    await context.emit(stream, {"type": "style.downloading"})
    urls = validate_user_urls(split_urls([str(url) for url in payload["urls"]]))
    files = await asyncio.to_thread(download_references, urls, workspace / "reference")
    for folder in ("analysis/frames", "test-run"):
        (workspace / folder).mkdir(parents=True, exist_ok=True)
    # Clones restyle a proven engine instead of starting from nothing.
    base = payload.get("base") if payload.get("base") in BASE_STYLES else None
    if base:
        fork_base(workspace, name, base, SKILLS_ROOT / "library")
    else:
        write_fork_tool(workspace, name)
    await context.emit(stream, {"type": "agent.started", "base": base})
    brief = style_brief(name, [path.relative_to(workspace).as_posix() for path in files], str(payload.get("notes") or ""), base)
    result = await AgentSessionRunner(workspace).run(brief, event_sink=lambda event: context.emit(stream, event))
    if result.status != "succeeded":
        raise RuntimeError("The style analysis did not finish; see the run messages")
    target = install_user_skill(workspace, name, context.projects_root.resolve())
    summary = skill_summary(target)
    await context.emit(stream, {"type": "style.completed", "skill": summary})
    return {"skill_path": str(target), **summary}


def latest_composition(project: Path) -> Path | None:
    """Most recently edited HyperFrames project under ``compositions/``."""

    candidates = [path for path in (project / "compositions").glob("*/index.html") if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime).parent if candidates else None


def hyperframes_render_command(output: Path) -> list[str]:
    # On Windows npx is ``npx.cmd``; which() returns the launcher to execute.
    return [shutil.which("npx") or "npx", "hyperframes", "render", "--output", str(output)]


async def manual_render_job(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    """Export a manual edit with FFmpeg: no agent, no API credits."""

    from . import manual_edit

    payload = job.payload
    project = context.project_dir(str(payload["project_id"]))
    render_id = str(payload["render_id"])
    doc = manual_edit.load_edit(project, str(payload["edit_id"]))
    await context.emit(render_id, {"type": "render.started", "source": f"edits/{doc.id}"})
    sources = {asset_id: _storage_path(context, str(key)) for asset_id, key in dict(payload["sources"]).items()}
    folder = manual_edit.edit_dir(project, doc.id)
    subtitles = manual_edit.build_ass(doc)
    if subtitles:
        (folder / "overlay.ass").write_text(subtitles, encoding="utf-8")
    slug = re.sub(r"[^a-z0-9]+", "-", doc.name.lower()).strip("-")[:40] or "edit"
    output = project / "renders" / f"{slug}-{render_id[:8]}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    argv = manual_edit.export_command(doc, sources, dict(payload.get("has_audio") or {}), output, subtitles="overlay.ass" if subtitles else None)
    argv[0] = shutil.which("ffmpeg") or "ffmpeg"
    completed = await asyncio.to_thread(subprocess.run, argv, cwd=folder, capture_output=True, text=True)
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError(f"ffmpeg export failed: {(completed.stderr or completed.stdout).strip()[-2000:]}")
    record_manual(project, output, doc.id, doc.name, render_id)
    from .quality_harness.verification import FFProbeRunner, parse_probe

    probe = parse_probe(await asyncio.to_thread(FFProbeRunner().probe, output))
    verification = {"ok": bool(probe.duration_ms), "source": "manual", "observed": probe.model_dump(mode="json", exclude={"raw"})}
    await context.emit(render_id, {"type": "render.completed", "output_path": str(output), "verification": verification, "review": None})
    return {"status": "succeeded", "output_path": str(output), "verification": verification}


async def render_job(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    project = context.project_dir(str(job.payload["project_id"]))
    render_id = str(job.payload["render_id"])
    output = project / "renders" / f"{render_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = project / "render.ffconcat"
    requested = (project / str(job.payload["composition"])).resolve() if job.payload.get("composition") else None
    composition = None if manifest.is_file() else requested if requested and (requested / "index.html").is_file() and requested.is_relative_to(project / "compositions") else latest_composition(project)
    await context.emit(render_id, {"type": "render.started", "source": "timeline" if composition is None else f"compositions/{composition.name}"})

    if composition is not None:
        # HyperFrames projects (wassim-style and friends) carry their own
        # timing; the CLI renders them and ffprobe verifies the file exists
        # and is playable rather than comparing it to timeline.json.
        completed = await asyncio.to_thread(subprocess.run, hyperframes_render_command(output), cwd=composition, capture_output=True, text=True)
        if completed.returncode != 0 or not output.is_file():
            raise RuntimeError(f"hyperframes render failed: {(completed.stderr or completed.stdout).strip()[-2000:]}")
        record_render(project, output, composition, render_id)
        from .quality_harness.verification import FFProbeRunner, parse_probe

        probe = parse_probe(await asyncio.to_thread(FFProbeRunner().probe, output))
        verification = {"ok": bool(probe.duration_ms), "source": "hyperframes", "observed": probe.model_dump(mode="json", exclude={"raw"})}
        await context.emit(render_id, {"type": "render.completed", "output_path": str(output), "verification": verification, "review": None})
        return {"status": "succeeded", "output_path": str(output), "verification": verification, "review": None}

    timeline_path = project / "timeline.json"
    if not timeline_path.is_file():
        raise FileNotFoundError("timeline.json")
    if not manifest.is_file():
        raise FileNotFoundError("Nothing to render yet: ask the agent to build a composition under compositions/ or a render.ffconcat from the timeline")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    spec = TimelineSpec(duration_ms=int(timeline["duration_ms"]), width=int(timeline["width"]), height=int(timeline["height"]), fps=float(timeline["fps"]))
    from .media import render_timeline_command, run_media_command

    await asyncio.to_thread(run_media_command, render_timeline_command(manifest, output, fps=round(spec.fps), width=spec.width, height=spec.height))
    report = await asyncio.to_thread(verify_render, output, spec)
    if not report.ok:
        raise RuntimeError(report.model_dump_json())
    review = None
    if str(job.payload.get("preset", "preview")) != "preview" and os.getenv("ANTHROPIC_API_KEY"):
        review_input = ReviewInput(original_brief=str(job.payload.get("brief", "Verify the final render against the timeline.")), timeline=timeline, frame_extracts=[str(item) for item in job.payload.get("frame_extracts", [])], verification_report=report)
        passed, issues = await run_blind_sdk_review(review_input, model=os.getenv("AGENT_MODEL", "claude-opus-5-5"))
        review = {"passed": passed, "issues": issues, "cycle": 1}
        if not passed:
            raise RuntimeError(json.dumps({"review_failed": issues}))
    await context.emit(render_id, {"type": "render.completed", "output_path": str(output), "verification": report.model_dump(mode="json"), "review": review})
    return {"status": "succeeded", "output_path": str(output), "verification": report.model_dump(mode="json"), "review": review}
