"""Ingest pipeline boundary for probe, proxy, audio, transcript, and scenes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .media import audio_extract_command, ffprobe_command, proxy_command, thumbnail_command
from .transcription import Transcriber


def run_command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), check=True, capture_output=True, text=True)


def summarize_probe(probe: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields an editor needs instead of the full ffprobe dump."""

    streams = probe.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    duration = probe.get("format", {}).get("duration")
    rate = str(video.get("avg_frame_rate") or "0/1")
    numerator, _, denominator = rate.partition("/")
    try:
        fps = round(float(numerator) / float(denominator or 1), 3)
    except (ValueError, ZeroDivisionError):
        fps = None
    return {
        "duration_ms": round(float(duration) * 1000) if duration else None,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "has_audio": bool(audio),
        "video_codec": video.get("codec_name"),
    }


def ingest_asset(asset_path: str | Path, artifact_dir: str | Path, transcriber: Transcriber | None = None, *, asset: dict[str, Any] | None = None) -> dict[str, Any]:
    source = Path(asset_path).resolve()
    artifacts = Path(artifact_dir).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    probe_result = run_command(ffprobe_command(source).argv)
    probe = json.loads(probe_result.stdout)
    proxy = artifacts / "proxy.mp4"
    run_command(proxy_command(source, proxy).argv)
    audio = artifacts / "audio.wav"
    run_command(audio_extract_command(source, audio).argv)
    thumbnail_pattern = artifacts / "thumbnails" / "%05d.jpg"
    thumbnail_pattern.parent.mkdir(parents=True, exist_ok=True)
    run_command(thumbnail_command(source, thumbnail_pattern).argv)
    transcript = []
    if transcriber:
        transcript = [word.__dict__ for word in transcriber.transcribe(str(source))]
    (artifacts / "probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    (artifacts / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    # The manifest is what the agent's list_assets/describe_asset tools read.
    manifest = {
        **(asset or {}),
        "id": (asset or {}).get("id", artifacts.name),
        "path": str(source),
        "proxy_path": str(proxy),
        "audio_path": str(audio),
        "probe": summarize_probe(probe),
    }
    (artifacts / "asset.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return {"probe": probe, "manifest": manifest, "proxy": str(proxy), "audio": str(audio), "thumbnails": str(thumbnail_pattern.parent), "transcript": transcript, "scenes": []}
