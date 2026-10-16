"""Create the isolated project workspace used by worker agent sessions."""

from __future__ import annotations

import hashlib
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


FINGERPRINT = ".skill-fingerprint"
_SKIPPED_PARTS = {"__pycache__", ".git", "node_modules"}


def skill_fingerprint(skill: Path) -> str:
    """Hash every file of a skill so script and asset edits are detected too."""

    digest = hashlib.sha256()
    for path in sorted(item for item in skill.rglob("*") if item.is_file()):
        relative = path.relative_to(skill)
        if _SKIPPED_PARTS & set(relative.parts) or path.suffix == ".pyc" or path.name == FINGERPRINT:
            continue
        digest.update(relative.as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def install_skills(destination: Path, sources: list[Path]) -> list[str]:
    """Copy skill folders into a project's ``.claude/skills``.

    A skill already present is refreshed when any of its files changed, so
    edits shipped in the repo reach existing projects on their next run.
    """

    installed: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.is_dir():
            continue
        for skill in sorted(source.iterdir()):
            if not (skill / "SKILL.md").is_file():
                continue
            target = destination / skill.name
            fingerprint = skill_fingerprint(skill)
            marker = target / FINGERPRINT
            if marker.is_file() and marker.read_text(encoding="utf-8") == fingerprint:
                continue
            shutil.copytree(skill, target, dirs_exist_ok=True, ignore=_IGNORED)
            marker.write_text(fingerprint, encoding="utf-8")
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
    # Styles cloned from reference videos live in <projects root>/_skills;
    # projects and style workspaces sit one or two levels below it.
    user_skills = next((parent / "_skills" for parent in root.parents[:3] if (parent / "_skills").is_dir()), None)
    if user_skills is not None and not builtin_skills_root:
        sources.append(user_skills)
    install_skills(root / ".claude" / "skills", sources)
    return root
