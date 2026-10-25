from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    thumbnail_url: str | None = None
    # "clip": footage to edit (transcribed). "resource": an image, logo, sound
    # or b-roll the user attaches to an edit request (never transcribed).
    role: str = "clip"
    transcript_status: str | None = None
    transcript_language: str | None = None
    transcript_reviewed: bool = False
    created_at: datetime


class TranscriptWordIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    text: str = Field(max_length=200)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    segment: int = Field(default=0, ge=0)


class TranscriptResponse(BaseModel):
    asset_id: str
    words: list[dict[str, Any]] = Field(default_factory=list)
    language: str | None = None
    reviewed: bool = False
    status: str | None = None


class TranscriptUpdate(BaseModel):
    words: list[TranscriptWordIn] = Field(max_length=50_000)
    language: str | None = Field(default=None, max_length=12)


class ScriptAlign(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


class TranscribeRequest(BaseModel):
    # "tn" (Tunisian: Darija + French + English, the default), an ISO code
    # such as "ar", "fr", "en", or "auto" to let Whisper detect it.
    language: str | None = Field(default=None, max_length=12, pattern=r"^([a-z]{2,3}|auto)$")
    # Names and terms to spell the speaker's way (brands, tools, people).
    vocabulary: str = Field(default="", max_length=1000)


class AssetURLResponse(BaseModel):
    url: str
    expires_in: int


class BrandKit(BaseModel):
    colors: list[str] = Field(default_factory=list, max_length=6)
    fonts: list[str] = Field(default_factory=list, max_length=3)
    notes: str = Field(default="", max_length=1000)

    @field_validator("colors")
    @classmethod
    def _hex(cls, colors: list[str]) -> list[str]:
        for color in colors:
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise ValueError(f"Not a #RRGGBB colour: {color}")
        return [color.upper() for color in colors]

    @field_validator("fonts")
    @classmethod
    def _fonts(cls, fonts: list[str]) -> list[str]:
        cleaned = [font.strip() for font in fonts if font.strip()]
        if any(len(font) > 60 or not re.fullmatch(r"[A-Za-z0-9 .'-]+", font) for font in cleaned):
            raise ValueError("Font names may use letters, digits, spaces, dots, apostrophes and dashes")
        return cleaned


class RunCreate(BaseModel):
    brief: str = Field(min_length=1)
    scene_count: int = Field(default=1, ge=1, le=24)
    motion_graphics: bool = False
    # Optional skill (e.g. "wassim-style") the agent is told to invoke.
    skill: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9][a-z0-9:_-]*$")
    # Another style whose captions replace the main style's ("captions from X, motion from Y").
    caption_skill: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9][a-z0-9:_-]*$")
    # Colours, fonts and notes every style (and auto-style) follows.
    brand: BrandKit | None = None
    # "fast": one planning call + the style's scripts (cents). "agent": the
    # full Claude Code agent (dollars) for requests the engine can't express.
    mode: Literal["fast", "agent"] = "fast"
    asset_id: str | None = Field(default=None, max_length=64)
    # Fast mode only: skip the speaker cut-out (no head pop-out, much quicker).
    quick: bool = False
    # Resource asset ids (images, logos, sounds) to use in this edit.
    resources: list[str] = Field(default_factory=list, max_length=20)
    # "people": footage of someone talking or selling; "motion" / "product":
    # no footage, every scene is built.
    kind: Literal["people", "motion", "product"] = "people"
    # How much editing every style applies; minimal suits ads and talking heads.
    intensity: Literal["minimal", "balanced", "bold"] | None = None
    # Clips in the order the user wants them; more than one (or cut) joins
    # them into one clip first, with bad takes and pauses cut out when cut.
    clips: list[str] = Field(default_factory=list, max_length=12)
    cut: bool = False
    # The words to show (motion/product) or the script the speaker read.
    script: str | None = Field(default=None, max_length=20_000)


class RunResponse(BaseModel):
    id: str
    project_id: str
    status: str
    brief: str
    skill: str | None = None
    mode: str = "agent"
    sdk_session_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    # Set on After Effects exports once the zip is ready (a signed download link).
    export_url: str | None = None
    # The composition an After Effects export rebuilds.
    ae_export: str | None = None


class AeExportCreate(BaseModel):
    composition: str = Field(max_length=300, pattern=r"^compositions/[A-Za-z0-9._-]+$")


class UserMessage(BaseModel):
    answer: str = Field(min_length=1, max_length=20_000)
    resources: list[str] = Field(default_factory=list, max_length=20)


class MemoryUpdate(BaseModel):
    content: str = Field(max_length=200_000)


class RenderCreate(BaseModel):
    preset: Literal["preview", "1080p30", "1080p60", "4K", "9:16", "1:1"] = "preview"
    composition: str | None = Field(default=None, max_length=300, pattern=r"^compositions/[A-Za-z0-9._-]+$")
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
    # The HyperFrames reel it was rendered from (opens in Studio).
    composition: str | None = None
    skill: str | None = None
    title: str | None = None
    # The run (chat) that made it, so the edit page shows only its own video.
    run_id: str | None = None
    # Set for videos exported from the manual editor (reopens there).
    edit_id: str | None = None


class ManualEditCreate(BaseModel):
    name: str = Field(default="Untitled edit", max_length=120)
    asset_ids: list[str] = Field(min_length=1, max_length=50)


class StudioOpen(BaseModel):
    composition: str | None = Field(default=None, max_length=300, pattern=r"^compositions/[A-Za-z0-9._-]+$")


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
    # Every style runs as a cheap fast edit: "style" = its own engine
    # (fast.json), "generic" = one call writes the whole composition.
    fast: bool = False
    fast_engine: str | None = None
    # Signed links to the style's trailer and cover image, when it has them.
    preview_url: str | None = None
    cover_url: str | None = None


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
    # One or more entries; each may hold several URLs separated by commas.
    urls: list[str] = Field(min_length=1, max_length=10)
    name: str = Field(min_length=2, max_length=63)
    notes: str = Field(default="", max_length=4000)
    # A house style to fork ("wassim-style", ...); empty lets the agent pick.
    base: str | None = Field(default=None, max_length=63)


class SkillPreviewFromOutput(BaseModel):
    project_id: str = Field(max_length=64)
    # A finished video of that project, as listed by /outputs ("renders/x.mp4").
    path: str = Field(max_length=400)


class SkillEditCreate(BaseModel):
    skill: str = Field(min_length=2, max_length=63)
    request: str = Field(min_length=3, max_length=4000)
    # Save the result under a new name; required when editing a built-in style.
    save_as: str | None = Field(default=None, max_length=63)


class StyleExtractionResponse(BaseModel):
    id: str
    status: str
    urls: list[str]
    # "clone" (from reference videos) or "edit" (a change to an existing style).
    kind: str = "clone"
    name: str = ""
    notes: str = ""
    base: str | None = None
    skill_name: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    style_spec: dict[str, Any] | None = None
