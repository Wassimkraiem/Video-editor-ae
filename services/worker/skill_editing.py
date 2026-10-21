"""Change an existing style with Claude: the user describes the change, an agent edits a copy.

The agent works on ``<workspace>/skill-out/<target>`` (a copy of the source
skill) inside ``_styles/<job id>``, so a failed or bad edit never touches the
installed style. On success the copy is validated and installed like a clone;
the version it replaces is kept under ``_skill_versions/<name>/`` first, and
``restore_previous`` puts it back.

Built-in styles are never edited in place: the result is saved under a new
name, so a repo update can't silently undo the user's changes and theirs
can't break the house style.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .project_bootstrap import SKILLS_ROOT, SKILL_SOURCES
from .style_extraction import user_skills_root

VERSIONS_DIR = "_skill_versions"
_IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", ".skill-fingerprint")

EDIT_BRIEF = """You are changing the video style skill `{target}` at `skill-out/{target}/` (your working copy of `{source}`).

## The change the user wants
{request}

## How to work
1. Read `skill-out/{target}/SKILL.md` and everything it points to (`references/`, `fast.json`, the scripts it runs) until you know where the requested behaviour lives.
2. Make the change with the smallest edit that does it: adjust the style guide values, the planner rules in SKILL.md, or the script code. Keep every command, file name and JSON field the pipeline relies on, and keep the rest of the look as it is.
3. Keep the frontmatter `name: {target}`. Update the `description` only if the look changed in a way it describes; keep it on one line and put it in double quotes.
4. Check your work: run `python -m py_compile` on every Python script you changed, and if the skill has a lint/check script for compositions, make sure your change still passes it. You have no footage to render; don't try to.
5. Finish with a short summary for the user: what you changed, in which files, and anything you could not do.

Work only inside `skill-out/{target}/`. Do not create a new skill or rename the folder.
"""


def skill_source_dir(name: str, projects_root: Path) -> Path | None:
    """Where a style lives: the user's clones first, then the built-in folders."""

    for root in (user_skills_root(projects_root), *(SKILLS_ROOT / source for source in SKILL_SOURCES)):
        candidate = root / name
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def is_builtin(name: str) -> bool:
    return any((SKILLS_ROOT / source / name / "SKILL.md").is_file() for source in SKILL_SOURCES)


def rename_frontmatter(skill_md: Path, name: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    renamed = re.sub(r"(?m)^name:[ \t]*.*$", f"name: {name}", text, count=1)
    skill_md.write_text(renamed, encoding="utf-8")


def prepare_edit(workspace: Path, source: Path, target: str) -> Path:
    """Copy the source skill into the job workspace as ``skill-out/<target>``."""

    copy = workspace / "skill-out" / target
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(source, copy, ignore=_IGNORED)
    if source.name != target:
        rename_frontmatter(copy / "SKILL.md", target)
    return copy


def backup_installed(projects_root: Path, name: str) -> Path | None:
    """Keep the installed version of a user style before it is replaced."""

    current = user_skills_root(projects_root) / name
    if not (current / "SKILL.md").is_file():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = projects_root / VERSIONS_DIR / name / stamp
    shutil.copytree(current, target, ignore=_IGNORED)
    return target


def versions(projects_root: Path, name: str) -> list[Path]:
    folder = projects_root / VERSIONS_DIR / name
    return sorted((path for path in folder.iterdir() if (path / "SKILL.md").is_file()), reverse=True) if folder.is_dir() else []


def restore_previous(projects_root: Path, name: str) -> Path:
    """Put the latest saved version back; it leaves the version list."""

    saved = versions(projects_root, name)
    if not saved:
        raise FileNotFoundError(f"No earlier version of {name} to restore")
    target = user_skills_root(projects_root) / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(saved[0], target)
    shutil.rmtree(saved[0])
    return target
