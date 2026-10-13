"""Create the isolated project workspace used by worker agent sessions."""

from __future__ import annotations

import shutil
from pathlib import Path

from packages.timeline_schema import Timeline

from .quality_harness.models import ProjectProfile
from .quality_harness.project_memory import create_project_memory


SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"
# builtin: small generic recipes. library: the house styles (wassim-style,
# devin-style, ...) and the hyperframes / media-use skills they call.
SKILL_SOURCES = ("builtin", "library")
_IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "node_modules", ".DS_Store")


def install_skills(destination: Path, sources: list[Path]) -> list[str]:
    """Copy skill folders into a project's ``.claude/skills``.

    A skill already present is refreshed only when its SKILL.md changed, so
    edits shipped in the repo reach existing projects on their next run.
    """

    installed: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.is_dir():
            continue
        for skill in sorted(source.iterdir()):
            entry = skill / "SKILL.md"
            if not entry.is_file():
                continue
            target = destination / skill.name
            current = target / "SKILL.md"
            if current.is_file() and current.read_bytes() == entry.read_bytes():
                continue
            shutil.copytree(skill, target, dirs_exist_ok=True, ignore=_IGNORED)
            installed.append(skill.name)
    return installed


def bootstrap_project(project_dir: str | Path, profile: ProjectProfile | None = None, *, builtin_skills_root: str | Path | None = None) -> Path:
    root = Path(project_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ("raw", "proxies", "renders", "compositions", ".agent-context", ".claude/skills"):
        (root / name).mkdir(parents=True, exist_ok=True)
    create_project_memory(root, profile)
    timeline = root / "timeline.json"
    if not timeline.exists():
        timeline.write_text(Timeline(fps=30, width=1920, height=1080, duration_ms=1000).model_dump_json(indent=2) + "\n", encoding="utf-8")
    sources = [Path(builtin_skills_root).resolve()] if builtin_skills_root else [SKILLS_ROOT / name for name in SKILL_SOURCES]
    install_skills(root / ".claude" / "skills", sources)
    return root
