"""Per-style notes shared by every project: what an agent learned using a style.

Most of a full agent run's cost is discovery: reading the skill, trying its
scripts, hitting the same pitfalls. The first run in a style writes down the
commands that worked and the fixes it needed; later runs, on any video, start
from those notes. They live in ``<PROJECTS_ROOT>/_style_notes/<skill>.md`` and
are copied in and out of the project's ``.agent-context`` around each run.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

MAX_BYTES = 16_000


def _shared(projects_root: Path, skill: str) -> Path:
    return projects_root / "_style_notes" / f"{re.sub(r'[^A-Za-z0-9._-]', '_', skill)}.md"


def _local(project: Path, skill: str) -> Path:
    return project / ".agent-context" / "style-notes" / _shared(Path("."), skill).name


def prepare(project: Path, skill: str | None) -> str:
    """Copy the shared notes in; returns the prompt section for the agent."""

    if not skill:
        return ""
    shared, local = _shared(project.parent, skill), _local(project, skill)
    local.parent.mkdir(parents=True, exist_ok=True)
    if shared.is_file():
        shutil.copyfile(shared, local)
        lead = f"Notes from earlier edits in `{skill}` are in `{local.relative_to(project).as_posix()}`: read them first and skip re-discovering what they cover."
    else:
        lead = f"This is the first edit in `{skill}`."
    return (
        f"## Style notes\n\n{lead} When the edit is done, update that file (under 60 lines, no details of this video): "
        "the exact commands and order that worked, where files go, pitfalls you hit and their fixes, and anything you would do differently."
    )


def publish(project: Path, skill: str | None) -> bool:
    """Share the run's updated notes with every future project."""

    if not skill:
        return False
    local, shared = _local(project, skill), _shared(project.parent, skill)
    if not local.is_file() or not 0 < local.stat().st_size <= MAX_BYTES:
        return False
    if shared.is_file() and shared.read_bytes() == local.read_bytes():
        return False
    shared.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(local, shared)
    return True
