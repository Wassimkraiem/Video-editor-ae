"""Domain tools exposed to Claude through an in-process MCP server."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from packages.timeline_schema import Timeline, TimelineOp, apply_timeline_ops


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
        return {"timeline": timeline.model_dump(mode="json"), "diff": diff, "version_id": str(abs(hash(timeline.model_dump_json()))) }

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
        return {"status": "needs_user", "question": question, "options": options}

    def preview_composition(self, composition_path: str) -> dict[str, Any]:
        candidate = (self.project_dir / composition_path).resolve()
        if not candidate.is_relative_to(self.project_dir) or not candidate.is_file():
            raise ValueError("Composition path must be an existing project file")
        return {"status": "queued", "composition_path": str(candidate)}
