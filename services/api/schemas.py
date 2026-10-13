from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)


class UserLogin(UserCreate):
    pass


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workflow: Literal["raw-footage", "motion-graphics", "explainer"] = "raw-footage"
    profile: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    profile: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    workflow: str
    profile: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TimelineVersionCreate(BaseModel):
    ops: list[dict[str, Any]] = Field(default_factory=list)
    timeline: dict[str, Any] | None = None


class TimelineVersionResponse(BaseModel):
    version: int
    parent_version: int | None
    schema_version: str
    data: dict[str, Any]
    diff: list[dict[str, Any]]
    created_at: datetime


class AssetResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    kind: str
    mime_type: str
    size_bytes: int
    storage_key: str
    status: str
    probe: dict[str, Any] | None = None
    created_at: datetime


class TranscriptResponse(BaseModel):
    asset_id: str
    words: list[dict[str, Any]] = Field(default_factory=list)


class AssetURLResponse(BaseModel):
    url: str
    expires_in: int


class RunCreate(BaseModel):
    brief: str = Field(min_length=1)
    scene_count: int = Field(default=1, ge=1, le=24)
    motion_graphics: bool = False
    # Optional skill (e.g. "wassim-style") the agent is told to invoke.
    skill: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9][a-z0-9:_-]*$")


class RunResponse(BaseModel):
    id: str
    project_id: str
    status: str
    brief: str
    skill: str | None = None
    sdk_session_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class UserMessage(BaseModel):
    answer: str = Field(min_length=1, max_length=20_000)


class MemoryUpdate(BaseModel):
    content: str = Field(max_length=200_000)


class RenderCreate(BaseModel):
    preset: Literal["preview", "1080p30", "1080p60", "4K", "9:16", "1:1"] = "preview"
    brief: str | None = None
    frame_extracts: list[str] = Field(default_factory=list)


class RenderResponse(BaseModel):
    id: str
    project_id: str
    preset: str
    status: str
    output_url: str | None = None
    verification: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime


class OutputResponse(BaseModel):
    name: str
    path: str
    size_bytes: int
    modified_at: datetime
    url: str


class DownloadResponse(BaseModel):
    url: str


class CompositionResponse(BaseModel):
    id: str
    project_id: str
    path: str
    duration_ms: int
    status: str


class CompositionFilesResponse(BaseModel):
    files: list[str] = Field(default_factory=list)


class PreviewResponse(BaseModel):
    job_id: str
    status: str
    url: str | None = None


class SkillCreate(BaseModel):
    name: str
    description: str
    scope: Literal["user", "project"] = "user"
    body: str


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    scope: str
    enabled: bool
    scripts_approved: bool
    checksum: str


class ImageCreate(BaseModel):
    prompt: str = Field(min_length=1)
    size: Literal["1024x1024", "1536x1024", "1024x1536"] = "1024x1024"
    transparent_background: bool = False


class GeneratedImageResponse(BaseModel):
    id: str
    project_id: str
    prompt: str
    model: str
    size: str
    cache_key: str
    status: str
    created_at: datetime


class StyleExtractionCreate(BaseModel):
    urls: list[str] = Field(min_length=1)


class StyleExtractionResponse(BaseModel):
    id: str
    status: str
    urls: list[str]
    style_spec: dict[str, Any] | None = None
