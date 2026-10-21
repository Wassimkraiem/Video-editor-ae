"""A trailer (short preview video) and a cover image per style, shown in the style pickers.

Stored in ``<PROJECTS_ROOT>/_skill_previews/<style>/{preview.mp4,cover.jpg}``. A preview comes
from one of the user's own videos in that style (set by hand, or the first one made), or from a
demo the user asks to generate.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

PREVIEWS_DIR = "_skill_previews"
PREVIEW_FILES = ("preview.mp4", "cover.jpg")
# Trailers are for browsing: short and light so the picker loads fast.
MAX_SECONDS = 20
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

DEMO_BRIEF = """Make a short demo of this style for its preview in a style picker (about 12-18 seconds, 9:16).
Subject: "Pulse", an imaginary habit-tracker app. Its promise: "Build habits that stick". Three
features: daily streaks, smart reminders, a weekly progress chart. Price: free, Pro 4.99/month.
CTA: "Download Pulse". Show off what makes this style recognisable in the first seconds."""


def preview_dir(projects_root: Path, name: str) -> Path:
    if not NAME.match(name):
        raise ValueError("bad style name")
    return projects_root / PREVIEWS_DIR / name


def has_preview(projects_root: Path, name: str) -> bool:
    return (preview_dir(projects_root, name) / "preview.mp4").is_file()


def _duration(path: Path) -> float:
    completed = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return float(json.loads(completed.stdout)["format"].get("duration") or 0)


def install_preview(projects_root: Path, name: str, video: Path) -> Path:
    """Make ``video`` the style's trailer: a light 720-wide cut of its first seconds + a cover frame."""

    folder = preview_dir(projects_root, name)
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    seconds = min(_duration(video) or MAX_SECONDS, MAX_SECONDS)
    trailer = folder / "preview.tmp.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(video), "-t", f"{seconds:.2f}", "-vf", "scale='min(720,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(trailer)], check=True, capture_output=True)
    trailer.replace(folder / "preview.mp4")
    # A frame a third of the way in shows the style better than the first frame.
    subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{seconds / 3:.2f}", "-i", str(folder / "preview.mp4"), "-frames:v", "1", "-q:v", "4", str(folder / "cover.jpg")], check=True, capture_output=True)
    return folder
