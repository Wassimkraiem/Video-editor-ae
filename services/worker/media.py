"""Typed FFmpeg/ffprobe command builders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class FFmpegCommand:
    argv: tuple[str, ...]


def run_media_command(command: FFmpegCommand) -> subprocess.CompletedProcess[str]:
    """Execute a typed media command without invoking a shell."""

    return subprocess.run(list(command.argv), check=True, capture_output=True, text=True)


def ffprobe_command(path: str | Path) -> FFmpegCommand:
    return FFmpegCommand(("ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(Path(path).resolve())))


def proxy_command(input_path: str | Path, output_path: str | Path) -> FFmpegCommand:
    return FFmpegCommand(("ffmpeg", "-y", "-i", str(Path(input_path).resolve()), "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(Path(output_path).resolve())))


def audio_extract_command(input_path: str | Path, output_path: str | Path) -> FFmpegCommand:
    return FFmpegCommand(("ffmpeg", "-y", "-i", str(Path(input_path).resolve()), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(Path(output_path).resolve())))


def thumbnail_command(input_path: str | Path, output_pattern: str | Path, *, fps: float = 1 / 5) -> FFmpegCommand:
    if fps <= 0:
        raise ValueError("Thumbnail fps must be positive")
    return FFmpegCommand(("ffmpeg", "-y", "-i", str(Path(input_path).resolve()), "-vf", f"fps={fps:g},scale=640:-2", str(Path(output_pattern).resolve())))


def loudness_normalize_command(input_path: str | Path, output_path: str | Path) -> FFmpegCommand:
    return FFmpegCommand(("ffmpeg", "-y", "-i", str(Path(input_path).resolve()), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy", str(Path(output_path).resolve())))


def render_timeline_command(timeline_path: str | Path, output_path: str | Path, *, fps: int, width: int, height: int) -> FFmpegCommand:
    return FFmpegCommand(("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(Path(timeline_path).resolve()), "-r", str(fps), "-vf", f"scale={width}:{height}", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-c:a", "aac", str(Path(output_path).resolve())))
