"""Typed media probing and timeline/render verification."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol

from .models import RenderProbe, TimelineSpec, VerificationIssue, VerificationReport


class ProbeRunner(Protocol):
    def probe(self, media_path: Path) -> dict[str, Any]: ...


class FFProbeRunner:
    """Invoke ffprobe with an argv list; shell strings are never accepted."""

    def probe(self, media_path: Path) -> dict[str, Any]:
        path = media_path.resolve()
        command = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_entries",
            "format=duration:format_tags=integrated_lufs,lavfi.r128.I:stream=index,codec_type,width,height,avg_frame_rate:stream_tags=integrated_lufs,lavfi.r128.I",
            str(path),
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"ffprobe failed for {path}: {completed.stderr.strip()}")
        result = json.loads(completed.stdout or "{}")
        # ffprobe exposes dimensions/fps/duration, while ebur128 computes the
        # integrated loudness. Both commands use typed argv; no shell command
        # string is accepted. The measured value is added to the same raw
        # payload consumed by parse_probe().
        if any(item.get("codec_type") == "audio" for item in result.get("streams", [])):
            loudness = subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=framelog=verbose", "-f", "null", "-"],
                check=False,
                capture_output=True,
                text=True,
            )
            matches = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", loudness.stderr)
            if matches:
                result.setdefault("format", {}).setdefault("tags", {})["integrated_lufs"] = matches[-1]
        return result


def _parse_fps(value: str | int | float | None) -> float | None:
    if value in (None, "", "0/0"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        if float(denominator) == 0:
            return None
        return float(numerator) / float(denominator)
    return float(value)


def parse_probe(raw: dict[str, Any]) -> RenderProbe:
    streams = raw.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    tags: dict[str, Any] = {}
    tags.update(raw.get("format", {}).get("tags") or {})
    tags.update(video.get("tags") or {})
    loudness = next(
        (tags[key] for key in ("integrated_lufs", "lavfi.r128.I", "I") if tags.get(key) is not None),
        None,
    )
    loudness_value: float | None = None
    if loudness is not None:
        match = re.search(r"-?\d+(?:\.\d+)?", str(loudness))
        if match:
            loudness_value = float(match.group(0))
    return RenderProbe(
        duration_ms=round(float(raw.get("format", {}).get("duration", 0)) * 1000)
        if raw.get("format", {}).get("duration") is not None
        else None,
        width=video.get("width"),
        height=video.get("height"),
        fps=_parse_fps(video.get("avg_frame_rate")),
        loudness_lufs=loudness_value,
        raw=raw,
    )


def verify_render(render_path: str | Path, timeline: TimelineSpec, runner: ProbeRunner | None = None) -> VerificationReport:
    path = Path(render_path).resolve()
    observed = parse_probe((runner or FFProbeRunner()).probe(path))
    issues: list[VerificationIssue] = []

    def compare(field: str, expected: Any, actual: Any, message: str, tolerance: float = 0) -> None:
        if actual is None or abs(float(actual) - float(expected)) > tolerance:
            issues.append(VerificationIssue(field=field, expected=expected, actual=actual, message=message))

    compare("duration_ms", timeline.duration_ms, observed.duration_ms, "Render duration differs from timeline", timeline.duration_tolerance_ms)
    compare("width", timeline.width, observed.width, "Render width differs from timeline")
    compare("height", timeline.height, observed.height, "Render height differs from timeline")
    compare("fps", timeline.fps, observed.fps, "Render frame rate differs from timeline", timeline.fps_tolerance)
    compare("loudness_lufs", timeline.loudness_lufs, observed.loudness_lufs, "Integrated loudness differs from target", timeline.loudness_tolerance_lufs)
    return VerificationReport(ok=not issues, render_path=str(path), expected=timeline, observed=observed, issues=issues)
