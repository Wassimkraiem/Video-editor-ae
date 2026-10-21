"""Remember which reel and style produced each finished video.

The library shows the style on every cover and opens any video's reel in
Studio, so each render is tied to its HyperFrames composition. Agent turns
and render jobs record that link; older videos are matched by time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CATALOG = "renders/.catalog.json"
COMPOSITION_META = ".studio-meta.json"
_SKIPPED = {"node_modules", "assets", "proxies"}


def output_files(project: Path) -> list[Path]:
    """Finished MP4s: not the footage a reel copies in, not renderer scratch."""

    files = []
    for pattern in ("renders/**/*.mp4", "compositions/**/*.mp4"):
        for path in project.glob(pattern):
            parts = path.relative_to(project).parts
            if path.is_file() and not _SKIPPED & set(parts) and not any(part.startswith(("work-", ".")) for part in parts):
                files.append(path)
    return files


def compositions(project: Path) -> list[Path]:
    return [index.parent for index in (project / "compositions").glob("*/index.html") if index.is_file()]


def snapshot(project: Path) -> dict[str, float]:
    state = {path.relative_to(project).as_posix(): path.stat().st_mtime for path in output_files(project)}
    state.update({f"{folder.relative_to(project).as_posix()}/index.html": (folder / "index.html").stat().st_mtime for folder in compositions(project)})
    return state


def read_catalog(project: Path) -> dict[str, dict[str, Any]]:
    try:
        return json.loads((project / CATALOG).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def composition_meta(folder: Path) -> dict[str, Any]:
    try:
        return json.loads((folder / COMPOSITION_META).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def composition_for(project: Path, output: Path, preferred: list[Path] | None = None) -> Path | None:
    """The reel a video came from: its own folder, a reel edited in the same turn, or the latest before it."""

    relative = output.relative_to(project).parts
    if relative[0] == "compositions" and len(relative) > 2:
        return project / "compositions" / relative[1]
    if preferred:
        return max(preferred, key=lambda folder: (folder / "index.html").stat().st_mtime)
    rendered_at = output.stat().st_mtime
    earlier = [folder for folder in compositions(project) if (folder / "index.html").stat().st_mtime <= rendered_at + 5]
    candidates = earlier or compositions(project)
    return max(candidates, key=lambda folder: (folder / "index.html").stat().st_mtime) if candidates else None


# Short names the house styles go by in file names.
STYLE_ALIASES = {"glass": "talking-head-glass-edit", "kinetic": "kinetic-editorial-reel"}


def guess_style(names: list[str], skills: list[str]) -> str | None:
    """The style a video was made in, read from its file or reel name.

    For videos made before outputs were tagged: "protect-your-job-neon-3d-blue.mp4"
    is neon-3d-blue, "protectyourjob-wassim" is wassim-style. The longest
    match wins, so "neon-3d-blue" beats a shorter style hidden inside it.
    """

    text = " ".join(names).lower()
    candidates = {skill: skill for skill in skills} | {skill.removesuffix("-style"): skill for skill in skills if skill.endswith("-style")} | STYLE_ALIASES
    found = [(len(key), skill) for key, skill in candidates.items() if key and key in text and skill in skills]
    return max(found)[1] if found else None


def record_manual(project: Path, output: Path, edit_id: str, title: str, render_id: str) -> None:
    """Tag a video exported from the manual editor, so it reopens there."""

    catalog = read_catalog(project)
    catalog[output.relative_to(project).as_posix()] = {
        "composition": None,
        "skill": "manual",
        "title": title,
        "run_id": None,
        "edit_id": edit_id,
        "render_id": render_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_catalog(project, catalog)


def _write_catalog(project: Path, catalog: dict[str, dict[str, Any]]) -> None:
    path = project / CATALOG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")


def record_turn(project: Path, before: dict[str, float], *, run_id: str, skill: str | None, title: str) -> list[str]:
    """Tag the reels and videos an agent turn created or changed."""

    now = datetime.now(timezone.utc).isoformat()
    after = snapshot(project)
    changed = {path for path, mtime in after.items() if before.get(path) != mtime}
    touched = [project / Path(path).parent for path in changed if path.endswith("/index.html")]
    for folder in touched:
        meta = composition_meta(folder)
        # A follow-up turn keeps the style the reel was first made in.
        meta.update(run_id=run_id, title=meta.get("title") or title, skill=meta.get("skill") or skill, updated_at=now)
        (folder / COMPOSITION_META).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    catalog = read_catalog(project)
    videos = [path for path in changed if path.endswith(".mp4")]
    for relative in videos:
        output = project / relative
        folder = composition_for(project, output, touched)
        meta = composition_meta(folder) if folder else {}
        catalog[relative] = {
            "composition": folder.relative_to(project).as_posix() if folder else None,
            "skill": meta.get("skill") or skill,
            "title": meta.get("title") or title,
            "run_id": run_id,
            "created_at": now,
        }
    if videos:
        _write_catalog(project, catalog)
    return videos


def record_render(project: Path, output: Path, folder: Path | None, render_id: str) -> None:
    """Tag a video rendered from the studio's Render button."""

    meta = composition_meta(folder) if folder else {}
    catalog = read_catalog(project)
    catalog[output.relative_to(project).as_posix()] = {
        "composition": folder.relative_to(project).as_posix() if folder else None,
        "skill": meta.get("skill"),
        "title": meta.get("title"),
        "run_id": meta.get("run_id"),
        "render_id": render_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_catalog(project, catalog)
