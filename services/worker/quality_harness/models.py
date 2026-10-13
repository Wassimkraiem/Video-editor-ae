"""Small, serialisable models shared by the quality gates.

These models deliberately describe the contract between the worker and the
quality layer. Media work remains in the worker and the SDK remains the owner
of the agent tool loop.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = ""
    colors: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    tone: str = ""
    target_platforms: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    standing_instructions: list[str] = Field(default_factory=list)


class TimelineSpec(BaseModel):
    """Expected output properties captured at render request time."""

    duration_ms: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    loudness_lufs: float = -14.0
    loudness_tolerance_lufs: float = Field(default=1.0, ge=0)
    duration_tolerance_ms: int = Field(default=40, ge=0)
    fps_tolerance: float = Field(default=0.01, ge=0)


class RenderProbe(BaseModel):
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    loudness_lufs: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class VerificationIssue(BaseModel):
    field: str
    expected: Any
    actual: Any
    message: str


class VerificationReport(BaseModel):
    ok: bool
    render_path: str
    expected: TimelineSpec
    observed: RenderProbe
    issues: list[VerificationIssue] = Field(default_factory=list)


class HookResult(BaseModel):
    ok: bool
    hook: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StoryScene(BaseModel):
    id: str
    title: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    assets: list[str] = Field(default_factory=list)
    template: str = ""
    notes: str = ""


class Storyboard(BaseModel):
    project_id: str
    brief: str
    scenes: list[StoryScene] = Field(min_length=1)
    status: str = "awaiting_approval"
    approved_by: str | None = None


class ReviewInput(BaseModel):
    """The only context a blind reviewer is allowed to receive."""

    original_brief: str
    timeline: dict[str, Any]
    frame_extracts: list[str] = Field(default_factory=list)
    verification_report: VerificationReport


class ReviewResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    cycle: int


class RunStatus(StrEnum):
    PLANNING = "planning"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EDITING = "editing"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
