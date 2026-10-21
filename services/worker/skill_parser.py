"""Safe SKILL.md parser and validator."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SkillFrontmatter(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class SkillPackage(BaseModel):
    frontmatter: SkillFrontmatter
    body: str
    checksum: str
    has_scripts: bool


PLAIN_FIELD = re.compile(r"^([A-Za-z_][\w-]*):[ \t]+(.*?)[ \t]*$")


def repair_frontmatter(text: str) -> str:
    """Quote plain one-line values that YAML rejects.

    Agents write descriptions like ``description: Captions: small white text``;
    the second ": " makes YAML read a nested mapping and fail. Valid
    frontmatter comes back unchanged.
    """

    try:
        yaml.safe_load(text)
        return text
    except yaml.YAMLError:
        pass
    lines = []
    for line in text.split("\n"):
        match = PLAIN_FIELD.match(line)
        value = match.group(2) if match else ""
        if match and value and value[0] not in "'\"|>[{&*!#" and (": " in value or " #" in value or value.endswith(":")):
            line = f"{match.group(1)}: {json.dumps(value, ensure_ascii=False)}"
        lines.append(line)
    return "\n".join(lines)


def split_skill(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        raise ValueError("SKILL.md requires YAML frontmatter")
    _, frontmatter_text, body = text.split("---", 2)
    return frontmatter_text, body


def repair_skill_file(path: Path) -> bool:
    """Rewrite SKILL.md with repaired frontmatter; True when it changed.

    Claude Code reads the same frontmatter when it loads the skill, so the
    fix has to land in the file, not only in our parse.
    """

    text = path.read_text(encoding="utf-8")
    frontmatter_text, body = split_skill(text)
    repaired = repair_frontmatter(frontmatter_text)
    if repaired == frontmatter_text:
        return False
    path.write_text(f"---{repaired}---{body}", encoding="utf-8")
    return True


def parse_skill(path: str | Path) -> SkillPackage:
    source = Path(path).resolve()
    if source.name != "SKILL.md":
        raise ValueError("Skill entrypoint must be SKILL.md")
    text = source.read_text(encoding="utf-8")
    frontmatter_text, body = split_skill(text)
    try:
        loaded = yaml.safe_load(repair_frontmatter(frontmatter_text))
    except yaml.YAMLError as exc:
        raise ValueError(f"SKILL.md frontmatter is not valid YAML: {exc}") from exc
    frontmatter = SkillFrontmatter.model_validate(loaded or {})
    return SkillPackage(frontmatter=frontmatter, body=body.strip(), checksum=hashlib.sha256(text.encode()).hexdigest(), has_scripts=(source.parent / "scripts").is_dir())


def validate_skill_archive(archive: str | Path, max_bytes: int = 20 * 1024 * 1024) -> SkillPackage:
    source = Path(archive).resolve()
    if source.stat().st_size > max_bytes:
        raise ValueError("Skill archive is too large")
    with zipfile.ZipFile(source) as bundle:
        for info in bundle.infolist():
            name = Path(info.filename)
            if name.is_absolute() or ".." in name.parts or info.is_dir() and name.parts[-1] == "":
                raise ValueError("Skill archive contains an unsafe path")
            # Unix symlinks can escape the extraction root even when their
            # filename itself is harmless.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Skill archive cannot contain symlinks")
            if info.file_size > max_bytes:
                raise ValueError("Skill file is too large")
        if "SKILL.md" not in bundle.namelist():
            candidates = [item for item in bundle.namelist() if item.endswith("/SKILL.md")]
            if len(candidates) != 1:
                raise ValueError("Skill archive must contain exactly one SKILL.md")
            entry = candidates[0]
        else:
            entry = "SKILL.md"
        text = bundle.read(entry).decode("utf-8")
    temporary_dir = source.parent / f".{source.stem}-skill"
    temporary_dir.mkdir(exist_ok=True)
    temporary = temporary_dir / "SKILL.md"
    temporary.write_text(text, encoding="utf-8")
    try:
        return parse_skill(temporary)
    finally:
        temporary.unlink(missing_ok=True)
        temporary_dir.rmdir()
