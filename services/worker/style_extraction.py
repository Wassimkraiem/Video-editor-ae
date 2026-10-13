"""Style extraction provider boundary and derived skill writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def validate_user_urls(urls: list[str]) -> list[str]:
    if not urls:
        raise ValueError("At least one URL is required")
    cleaned: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Only credential-free http(s) URLs are accepted")
        host = parsed.hostname.lower()
        if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".local"):
            raise ValueError("Local network URLs are not allowed")
        cleaned.append(url)
    return cleaned


def write_extracted_style_skill(root: str | Path, name: str, style_spec: dict[str, Any]) -> Path:
    target = Path(root).resolve() / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "references").mkdir(exist_ok=True)
    (target / "templates").mkdir(exist_ok=True)
    (target / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Extracted video style skill\n---\n\nApply the derived pacing, typography, color, and motion rules.\n", encoding="utf-8")
    (target / "references" / "style-spec.json").write_text(json.dumps(style_spec, indent=2) + "\n", encoding="utf-8")
    return target
