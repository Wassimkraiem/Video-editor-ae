"""Read a HyperFrames composition back as a studio timeline.

Style skills (wassim-style, talking-head-glass-edit, ...) edit by authoring a
HyperFrames project, not by writing ``timeline.json``. Its ``index.html``
declares every track with ``data-start``/``data-duration``/
``data-track-index``, and the skills' ``edit/`` plans hold the finer beats:
caption groups (word indices into ``transcript.json``) and SFX cues.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

SFX_MARK_S = 0.25


class _ClipParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root: dict[str, str] | None = None
        self.clips: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if "data-start" not in values:
            return
        if self.root is None and "data-track-index" not in values:
            self.root = values
        elif "data-track-index" in values:
            self.clips.append((tag, values))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


def _kind(tag: str, values: dict[str, str]) -> str:
    explicit = values.get("data-track-kind")
    if explicit:
        return "caption" if explicit.startswith("caption") else explicit
    if tag in {"video", "img"}:
        return "video"
    if tag == "audio":
        return "audio"
    return "graphics"


def _label(values: dict[str, str]) -> str:
    raw = values.get("data-composition-id") or values.get("id") or values.get("data-label") or ""
    return raw.replace("-host", "").replace("-", " ").replace("_", " ").strip() or "clip"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _caption_items(folder: Path) -> list[dict[str, Any]]:
    plan, words = _load(folder / "edit" / "captions.json"), _load(folder / "transcript.json")
    if not isinstance(plan, dict) or not isinstance(words, list):
        return []
    items = []
    for index, group in enumerate(plan.get("groups") or []):
        spans = [words[i] for _, indices in group.get("words") or [] for i in indices if isinstance(i, int) and 0 <= i < len(words)]
        if not spans:
            continue
        start, end = min(_number(w.get("start")) for w in spans), max(_number(w.get("end")) for w in spans)
        text = " ".join(str(word) for word, _ in group.get("words") or [])
        items.append({"id": f"caption-{index}", "type": "caption", "start_ms": _ms(start), "end_ms": _ms(max(end, start + 0.1)), "label": text})
    return items


def _sfx_items(folder: Path) -> list[dict[str, Any]]:
    plan = _load(folder / "edit" / "sfx.json")
    if not isinstance(plan, dict):
        return []
    items = []
    for index, cue in enumerate(plan.get("cues") or []):
        if isinstance(cue, list) and len(cue) >= 2:
            start = _number(cue[1])
            items.append({"id": f"sfx-{index}", "type": "sfx", "start_ms": _ms(start), "end_ms": _ms(start + SFX_MARK_S), "label": str(cue[0])})
    return items


def composition_timeline(project_root: Path, composition: str | None = None) -> dict[str, Any] | None:
    """Timeline of one composition (the most recently edited by default), or None if there is none."""

    candidates = [path for path in (project_root / "compositions").glob("*/index.html") if path.is_file()]
    if composition:
        candidates = [path for path in candidates if path.parent.relative_to(project_root).as_posix() == composition]
    if not candidates:
        return None
    index = max(candidates, key=lambda path: path.stat().st_mtime)
    parser = _ClipParser()
    parser.feed(index.read_text(encoding="utf-8", errors="replace"))
    root = parser.root or {}
    folder = index.parent

    captions, sfx = _caption_items(folder), _sfx_items(folder)
    tracks: dict[str, dict[str, Any]] = {}
    for position, (tag, values) in enumerate(sorted(parser.clips, key=lambda clip: _number(clip[1].get("data-track-index")))):
        kind = _kind(tag, values)
        # Detailed plans replace their single full-length host clip.
        if (kind == "caption" and captions) or (kind == "audio" and sfx and "sfx" in values.get("id", "")):
            continue
        start = _number(values.get("data-start"))
        end = start + _number(values.get("data-duration"))
        track = tracks.setdefault(f"{kind}-{values.get('data-track-index')}", {"id": f"{kind}-{values.get('data-track-index')}", "type": kind, "items": []})
        track["items"].append({"id": values.get("id") or f"clip-{position}", "type": kind, "start_ms": _ms(start), "end_ms": _ms(end), "label": _label(values)})
    if captions:
        tracks["caption"] = {"id": "caption", "type": "caption", "items": captions}
    if sfx:
        tracks["sfx"] = {"id": "sfx", "type": "sfx", "items": sfx}

    ends = [item["end_ms"] for track in tracks.values() for item in track["items"]]
    duration = _number(root.get("data-duration")) * 1000 or max(ends, default=1000)
    return {
        "version": 0,
        "source": f"compositions/{folder.name}",
        "data": {
            "duration_ms": round(duration),
            "width": int(_number(root.get("data-width"), 1080)),
            "height": int(_number(root.get("data-height"), 1920)),
            "fps": 30,
            "tracks": list(tracks.values()),
        },
    }
