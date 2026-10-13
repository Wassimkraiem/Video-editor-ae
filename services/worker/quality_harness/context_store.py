"""File-backed context with bounded reads for long editing runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProjectContextStore:
    def __init__(self, project_dir: str | Path) -> None:
        self.root = Path(project_dir).resolve()
        self.context_dir = self.root / ".agent-context"
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def write_transcript(self, asset_id: str, words: list[dict[str, Any]]) -> Path:
        path = self.context_dir / f"transcript-{asset_id}.json"
        path.write_text(json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def read_transcript_slice(self, asset_id: str, start_ms: int | None = None, end_ms: int | None = None) -> list[dict[str, Any]]:
        path = self.context_dir / f"transcript-{asset_id}.json"
        words = json.loads(path.read_text(encoding="utf-8"))
        return [word for word in words if (start_ms is None or word.get("start_ms", 0) >= start_ms) and (end_ms is None or word.get("end_ms", 0) <= end_ms)]

    def write_scene_data(self, asset_id: str, scenes: list[dict[str, Any]]) -> Path:
        path = self.context_dir / f"scenes-{asset_id}.json"
        path.write_text(json.dumps(scenes, indent=2) + "\n", encoding="utf-8")
        return path

    def read_scene_slice(self, asset_id: str, start_ms: int | None = None, end_ms: int | None = None) -> list[dict[str, Any]]:
        path = self.context_dir / f"scenes-{asset_id}.json"
        scenes = json.loads(path.read_text(encoding="utf-8"))
        return [scene for scene in scenes if (start_ms is None or scene.get("end_ms", 0) >= start_ms) and (end_ms is None or scene.get("start_ms", 0) <= end_ms)]

    def write_composition_html(self, composition_id: str, html: str) -> Path:
        path = self.context_dir / "compositions" / f"{composition_id}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def read_composition(self, composition_id: str) -> str:
        return (self.context_dir / "compositions" / f"{composition_id}.html").read_text(encoding="utf-8")

    def sdk_context_options(self) -> dict[str, object]:
        """Options used when constructing Claude Agent SDK sessions.

        The SDK owns compaction. Keeping the plan and project memory as files
        lets compacted sessions reload them without putting full transcripts in
        the prompt.
        """

        return {
            "context_files": [str(self.root / "CLAUDE.md"), str(self.root / "storyboard.json")],
            # Harness metadata consumed by sdk_runner. It is intentionally
            # removed before constructing ClaudeAgentOptions; sdk_runner
            # enables the Claude Code runtime's automatic compaction instead
            # of implementing a custom summarizer.
            "compaction": {"enabled": True, "preserve_files": ["CLAUDE.md", "storyboard.json"]},
        }
