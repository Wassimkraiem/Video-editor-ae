"""Create the isolated project workspace used by worker agent sessions."""

from __future__ import annotations

import shutil
from pathlib import Path

from packages.timeline_schema import Timeline

from .quality_harness.models import ProjectProfile
from .quality_harness.project_memory import create_project_memory


def bootstrap_project(project_dir: str | Path, profile: ProjectProfile | None = None, *, builtin_skills_root: str | Path | None = None) -> Path:
    root = Path(project_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ("raw", "proxies", "renders", "compositions", ".agent-context", ".claude/skills"):
        (root / name).mkdir(parents=True, exist_ok=True)
    create_project_memory(root, profile)
    timeline = root / "timeline.json"
    if not timeline.exists():
        timeline.write_text(Timeline(fps=30, width=1920, height=1080, duration_ms=1000).model_dump_json(indent=2) + "\n", encoding="utf-8")
    source = Path(builtin_skills_root).resolve() if builtin_skills_root else Path(__file__).resolve().parents[2] / "skills" / "builtin"
    destination = root / ".claude" / "skills"
    if source.is_dir():
        for skill in source.iterdir():
            target = destination / skill.name
            if not target.exists() and skill.is_dir():
                shutil.copytree(skill, target)
    return root
