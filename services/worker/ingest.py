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


def ingest_asset(asset_path: str | Path, artifact_dir: str | Path, transcriber: Transcriber | None = None) -> dict[str, Any]:
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
    return {"probe": probe, "proxy": str(proxy), "audio": str(audio), "thumbnails": str(thumbnail_pattern.parent), "transcript": transcript, "scenes": []}
