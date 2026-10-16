"""Domain tools exposed to Claude through an in-process MCP server."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from packages.timeline_schema import Timeline, TimelineOp, apply_timeline_ops


def load_project_media(project_dir: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Read the asset manifests and transcripts the ingest job wrote.

    Each ingested asset owns ``proxies/<asset_id>/`` with ``asset.json``
    (written by ``ingest_asset``) and ``transcript.json``.
    """

    assets: dict[str, dict[str, Any]] = {}
    transcripts: dict[str, list[dict[str, Any]]] = {}
    for manifest in sorted(Path(project_dir).resolve().glob("proxies/*/asset.json")):
        try:
            asset = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        asset_id = str(asset.get("id") or manifest.parent.name)
        assets[asset_id] = asset
        transcript = manifest.parent / "transcript.json"
        if transcript.is_file():
            try:
                transcripts[asset_id] = json.loads(transcript.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                transcripts[asset_id] = []
    return assets, transcripts


TRANSCRIBING_MARKER = ".transcribing"


def pending_transcripts(project_dir: str | Path) -> list[str]:
    """Clips whose ingest or transcription is still running."""

    return sorted(marker.parent.name for marker in Path(project_dir).resolve().glob(f"proxies/*/{TRANSCRIBING_MARKER}"))


def _clock(ms: int) -> str:
    return f"{ms / 1000:.1f}"


def media_brief(project_dir: str | Path) -> str:
    """Describe every clip and its transcript for the start of an agent turn.

    The transcript (corrected by the user when marked reviewed) is the source
    of truth for captions, so it is handed over in full rather than left for
    the agent to find or re-create.
    """

    root = Path(project_dir).resolve()
    assets, transcripts = load_project_media(root)
    if not assets:
        return ""
    lines = ["## Project media (prepared by the studio)", ""]
    for asset_id, asset in assets.items():
        if asset.get("role") == "resource":
            continue  # attached per request, see resource_brief
        probe = asset.get("probe") or {}
        folder = root / "proxies" / asset_id
        try:
            meta = json.loads((folder / "transcript.meta.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        raw = Path(str(asset.get("path", ""))).name
        size = f"{probe.get('width')}x{probe.get('height')}" if probe.get("width") else "audio"
        duration = f"{(probe.get('duration_ms') or 0) / 1000:.1f}s"
        lines.append(f"### Clip `{asset_id}`: {asset.get('filename', raw)} ({duration}, {size})")
        lines.append(f"- source: `raw/{raw}`, proxy: `proxies/{asset_id}/proxy.mp4`")
        words = transcripts.get(asset_id) or []
        if not words:
            lines.append("- transcript: none (no speech, or transcription failed); transcribe with the skill's script if you need one")
            lines.append("")
            continue
        language = {"tn": "Tunisian (Darija in Arabic script, French/English in Latin)"}.get(str(meta.get("language")), str(meta.get("language") or "unknown"))
        status = "REVIEWED and corrected by the user" if meta.get("reviewed") else "automatic, not reviewed yet"
        status += ": use these exact words and timings; never re-transcribe, respell or correct them (the user fixes words in the Transcripts center)"
        lines.append(f"- transcript: {language}; {status}")
        lines.append(f"- files: `proxies/{asset_id}/transcript.json` (ms) and `proxies/{asset_id}/words.json` (the skills' `edit/words.json` format, seconds): copy words.json into the skill project's `edit/words.json`")
        segments: dict[int, list[dict[str, Any]]] = {}
        for word in words:
            segments.setdefault(int(word.get("segment", 0)), []).append(word)
        lines.append("")
        lines.append("```")
        for segment in segments.values():
            lines.append(f"[{_clock(segment[0]['start_ms'])}-{_clock(segment[-1]['end_ms'])}] " + " ".join(str(word["text"]) for word in segment))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def describe_resource(asset: dict[str, Any]) -> str:
    probe = asset.get("probe") or {}
    seconds = (probe.get("duration_ms") or 0) / 1000
    if probe.get("width") and seconds > 1:
        kind = f"video {probe['width']}x{probe['height']}, {seconds:.1f}s"
    elif probe.get("width"):
        kind = f"image {probe['width']}x{probe['height']}"
    else:
        kind = f"audio {seconds:.1f}s"
    return f"{asset.get('filename')} ({kind})"


def resource_brief(project_dir: str | Path, ids: list[str]) -> str:
    """The files the user attached to this request, for agent-mode turns."""

    assets, _ = load_project_media(project_dir)
    lines = [f"- `raw/{Path(str(assets[item].get('path', ''))).name}`: {describe_resource(assets[item])}" for item in ids if item in assets]
    if not lines:
        return ""
    return (
        "## Attached resources\n\nThe user attached these for this request. Copy each one you use into the composition's "
        "`assets/resources/` and use it where the request says (images as cards, screenshots or overlays; sounds as SFX or music):\n"
        + "\n".join(lines)
    )


class ProjectToolService:
    def __init__(
        self,
        project_dir: str | Path,
        assets: dict[str, dict[str, Any]] | None = None,
        transcripts: dict[str, list[dict[str, Any]]] | None = None,
        render_callback: Callable[[str], dict[str, Any]] | None = None,
        image_callback: Callable[..., dict[str, Any]] | None = None,
    ):
        self.project_dir = Path(project_dir).resolve()
        self.assets = assets or {}
        self.transcripts = transcripts or {}
        self.render_callback = render_callback
        self.image_callback = image_callback
        self.timeline_path = self.project_dir / "timeline.json"
        self.renders_dir = self.project_dir / "renders"
        self.renders_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def get_timeline(self) -> Timeline:
        if not self.timeline_path.exists():
            return Timeline(fps=30, width=1920, height=1080, duration_ms=1000)
        return Timeline.model_validate_json(self.timeline_path.read_text(encoding="utf-8"))

    def apply_timeline_ops(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        timeline, diff = apply_timeline_ops(self.get_timeline(), [TimelineOp.model_validate(op) for op in ops])
        temporary = self.timeline_path.with_suffix(".json.tmp")
        temporary.write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.timeline_path)
        # hash() is salted per process; a content hash stays stable across
        # worker restarts so the studio can compare versions.
        version_id = hashlib.sha256(timeline.model_dump_json().encode()).hexdigest()[:16]
        return {"timeline": timeline.model_dump(mode="json"), "diff": diff, "version_id": version_id}

    def list_assets(self) -> list[dict[str, Any]]:
        return list(self.assets.values())

    def describe_asset(self, asset_id: str) -> dict[str, Any]:
        if asset_id not in self.assets:
            raise ValueError(f"Unknown asset: {asset_id}")
        return self.assets[asset_id]

    def get_transcript(self, asset_id: str, start_ms: int | None = None, end_ms: int | None = None) -> list[dict[str, Any]]:
        words = self.transcripts.get(asset_id, [])
        if start_ms is None and end_ms is None:
            return words
        return [word for word in words if (end_ms is None or int(word.get("start_ms", 0)) < end_ms) and (start_ms is None or int(word.get("end_ms", 0)) > start_ms)]

    def search_transcript(self, query: str) -> list[dict[str, Any]]:
        terms = [term for term in re.findall(r"[\w']+", query.lower()) if term]
        if not terms:
            return []
        matches: list[dict[str, Any]] = []
        for asset_id, words in self.transcripts.items():
            for word in words:
                if any(term in str(word.get("text", "")).lower() for term in terms):
                    matches.append({"asset_id": asset_id, **word})
        return matches

    def auto_cut_silence(self, asset_id: str, threshold_db: float, min_silence_ms: int, padding_ms: int) -> dict[str, Any]:
        if asset_id not in self.assets:
            raise ValueError(f"Unknown asset: {asset_id}")
        if min_silence_ms < 1 or padding_ms < 0:
            raise ValueError("Silence and padding values must be positive")
        # The exact waveform analysis is performed by the worker's FFmpeg
        # pipeline. This tool returns a typed request and keeps edits
        # deterministic when no audio probe is available yet.
        return {"asset_id": asset_id, "threshold_db": threshold_db, "min_silence_ms": min_silence_ms, "padding_ms": padding_ms, "segments": []}

    def remove_filler_words(self, asset_id: str, fillers: list[str]) -> dict[str, Any]:
        words = self.get_transcript(asset_id)
        normalized = {word.strip().lower() for word in fillers if word.strip()}
        removed = [word for word in words if str(word.get("text", "")).strip().lower() in normalized]
        return {"asset_id": asset_id, "removed_word_ids": [word.get("id") for word in removed], "cut_ranges": [{"start_ms": word.get("start_ms"), "end_ms": word.get("end_ms")} for word in removed]}

    def extract_frames(self, asset_id: str, timestamps: list[int]) -> list[str]:
        asset = self.describe_asset(asset_id)
        source = asset.get("proxy_path") or asset.get("path")
        if not source:
            return []
        output_dir = self.project_dir / "proxies" / "frames" / asset_id
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[str] = []
        for timestamp in timestamps:
            if timestamp < 0:
                raise ValueError("Frame timestamps must be non-negative")
            target = output_dir / f"{timestamp:010d}.jpg"
            subprocess.run(("ffmpeg", "-y", "-ss", f"{timestamp / 1000:.3f}", "-i", str(Path(source).resolve()), "-frames:v", "1", str(target)), check=True, capture_output=True, text=True)
            results.append(str(target))
        return results

    def render_preview(self) -> dict[str, Any]:
        return self._render("preview")

    def render_final(self, preset: str) -> dict[str, Any]:
        return self._render(preset)

    def _render(self, preset: str) -> dict[str, Any]:
        if preset not in {"preview", "1080p30", "1080p60", "4K", "9:16", "1:1"}:
            raise ValueError("Unsupported render preset")
        if self.render_callback:
            return self.render_callback(preset)
        return {"status": "queued", "preset": preset, "timeline_path": str(self.timeline_path)}

    def get_render_status(self, render_id: str) -> dict[str, Any]:
        status_path = self.renders_dir / render_id / "status.json"
        if not status_path.exists():
            return {"render_id": render_id, "status": "unknown"}
        return {"render_id": render_id, **json.loads(status_path.read_text(encoding="utf-8"))}

    def generate_image(self, prompt: str, size: str, transparent_background: bool = False) -> dict[str, Any]:
        if not prompt.strip():
            raise ValueError("Image prompt cannot be empty")
        if self.image_callback:
            return self.image_callback(prompt=prompt, size=size, transparent_background=transparent_background)
        return {"status": "queued", "prompt": prompt, "size": size, "transparent_background": transparent_background}

    def generate_voiceover(self, script: str, voice_id: str) -> dict[str, Any]:
        if not script.strip() or not voice_id.strip():
            raise ValueError("Voiceover script and voice_id are required")
        return {"status": "queued", "voice_id": voice_id, "script": script}

    def ask_user(self, question: str, options: list[str]) -> dict[str, Any]:
        if not question.strip() or not options:
            raise ValueError("ask_user requires a question and at least one option")
        record = {"question": question, "options": [str(option) for option in options]}
        questions = self.project_dir / ".agent-context" / "questions.jsonl"
        questions.parent.mkdir(parents=True, exist_ok=True)
        with questions.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        # Runs are not interactive: the studio shows the question and the
        # user's answer resumes this SDK session as a new turn.
        return {
            "status": "needs_user",
            **record,
            "instruction": "Stop here. End your turn with the question and options so the user can answer; their reply resumes this session.",
        }

    def preview_composition(self, composition_path: str) -> dict[str, Any]:
        candidate = (self.project_dir / composition_path).resolve()
        if not candidate.is_relative_to(self.project_dir) or not candidate.is_file():
            raise ValueError("Composition path must be an existing project file")
        return {"status": "queued", "composition_path": str(candidate)}
