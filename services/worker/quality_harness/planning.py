"""Plan mode and user approval for multi-scene work."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .models import Storyboard


class PlanGate:
    """Stateful guard used by write/render tools in a planned run."""

    def __init__(self, required: bool = False) -> None:
        self.required = required
        self.approved = not required

    def approve(self) -> None:
        self.approved = True

    def check(self) -> tuple[bool, str]:
        if self.required and not self.approved:
            return False, "Storyboard approval is required before composition or render tools can run"
        return True, "Storyboard gate passed"


def requires_plan(*, scene_count: int = 0, motion_graphics: bool = False, brief: str = "") -> bool:
    text = brief.lower()
    return scene_count > 1 or motion_graphics or any(term in text for term in ("motion graphics", "kinetic typography", "animated title"))


def write_storyboard(project_dir: str | Path, storyboard: Storyboard) -> Path:
    path = Path(project_dir).resolve() / "storyboard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(storyboard.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return path


def request_storyboard_approval(
    storyboard: Storyboard,
    ask_user: Callable[[str, list[str]], str],
) -> Storyboard:
    """Use the SDK ask_user tool before any composition or render is created."""

    answer = ask_user(
        "Approve this storyboard before I create compositions or render?",
        ["Approve", "Revise"],
    )
    if answer != "Approve":
        storyboard.status = "revision_requested"
        return storyboard
    storyboard.status = "approved"
    return storyboard
