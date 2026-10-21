from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import os
import tempfile
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .repository import MemoryRepository, now
from .schemas import (
    ScriptAlign,
    AssetResponse,
    AssetURLResponse,
    CompositionFilesResponse,
    CompositionResponse,
    DownloadResponse,
    GeneratedImageResponse,
    ImageCreate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    PreviewResponse,
    RenderCreate,
    RenderResponse,
    RunCreate,
    RunResponse,
    SkillCreate,
    SkillResponse,
    StyleExtractionCreate,
    StyleExtractionResponse,
    TimelineVersionCreate,
    TimelineVersionResponse,
    TranscriptResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserMessage,
    UserResponse,
    ManualEditCreate,
    SkillEditCreate,
    SkillPreviewFromOutput,
    MemoryUpdate,
    OutputResponse,
    StudioOpen,
    TranscribeRequest,
    TranscriptUpdate,
)
from .security import create_token, current_user_id, hash_password, optional_user_id, verify_password, decode_token
from .storage import LocalStorage, sniff_mime
from .local_worker import LocalJobRunner
from .event_state import record_event, register_user_skill
from .composition_timeline import composition_timeline
from .queue import enqueue_postgres_job
from .persistence import PostgresPersistence
from services.worker.skill_parser import validate_skill_archive
from services.worker.style_extraction import BASE_STYLES, skill_summary, slugify_skill_name, split_urls, validate_user_urls
from .rate_limit import expensive_rate_limit
from services.worker.quality_harness.models import ProjectProfile
from services.worker.fast_edit import fast_engine, skill_supports_fast
from services.worker.catalog import composition_for, composition_meta, guess_style, output_files, read_catalog
from services.worker import manual_edit, skill_editing, skill_previews
from services.worker.alignment import align_script
from services.worker.transcription import write_transcript
from services.worker.project_bootstrap import SKILL_SOURCES, SKILLS_ROOT, bootstrap_project
from services.worker.quality_harness.project_memory import create_project_memory
from services.worker.quality_harness.models import Storyboard, StoryScene
from services.worker.quality_harness.planning import requires_plan, write_storyboard


settings = get_settings()
logger = logging.getLogger("video-editor-api")
repo = MemoryRepository()
database = PostgresPersistence(settings.database_url)
storage = LocalStorage(settings.storage_root, settings.access_token_secret)
# Agent outputs (renders, compositions) live in the project workspace and are
# served through short-lived signed URLs so <video> tags can play them.
project_files = LocalStorage(settings.projects_root, settings.access_token_secret, route="/api/v1/project-files")
# Style trailers and covers; served only through signed links (they play in <video>/<img> tags).
preview_files = LocalStorage(Path(settings.projects_root) / skill_previews.PREVIEWS_DIR, settings.access_token_secret, route="/api/v1/skill-previews")
local_runner: LocalJobRunner | None = None
TERMINAL_EVENTS = {"agent.succeeded", "agent.failed", "run.cancelled", "render.completed", "render.failed"}


def export_agent_environment() -> None:
    """Expose `.env` values the agent subprocess reads from its environment.

    pydantic-settings parses `.env` into ``settings`` only; the Claude Code
    CLI spawned by the in-process worker needs real environment variables.
    """

    for name, value in (("ANTHROPIC_API_KEY", settings.anthropic_api_key), ("CLAUDE_CODE_OAUTH_TOKEN", settings.claude_code_oauth_token), ("AGENT_MODEL", settings.agent_model), ("GROQ_API_KEY", settings.groq_api_key), ("TRANSCRIBER", settings.transcriber)):
        if value and not os.environ.get(name):
            os.environ[name] = value


# Events this API process applied itself before writing them to Postgres;
# the tail skips them so they are not applied twice.
_published_here: set[str] = set()


async def publish_event(stream_id: str, event: dict[str, Any]) -> None:
    """Apply an event now and, with Postgres, add it to the durable log.

    The log is the source of truth for chats, uploads and renders: replaying
    it on startup rebuilds them (see ``apply_event``).
    """

    if not database.enabled:
        record_event(repo, stream_id, event)
        return
    event = json.loads(json.dumps({**event, "eid": str(uuid4())}, default=str))
    _published_here.add(event["eid"])
    record_event(repo, stream_id, event)
    await database.add_job_event(stream_id, event)


async def replay_job_events(after: int = 0) -> int:
    """Apply every logged event after ``after``; returns the last id seen."""

    while rows := await database.job_events_after(after, limit=2000):
        for event_id, stream_id, event in rows:
            after = event_id
            if event.get("eid") in _published_here:
                _published_here.discard(event["eid"])
                continue
            record_event(repo, stream_id, event)
    return after


async def tail_job_events(after: int) -> None:
    """Mirror events that worker containers write to Postgres.

    Workers run in another process, so their progress arrives through the
    ``job_events`` table. Each row is appended to the in-memory SSE stream
    and applied to the asset, run or render it describes.
    """

    while True:
        try:
            last = await replay_job_events(after)
        except Exception:
            logger.exception("job_event_tail_failed")
            await asyncio.sleep(2)
            continue
        if last == after:
            await asyncio.sleep(0.5)
        after = last


@asynccontextmanager
async def lifespan(_: FastAPI):
    global local_runner
    tail: asyncio.Task[None] | None = None
    if database.enabled:
        # Rebuild chats, uploads and renders before serving requests: rows
        # first (older runs predate full-record events), then the event log.
        runs, assets = await database.all_agent_runs_and_assets()
        for record in runs:
            repo.runs.setdefault(record["id"], record)
        for record in assets:
            repo.assets.setdefault(record["id"], record)
        tail = asyncio.create_task(tail_job_events(await replay_job_events()))
    elif settings.local_worker_enabled:
        export_agent_environment()
        local_runner = LocalJobRunner(repo, settings.projects_root, settings.storage_root)
        logger.info("local_worker_enabled projects_root=%s", settings.projects_root)
    try:
        yield
    finally:
        if tail is not None:
            tail.cancel()
        if local_runner is not None:
            await local_runner.shutdown()
            local_runner = None


app = FastAPI(title="AI Video Editing Studio API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "X-CSRF-Token"],
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


def seed_builtin_skills() -> None:
    if repo.skills:
        return
    import yaml

    for scope in SKILL_SOURCES:
        for skill_path in sorted((SKILLS_ROOT / scope).glob("*/SKILL.md")):
            try:
                text = skill_path.read_text(encoding="utf-8")
                metadata = yaml.safe_load(text.split("---", 2)[1]) or {}
                engine = fast_engine(skill_path.parent)
                repo.create_skill(str(metadata["name"]), " ".join(str(metadata["description"]).split()), scope, text, fast=engine is not None, engine=engine)
            except (OSError, KeyError, ValueError, IndexError, yaml.YAMLError):
                logger.exception("builtin_skill_seed_failed", extra={"path": str(skill_path)})


seed_builtin_skills()


def seed_user_skills() -> None:
    """Styles cloned earlier live in <projects root>/_skills."""

    from services.worker.style_extraction import skill_summary, user_skills_root

    root = user_skills_root(Path(settings.projects_root))
    for skill_dir in sorted(root.glob("*/")) if root.is_dir() else []:
        try:
            register_user_skill(repo, skill_summary(skill_dir))
        except (OSError, ValueError):
            logger.exception("user_skill_seed_failed", extra={"path": str(skill_dir)})


seed_user_skills()


@app.exception_handler(HTTPException)
async def problem_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, media_type="application/problem+json", content={"type": "about:blank", "title": "Request failed", "status": exc.status_code, "detail": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_problem_handler(_, exc: RequestValidationError):
    return JSONResponse(status_code=422, media_type="application/problem+json", content={"type": "about:blank", "title": "Validation failed", "status": 422, "detail": json.dumps(exc.errors(), default=str)})


def public_user(user: dict[str, Any]) -> UserResponse:
    return UserResponse(id=user["id"], email=user["email"], created_at=user["created_at"])


def public_project(project: dict[str, Any]) -> ProjectResponse:
    return ProjectResponse(**{key: project[key] for key in ("id", "owner_id", "name", "workflow", "profile", "created_at", "updated_at")})


def set_auth_cookies(response: Response, refresh_token: str) -> None:
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=False, samesite="lax", max_age=settings.refresh_token_ttl_seconds)
    response.set_cookie("csrf_token", secrets.token_urlsafe(24), httponly=False, secure=False, samesite="lax", max_age=settings.refresh_token_ttl_seconds)


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF token required")


def require_project(project_id: str, user_id: str) -> dict[str, Any]:
    try:
        return repo.project_for(project_id, user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


async def require_project_access(project_id: str, user_id: str) -> dict[str, Any]:
    if database.enabled:
        project = await database.project(project_id, user_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project
    return require_project(project_id, user_id)


async def event_stream(request: Request, stream_id: str, last_event_id: str | None):
    """Replay events after ``last_event_id`` and keep tailing new ones.

    The stream stays open (with heartbeats) until the client disconnects, so
    the studio sees agent messages as the worker produces them.
    """

    try:
        after = int(last_event_id or 0)
    except ValueError:
        after = 0
    idle = 0.0
    while True:
        fresh = [event for event in repo.events.get(stream_id, []) if int(event["id"]) > after]
        for event in fresh:
            after = int(event["id"])
            yield f"id: {event['id']}\ndata: {json.dumps(event, default=str)}\n\n"
        if await request.is_disconnected():
            return
        idle = 0.0 if fresh else idle + 0.5
        if idle >= 15:
            idle = 0.0
            yield ": heartbeat\n\n"
        await asyncio.sleep(0.5)


def sse_response(request: Request, stream_id: str, last_event_id: str | None) -> StreamingResponse:
    return StreamingResponse(
        event_stream(request, stream_id, request.headers.get("Last-Event-ID") or last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def project_dir(project_id: str) -> Path:
    root = Path(settings.projects_root).resolve()
    path = (root / project_id).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Project not found")
    return path


async def enqueue_job(job_type: str, payload: dict[str, Any]) -> None:
    """Publish to Postgres when configured, otherwise run in-process."""

    if local_runner is not None:
        local_runner.submit(job_type, payload)
        return
    repo.enqueue_job(job_type, payload)
    try:
        if database.enabled:
            await database.enqueue_job(job_type, payload)
        else:
            await enqueue_postgres_job(settings.database_url, job_type, payload)
    except Exception:  # pragma: no cover - only exercised with an unavailable deployment DB
        logger.exception("job_enqueue_failed", extra={"job_type": job_type})


@app.get("/api/v1/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/v1/readyz")
async def readyz():
    Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    database_state = "memory"
    if settings.database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                database_state = "ready"
            finally:
                await engine.dispose()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
    return {
        "status": "ready",
        "database": database_state,
        "storage": "ready",
        "worker": "local" if local_runner else "queue",
        # The worker reads the key from its environment; the studio uses
        # this to warn before a run that would fail immediately.
        "agent_key_configured": bool(os.getenv("ANTHROPIC_API_KEY") or settings.anthropic_api_key or os.getenv("CLAUDE_CODE_OAUTH_TOKEN") or settings.claude_code_oauth_token),
    }


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate, response: Response):
    try:
        password_hash = hash_password(payload.password)
        user = repo.create_user(payload.email, password_hash)
        if database.enabled:
            persisted = await database.create_user(payload.email, password_hash)
            if persisted is None:
                raise ValueError("Email already registered")
            user = persisted
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    access = create_token(user["id"], "access", settings.access_token_ttl_seconds)
    refresh = create_token(user["id"], "refresh", settings.refresh_token_ttl_seconds)
    set_auth_cookies(response, refresh)
    return TokenResponse(access_token=access)


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(payload: UserLogin, response: Response):
    user = await database.user_by_email(payload.email) if database.enabled else None
    user = user or next((item for item in repo.users.values() if item["email"] == payload.email.lower()), None)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_token(user["id"], "access", settings.access_token_ttl_seconds)
    refresh = create_token(user["id"], "refresh", settings.refresh_token_ttl_seconds)
    set_auth_cookies(response, refresh)
    return TokenResponse(access_token=access)


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response):
    require_csrf(request)
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token required")
    # Signed refresh tokens stay valid across API restarts; only tokens that
    # were rotated or logged out in this process are refused.
    if token in repo.refresh_tokens:
        raise HTTPException(status_code=401, detail="Refresh token has already been rotated")
    user_id = str(decode_token(token, "refresh")["sub"])
    repo.refresh_tokens.add(token)
    access = create_token(user_id, "access", settings.access_token_ttl_seconds)
    rotated = create_token(user_id, "refresh", settings.refresh_token_ttl_seconds)
    set_auth_cookies(response, rotated)
    return TokenResponse(access_token=access)


@app.post("/api/v1/auth/logout", status_code=204)
async def logout(request: Request, response: Response):
    require_csrf(request)
    if token := request.cookies.get("refresh_token"):
        repo.refresh_tokens.add(token)
    response.delete_cookie("refresh_token")
    response.delete_cookie("csrf_token")


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def me(user_id: str = Depends(current_user_id)):
    user = await database.user_by_id(user_id) if database.enabled else None
    user = user or repo.users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return public_user(user)


@app.post("/api/v1/projects", response_model=ProjectResponse, status_code=201)
async def create_project(payload: ProjectCreate, user_id: str = Depends(current_user_id)):
    project = repo.create_project(user_id, payload.name, payload.workflow, payload.profile)
    if database.enabled:
        project = await database.create_project(user_id, payload.name, payload.workflow, payload.profile, project_id=project["id"])
    repo.create_initial_timeline(project["id"])
    if database.enabled:
        await database.save_timeline_version(project["id"], repo.timelines[project["id"]][0], user_id)
    profile = ProjectProfile.model_validate(payload.profile)
    bootstrap_project(Path(settings.projects_root) / project["id"], profile)
    return public_project(project)


@app.get("/api/v1/projects", response_model=list[ProjectResponse])
async def list_projects(user_id: str = Depends(current_user_id)):
    projects = await database.projects(user_id) if database.enabled else [project for project in repo.projects.values() if project["owner_id"] == user_id]
    return [public_project(project) for project in projects]


@app.get("/api/v1/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user_id: str = Depends(current_user_id)):
    return public_project(await require_project_access(project_id, user_id))


@app.patch("/api/v1/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, payload: ProjectUpdate, user_id: str = Depends(current_user_id)):
    project = await require_project_access(project_id, user_id)
    if payload.name is not None:
        project["name"] = payload.name
    if payload.profile is not None:
        project["profile"] = payload.profile
    project["updated_at"] = now()
    if database.enabled:
        project = await database.update_project(project_id, {key: value for key, value in (("name", payload.name), ("profile", payload.profile)) if value is not None}) or project
    return public_project(project)


@app.delete("/api/v1/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    repo.projects.pop(project_id, None)


@app.get("/api/v1/projects/{project_id}/timeline/versions", response_model=list[TimelineVersionResponse])
async def timeline_versions(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    repo.timelines.setdefault(project_id, [])
    repo.create_initial_timeline(project_id)
    return repo.timelines[project_id]


@app.get("/api/v1/projects/{project_id}/studio")
async def studio_state(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    return repo.studios.get(project_id) or {"status": "closed"}


@app.post("/api/v1/projects/{project_id}/studio", status_code=202)
async def open_studio(project_id: str, payload: StudioOpen | None = None, user_id: str = Depends(current_user_id)):
    """Start HyperFrames Studio, the hand-editing timeline, on a reel (the latest by default)."""

    await require_project_access(project_id, user_id)
    composition = payload.composition if payload else None
    repo.studios[project_id] = {"status": "starting", "composition": composition}
    await enqueue_job("studio_open", {"project_id": project_id, "composition": composition})
    return repo.studios[project_id]


@app.get("/api/v1/projects/{project_id}/timeline/composition")
async def composition_timeline_view(project_id: str, composition: str | None = Query(default=None, max_length=300, pattern=r"^compositions/[A-Za-z0-9._-]+$"), user_id: str = Depends(current_user_id)):
    """A HyperFrames composition (the latest by default) as tracks, or null when there is none."""

    await require_project_access(project_id, user_id)
    return composition_timeline(project_dir(project_id), composition)


@app.post("/api/v1/projects/{project_id}/timeline/versions", response_model=TimelineVersionResponse, status_code=201)
async def create_timeline_version(project_id: str, payload: TimelineVersionCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    try:
        record = repo.apply_version(project_id, payload.ops, payload.timeline)
        if database.enabled:
            await database.save_timeline_version(project_id, record, user_id)
        return record
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/projects/{project_id}/timeline/versions/{version}/restore", response_model=TimelineVersionResponse)
async def restore_timeline_version(project_id: str, version: int, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    versions = repo.timelines.get(project_id, [])
    selected = next((item for item in versions if item["version"] == version), None)
    if not selected:
        raise HTTPException(status_code=404, detail="Timeline version not found")
    record = {**selected, "version": len(versions) + 1, "parent_version": versions[-1]["version"], "created_at": now(), "diff": [{"op": "restore", "from_version": version}]}
    versions.append(record)
    if database.enabled:
        await database.save_timeline_version(project_id, record, user_id)
    return record


@app.post("/api/v1/projects/{project_id}/assets", response_model=AssetResponse, status_code=201, dependencies=[Depends(expensive_rate_limit)])
async def upload_asset(project_id: str, file: UploadFile = File(...), role: str = Form("clip"), user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    if role not in {"clip", "resource"}:
        raise HTTPException(status_code=422, detail="role must be clip or resource")
    try:
        sample = file.file.read(4096)
        file.file.seek(0)
        mime_type = sniff_mime(file.filename or "upload", file.content_type, sample)
        # The folder records the role, so it survives every replay path.
        key = f"projects/{project_id}/{'resources' if role == 'resource' else 'raw'}/{uuid4()}-{Path(file.filename or 'upload').name}"
        size, checksum = storage.put_stream(key, file.file, settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    asset = {"id": str(uuid4()), "project_id": project_id, "filename": Path(file.filename or "upload").name, "kind": mime_type.split("/", 1)[0], "mime_type": mime_type, "size_bytes": size, "storage_key": key, "status": "uploaded", "probe": {"sha256": checksum}, "role": role, "created_at": now()}
    repo.assets[asset["id"]] = asset
    if database.enabled:
        await database.create_asset(asset)
    await enqueue_job("ingest", {"asset_id": asset["id"], "project_id": project_id, "storage_key": key, "filename": asset["filename"], "mime_type": mime_type, "role": role})
    await publish_event(project_id, {"type": "asset.uploaded", "asset_id": asset["id"], "filename": asset["filename"], "record": asset})
    return asset


@app.get("/api/v1/projects/{project_id}/assets", response_model=list[AssetResponse])
async def list_assets(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    assets = [with_thumbnail(asset) for asset in repo.assets.values() if asset["project_id"] == project_id]
    return sorted(assets, key=lambda asset: str(asset["created_at"]), reverse=True)


def asset_role(asset: dict[str, Any]) -> str:
    return "resource" if "/resources/" in str(asset.get("storage_key", "")) else "clip"


def attached_resources(project_id: str, ids: list[str]) -> list[str]:
    """Keep only resource assets of this project, in the order given."""

    return [asset_id for asset_id in dict.fromkeys(ids) if (asset := repo.assets.get(asset_id)) and asset["project_id"] == project_id]


def with_thumbnail(asset: dict[str, Any]) -> dict[str, Any]:
    """Point at the first frame ingest extracted, when there is one."""

    asset = {**asset, "role": asset_role(asset)}
    relative = f"proxies/{asset['id']}/thumbnails/00001.jpg"
    if (project_dir(asset["project_id"]) / relative).is_file():
        return {**asset, "thumbnail_url": project_files.url(f"{asset['project_id']}/{relative}")}
    return asset


async def asset_for(asset_id: str, user_id: str) -> dict[str, Any]:
    asset = repo.assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    await require_project_access(asset["project_id"], user_id)
    return asset


@app.get("/api/v1/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str, user_id: str = Depends(current_user_id)):
    return with_thumbnail(await asset_for(asset_id, user_id))


@app.get("/api/v1/assets/{asset_id}/transcript", response_model=TranscriptResponse)
async def asset_transcript(asset_id: str, user_id: str = Depends(current_user_id)):
    asset = await asset_for(asset_id, user_id)
    folder = project_dir(asset["project_id"]) / "proxies" / asset_id
    try:
        words = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        words = []
    try:
        meta = json.loads((folder / "transcript.meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}
    return {"asset_id": asset_id, "words": words, "language": meta.get("language"), "reviewed": bool(meta.get("reviewed")), "status": asset.get("transcript_status")}


@app.put("/api/v1/assets/{asset_id}/transcript", response_model=TranscriptResponse)
async def save_transcript(asset_id: str, payload: TranscriptUpdate, user_id: str = Depends(current_user_id)):
    """Save the user's corrections; captions and edits use this version."""

    asset = await asset_for(asset_id, user_id)
    words = [word.model_dump() for word in payload.words if word.text.strip()]
    for word in words:
        word["text"] = word["text"].strip()
        if word["end_ms"] < word["start_ms"]:
            raise HTTPException(status_code=422, detail=f"Word {word['id']} ends before it starts")
    words.sort(key=lambda word: (word["start_ms"], word["end_ms"]))
    write_transcript(project_dir(asset["project_id"]) / "proxies" / asset_id, words, language=payload.language or asset.get("transcript_language"), reviewed=True)
    await publish_event(asset["project_id"], {"type": "transcript.edited", "asset_id": asset_id, "language": payload.language})
    return {"asset_id": asset_id, "words": words, "language": payload.language or asset.get("transcript_language"), "reviewed": True, "status": "ready"}


@app.post("/api/v1/assets/{asset_id}/transcript/align", response_model=TranscriptResponse)
async def align_transcript(asset_id: str, payload: ScriptAlign, user_id: str = Depends(current_user_id)):
    """Time the user's own script from the speech; returned for review, not saved."""

    asset = await asset_for(asset_id, user_id)
    folder = project_dir(asset["project_id"]) / "proxies" / asset_id
    try:
        heard = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        heard = []
    if not heard:
        raise HTTPException(status_code=409, detail="This clip has no speech timing yet: wait for the transcription")
    words = align_script(payload.text, heard)
    return {"asset_id": asset_id, "words": words, "language": asset.get("transcript_language"), "reviewed": False, "status": asset.get("transcript_status")}


@app.post("/api/v1/assets/{asset_id}/transcribe", status_code=202)
async def retranscribe(asset_id: str, payload: TranscribeRequest, user_id: str = Depends(current_user_id)):
    """Run Whisper again, for example with the language set explicitly."""

    asset = await asset_for(asset_id, user_id)
    await publish_event(asset["project_id"], {"type": "transcribe.queued", "asset_id": asset_id})
    await enqueue_job("transcribe", {"project_id": asset["project_id"], "asset_id": asset_id, "language": payload.language, "vocabulary": payload.vocabulary})
    return {"status": "transcribing"}


@app.get("/api/v1/assets/{asset_id}/url", response_model=AssetURLResponse)
async def asset_url(asset_id: str, user_id: str = Depends(current_user_id)):
    asset = await asset_for(asset_id, user_id)
    return {"url": storage.url(asset["storage_key"]), "expires_in": 900}


async def serve_signed(backend: LocalStorage, key: str, request: Request, user_id: str | None, project_id: str) -> FileResponse:
    """Serve a file to its project owner, or to anyone holding a valid signature.

    A signed URL is the credential for <video>/<img> tags, which cannot send
    an Authorization header; signatures are only minted for project owners.
    """

    expires = request.query_params.get("expires")
    signature = request.query_params.get("signature")
    if expires is not None or signature is not None:
        try:
            valid = backend.verify(key, int(expires or "0"), signature or "")
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(status_code=403, detail="Media URL has expired or is invalid")
    elif user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    else:
        await require_project_access(project_id, user_id)
    try:
        path = backend.path(key)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Media not found") from exc
    return FileResponse(path)


@app.get("/api/v1/media/{key:path}")
async def media(key: str, request: Request, user_id: str | None = Depends(optional_user_id)):
    parts = Path(key).parts
    if len(parts) < 2 or parts[0] != "projects":
        raise HTTPException(status_code=404, detail="Media not found")
    return await serve_signed(storage, key, request, user_id, parts[1])


@app.get("/api/v1/project-files/{key:path}")
async def project_file(key: str, request: Request, user_id: str | None = Depends(optional_user_id)):
    parts = Path(key).parts
    # Only outputs, compositions and proxies are exposed; never raw/,
    # .claude/ or .agent-context/.
    if len(parts) < 3 or parts[1] not in {"renders", "compositions", "proxies"}:
        raise HTTPException(status_code=404, detail="File not found")
    return await serve_signed(project_files, key, request, user_id, parts[0])


@app.get("/api/v1/projects/{project_id}/outputs", response_model=list[OutputResponse])
async def project_outputs(project_id: str, user_id: str = Depends(current_user_id)):
    """Videos written by the agent or by render jobs, newest first."""

    await require_project_access(project_id, user_id)
    root = project_dir(project_id)
    # Finished videos only: skip the source footage a reel copies into its
    # assets/ and the renderer's scratch folders.
    files = sorted(output_files(root), key=lambda path: path.stat().st_mtime, reverse=True)
    catalog = read_catalog(root)
    runs = sorted((run for run in repo.runs.values() if run["project_id"] == project_id and run.get("skill")), key=lambda run: str(run["created_at"]))
    styles = [skill["name"] for skill in repo.skills.values() if not str(skill["name"]).startswith(("hyperframes", "media-use"))]
    outputs = []
    for path in files[:200]:
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        entry = catalog.get(relative)
        if entry is None:
            # Videos made before the catalog existed: match by time.
            folder = composition_for(root, path)
            meta = composition_meta(folder) if folder else {}
            made_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            run = next((item for item in reversed(runs) if str(item["created_at"]) <= made_at), runs[-1] if runs else None)
            entry = {"composition": folder.relative_to(root).as_posix() if folder else None, "skill": meta.get("skill") or (run or {}).get("skill"), "title": meta.get("title") or (run or {}).get("brief"), "run_id": meta.get("run_id") or (run or {}).get("id")}
            # The time match can pick the wrong reel; a style named in the file wins.
            entry["skill"] = guess_style([path.stem], styles) or entry["skill"]
        elif not entry.get("run_id") and entry.get("composition"):
            # Renders of a reel made before renders were tagged with their run.
            entry = {**entry, "run_id": composition_meta(root / entry["composition"]).get("run_id")}
        if not entry.get("skill"):
            entry = {**entry, "skill": guess_style([path.stem, entry.get("composition") or ""], styles)}
        outputs.append({
            "name": path.name, "path": relative, "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc),
            "url": project_files.url(f"{project_id}/{relative}"),
            "composition": entry.get("composition"), "skill": entry.get("skill"), "title": entry.get("title"), "run_id": entry.get("run_id"), "edit_id": entry.get("edit_id"),
        })
    return outputs


# -- Manual editor: cut, sound, captions and text without the agent -----------


def project_clips(project_id: str, asset_ids: list[str]) -> list[dict[str, Any]]:
    clips = []
    for asset_id in asset_ids:
        asset = repo.assets.get(asset_id)
        if not asset or asset["project_id"] != project_id or asset.get("kind") != "video" or asset.get("role") == "resource":
            raise HTTPException(status_code=422, detail=f"Not a video clip of this project: {asset_id}")
        clips.append(asset)
    return clips


def stored_edit(project_id: str, edit_id: str) -> manual_edit.EditDoc:
    try:
        return manual_edit.load_edit(project_dir(project_id), edit_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Edit not found") from exc


@app.get("/api/v1/projects/{project_id}/edits", response_model=list[manual_edit.EditDoc])
async def list_manual_edits(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    return manual_edit.list_edits(project_dir(project_id))


@app.post("/api/v1/projects/{project_id}/edits", response_model=manual_edit.EditDoc, status_code=201)
async def create_manual_edit(project_id: str, payload: ManualEditCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    project = project_dir(project_id)
    doc = manual_edit.new_edit(payload.name, project_clips(project_id, payload.asset_ids))
    doc.captions = manual_edit.captions_from_words(doc.clips, {clip.asset_id: manual_edit.read_words(project, clip.asset_id) for clip in doc.clips})
    return manual_edit.save_edit(project, doc)


@app.get("/api/v1/projects/{project_id}/edits/{edit_id}", response_model=manual_edit.EditDoc)
async def get_manual_edit(project_id: str, edit_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    return stored_edit(project_id, edit_id)


@app.put("/api/v1/projects/{project_id}/edits/{edit_id}", response_model=manual_edit.EditDoc)
async def save_manual_edit(project_id: str, edit_id: str, payload: manual_edit.EditDoc, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    current = stored_edit(project_id, edit_id)
    project_clips(project_id, sorted({clip.asset_id for clip in payload.clips}))
    doc = payload.model_copy(update={"id": current.id, "created_at": current.created_at})
    return manual_edit.save_edit(project_dir(project_id), doc)


@app.delete("/api/v1/projects/{project_id}/edits/{edit_id}", status_code=204)
async def delete_manual_edit(project_id: str, edit_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    stored_edit(project_id, edit_id)
    shutil.rmtree(manual_edit.edit_dir(project_dir(project_id), edit_id), ignore_errors=True)


@app.post("/api/v1/projects/{project_id}/edits/{edit_id}/captions", response_model=manual_edit.EditDoc)
async def regenerate_captions(project_id: str, edit_id: str, user_id: str = Depends(current_user_id)):
    """Rebuild caption lines from the clips' (reviewed) transcripts and the current cuts."""

    await require_project_access(project_id, user_id)
    project = project_dir(project_id)
    doc = stored_edit(project_id, edit_id)
    doc.captions = manual_edit.captions_from_words(doc.clips, {clip.asset_id: manual_edit.read_words(project, clip.asset_id) for clip in doc.clips})
    return manual_edit.save_edit(project, doc)


@app.post("/api/v1/projects/{project_id}/edits/{edit_id}/render", response_model=RenderResponse, status_code=202)
async def render_manual_edit(project_id: str, edit_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    doc = stored_edit(project_id, edit_id)
    if not doc.clips:
        raise HTTPException(status_code=422, detail="Add at least one clip before exporting")
    clips = project_clips(project_id, sorted({clip.asset_id for clip in doc.clips}))
    render = {"id": str(uuid4()), "project_id": project_id, "preset": "preview", "status": "queued", "output_url": None, "verification": None, "created_at": now()}
    repo.renders[render["id"]] = render
    await publish_event(render["id"], {"type": "render.created", "status": "queued", "record": render})
    await enqueue_job("manual_render", {
        "render_id": render["id"], "project_id": project_id, "edit_id": doc.id,
        "sources": {asset["id"]: asset["storage_key"] for asset in clips},
        "has_audio": {asset["id"]: bool((asset.get("probe") or {}).get("has_audio", True)) for asset in clips},
    })
    return render


@app.get("/api/v1/projects/{project_id}/memory", response_model=MemoryUpdate)
async def get_project_memory(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    path = create_project_memory(project_dir(project_id))
    return {"content": path.read_text(encoding="utf-8")}


@app.put("/api/v1/projects/{project_id}/memory", response_model=MemoryUpdate)
async def put_project_memory(project_id: str, payload: MemoryUpdate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    path = create_project_memory(project_dir(project_id))
    path.write_text(payload.content, encoding="utf-8")
    return {"content": payload.content}


@app.get("/api/v1/projects/{project_id}/storyboard")
async def get_storyboard(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    path = project_dir(project_id) / "storyboard.json"
    # Most projects never plan a storyboard; that is not an error.
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


@app.get("/api/v1/projects/{project_id}/events")
async def project_events(request: Request, project_id: str, user_id: str = Depends(current_user_id), last_event_id: str | None = None):
    await require_project_access(project_id, user_id)
    return sse_response(request, project_id, last_event_id)


def run_prompt(brief: str, skill: str | None) -> str:
    """Point the agent at the chosen style skill without rewriting the brief."""

    if not skill:
        return brief
    return f"Use the `{skill}` skill for this edit: invoke it with the Skill tool and follow it.\n\n{brief}"


@app.post("/api/v1/projects/{project_id}/runs", response_model=RunResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def create_run(project_id: str, payload: RunCreate, user_id: str = Depends(current_user_id), preview_for: str | None = None):
    await require_project_access(project_id, user_id)
    run_id = str(uuid4())
    caption_skill = payload.caption_skill if payload.caption_skill and payload.caption_skill != payload.skill else None
    if caption_skill and not any(skill["name"] == caption_skill for skill in repo.skills.values()):
        raise HTTPException(status_code=422, detail=f"Unknown caption style: {caption_skill}")
    brand = payload.brand.model_dump() if payload.brand else None
    # Fast mode needs a style that ships a fast.json manifest; others use the agent.
    mode = "fast" if payload.mode == "fast" and skill_supports_fast(project_dir(project_id), payload.skill) else "agent"
    clips = [clip for clip in dict.fromkeys(payload.clips) if (asset := repo.assets.get(clip)) and asset["project_id"] == project_id and asset_role(asset) == "clip"] if payload.kind == "people" else []
    asset_id = (clips[0] if clips else payload.asset_id) if payload.kind == "people" else None
    planned = mode == "agent" and requires_plan(scene_count=payload.scene_count, motion_graphics=payload.motion_graphics, brief=payload.brief)
    status_value = "waiting_for_approval" if planned else "queued"
    run = {"id": run_id, "project_id": project_id, "status": status_value, "brief": payload.brief, "skill": payload.skill, "mode": mode, "asset_id": asset_id, "quick": payload.quick, "kind": payload.kind, "intensity": payload.intensity, "clips": clips, "caption_skill": caption_skill, "brand": brand, "sdk_session_id": None, "usage": {}, "created_at": now()}
    repo.runs[run_id] = run
    if database.enabled:
        await database.create_agent_run(run_id, project_id, payload.brief, {"max_turns": 80, "max_budget_usd": 10.0, "wall_clock_timeout_s": 1800})
    await publish_event(run_id, {"type": "run.created", "status": status_value, "brief": payload.brief, "skill": payload.skill, "record": run})
    if planned:
        repo.timelines.setdefault(project_id, [])
        repo.create_initial_timeline(project_id)
        duration = max(1000, int(repo.timelines[project_id][-1]["data"]["duration_ms"] / payload.scene_count))
        storyboard = Storyboard(project_id=project_id, brief=payload.brief, scenes=[StoryScene(id=f"scene-{index + 1}", title=f"Scene {index + 1}", start_ms=index * duration, end_ms=(index + 1) * duration) for index in range(payload.scene_count)])
        write_storyboard(project_dir(project_id), storyboard)
    else:
        await enqueue_job("agent_run", {"run_id": run_id, "project_id": project_id, "brief": run_prompt(payload.brief, payload.skill), "skill": payload.skill, "title": payload.brief, "mode": mode, "asset_id": asset_id, "quick": payload.quick, "prompt": payload.brief if mode == "fast" else None, "resources": attached_resources(project_id, payload.resources),
                                     "kind": payload.kind, "intensity": payload.intensity, "clips": clips, "cut": payload.cut, "script": payload.script, "caption_skill": caption_skill, "brand": brand, "preview_for": preview_for})
    return run


@app.get("/api/v1/projects/{project_id}/runs", response_model=list[RunResponse])
async def list_runs(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    runs = [run for run in repo.runs.values() if run["project_id"] == project_id]
    return sorted(runs, key=lambda run: run["created_at"], reverse=True)


async def set_run_status(run: dict[str, Any], status_value: str) -> None:
    run["status"] = status_value
    if database.enabled:
        await database.update_agent_run(run["id"], {"status": status_value})


async def run_for(run_id: str, user_id: str) -> dict[str, Any]:
    # The in-memory run is kept current by job events; Postgres is the
    # fallback after an API restart.
    run = repo.runs.get(run_id)
    if run is None and database.enabled:
        run = await database.agent_run(run_id, user_id)
        if run is not None:
            repo.runs[run_id] = run
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    await require_project_access(run["project_id"], user_id)
    return run


@app.get("/api/v1/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, user_id: str = Depends(current_user_id)):
    return await run_for(run_id, user_id)


@app.post("/api/v1/runs/{run_id}/messages")
async def answer_run(run_id: str, payload: UserMessage, user_id: str = Depends(current_user_id)):
    run = await run_for(run_id, user_id)
    if run["status"] in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="The agent is still working on this run")
    approving = run["status"] == "waiting_for_approval"
    approved = payload.answer.strip().lower() in {"approve", "approved", "yes"}
    next_status = "revision_requested" if approving and not approved else "queued"
    # The event carries the resulting status so a replay lands on it too.
    resources = attached_resources(run["project_id"], payload.resources)
    await publish_event(run_id, {"type": "user.answer", "answer": payload.answer, "status": next_status, "resources": [repo.assets[item]["filename"] for item in resources]})
    await set_run_status(run, next_status)
    if approving and not approved:
        return {"accepted": True, "status": run["status"]}
    if approving:
        storyboard_path = project_dir(run["project_id"]) / "storyboard.json"
        if storyboard_path.is_file():
            storyboard = Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))
            storyboard.status, storyboard.approved_by = "approved", user_id
            write_storyboard(storyboard_path.parent, storyboard)
        await enqueue_job("agent_run", {"run_id": run_id, "project_id": run["project_id"], "brief": run_prompt(run["brief"], run.get("skill")), "skill": run.get("skill"), "title": run["brief"], "kind": run.get("kind"), "intensity": run.get("intensity"), "caption_skill": run.get("caption_skill"), "brand": run.get("brand")})
        return {"accepted": True, "status": run["status"]}
    # Any other answer is a follow-up turn in the same SDK session, so the
    # agent keeps its context: the plan, the files it read, its questions.
    await enqueue_job("agent_run", {"run_id": run_id, "project_id": run["project_id"], "prompt": payload.answer, "resume": run.get("sdk_session_id"), "skill": run.get("skill"), "title": run["brief"], "mode": run.get("mode", "agent"), "asset_id": run.get("asset_id"), "quick": run.get("quick", False), "resources": resources})
    return {"accepted": True, "status": run["status"]}


@app.post("/api/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user_id: str = Depends(current_user_id)):
    run = await run_for(run_id, user_id)
    if local_runner is not None:
        local_runner.cancel(run_id)
    await set_run_status(run, "cancelled")
    await publish_event(run_id, {"type": "run.cancelled"})
    return run


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(request: Request, run_id: str, user_id: str = Depends(current_user_id), last_event_id: str | None = None):
    await run_for(run_id, user_id)
    return sse_response(request, run_id, last_event_id)


@app.post("/api/v1/projects/{project_id}/renders", response_model=RenderResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def create_render(project_id: str, payload: RenderCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    render = {"id": str(uuid4()), "project_id": project_id, "preset": payload.preset, "status": "queued", "output_url": None, "verification": None, "created_at": now()}
    repo.renders[render["id"]] = render
    await publish_event(render["id"], {"type": "render.created", "status": "queued", "record": render})
    await enqueue_job("render", {"render_id": render["id"], "project_id": project_id, "preset": payload.preset, "brief": payload.brief or "", "frame_extracts": payload.frame_extracts, "composition": payload.composition})
    return render


def public_render(render: dict[str, Any]) -> dict[str, Any]:
    """Mint a fresh signed URL for a finished render on every read."""

    output = render.get("output_path")
    if not output or render["status"] != "succeeded":
        return render
    relative = Path(output).resolve().relative_to(project_dir(render["project_id"])).as_posix()
    return {**render, "output_url": project_files.url(f"{render['project_id']}/{relative}")}


async def render_for(render_id: str, user_id: str) -> dict[str, Any]:
    render = repo.renders.get(render_id)
    if not render:
        raise HTTPException(status_code=404, detail="Render not found")
    await require_project_access(render["project_id"], user_id)
    return public_render(render)


@app.get("/api/v1/projects/{project_id}/renders", response_model=list[RenderResponse])
async def list_renders(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    renders = [public_render(render) for render in repo.renders.values() if render["project_id"] == project_id]
    return sorted(renders, key=lambda render: render["created_at"], reverse=True)


@app.get("/api/v1/renders/{render_id}", response_model=RenderResponse)
async def get_render(render_id: str, user_id: str = Depends(current_user_id)):
    return await render_for(render_id, user_id)


@app.get("/api/v1/renders/{render_id}/events")
async def render_events(request: Request, render_id: str, user_id: str = Depends(current_user_id), last_event_id: str | None = None):
    await render_for(render_id, user_id)
    return sse_response(request, render_id, last_event_id)


@app.get("/api/v1/renders/{render_id}/download", response_model=DownloadResponse)
async def download_render(render_id: str, user_id: str = Depends(current_user_id)):
    render = await render_for(render_id, user_id)
    if not render["output_url"]:
        raise HTTPException(status_code=409, detail="Render is not ready")
    return {"url": render["output_url"]}


@app.get("/api/v1/projects/{project_id}/compositions", response_model=list[CompositionResponse])
async def compositions(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    return [item for item in repo.compositions.values() if item["project_id"] == project_id]


@app.get("/api/v1/compositions/{composition_id}/files", response_model=CompositionFilesResponse)
async def composition_files(composition_id: str, user_id: str = Depends(current_user_id)):
    composition = repo.compositions.get(composition_id)
    if not composition:
        raise HTTPException(status_code=404, detail="Composition not found")
    await require_project_access(composition["project_id"], user_id)
    return {"files": composition.get("files", [])}


@app.post("/api/v1/compositions/{composition_id}/preview", response_model=PreviewResponse)
async def composition_preview(composition_id: str, user_id: str = Depends(current_user_id)):
    composition = repo.compositions.get(composition_id)
    if not composition:
        raise HTTPException(status_code=404, detail="Composition not found")
    await require_project_access(composition["project_id"], user_id)
    job_id = str(uuid4())
    await enqueue_job("composition_preview", {"job_id": job_id, "composition_id": composition_id, "project_id": composition["project_id"]})
    return {"job_id": job_id, "status": "queued", "url": None}


@app.get("/api/v1/skills", response_model=list[SkillResponse])
async def list_skills(user_id: str = Depends(current_user_id)):
    root = Path(settings.projects_root)
    skills = []
    for skill in repo.skills.values():
        folder = root / skill_previews.PREVIEWS_DIR / str(skill["name"])
        links = {f"{stem}_url": preview_files.url(f"{skill['name']}/{file}") for stem, file in (("preview", "preview.mp4"), ("cover", "cover.jpg")) if (folder / file).is_file()}
        skills.append({**skill, **links})
    return skills


@app.get("/api/v1/skill-previews/{name}/{file}")
async def skill_preview_file(name: str, file: str, request: Request):
    if file not in skill_previews.PREVIEW_FILES or not skill_previews.NAME.match(name):
        raise HTTPException(status_code=404, detail="Not found")
    key = f"{name}/{file}"
    try:
        valid = preview_files.verify(key, int(request.query_params.get("expires") or "0"), request.query_params.get("signature") or "")
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(status_code=403, detail="Preview URL has expired or is invalid")
    try:
        return FileResponse(preview_files.path(key))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc


def style_or_404(name: str) -> str:
    if not any(skill["name"] == name for skill in repo.skills.values()) or name.startswith(("hyperframes", "media-use")):
        raise HTTPException(status_code=404, detail="Style not found")
    return name


@app.post("/api/v1/skills/{name}/preview", status_code=202)
async def set_skill_preview(name: str, payload: SkillPreviewFromOutput, user_id: str = Depends(current_user_id)):
    """Use one of the user's finished videos as the style's trailer."""

    style_or_404(name)
    await require_project_access(payload.project_id, user_id)
    root = project_dir(payload.project_id)
    if payload.path not in {path.relative_to(root).as_posix() for path in output_files(root)}:
        raise HTTPException(status_code=404, detail="Video not found")
    await enqueue_job("skill_preview", {"name": name, "project_id": payload.project_id, "path": payload.path})
    return {"status": "queued"}


@app.post("/api/v1/skills/{name}/preview/generate", response_model=RunResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def generate_skill_preview(name: str, user_id: str = Depends(current_user_id)):
    """Make a short demo in the style (one fast edit, uses credits) and keep it as its trailer."""

    style_or_404(name)
    project = next((item for item in repo.projects.values() if item.get("owner_id") == user_id and item.get("name") == PREVIEW_PROJECT), None)
    if project is None:
        created = await create_project(ProjectCreate(name=PREVIEW_PROJECT, workflow="motion-graphics"), user_id=user_id)
        project = created if isinstance(created, dict) else created.model_dump()
    run = await create_run(project["id"], RunCreate(brief=skill_previews.DEMO_BRIEF, skill=name, mode="fast", kind="product", intensity="balanced"), user_id=user_id, preview_for=name)
    return run


PREVIEW_PROJECT = "Style previews"


@app.post("/api/v1/projects/{project_id}/skills/{skill_id}", response_model=SkillResponse)
async def enable_project_skill(project_id: str, skill_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    try:
        return repo.set_project_skill(project_id, skill_id, True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc


@app.delete("/api/v1/projects/{project_id}/skills/{skill_id}", status_code=204)
async def disable_project_skill(project_id: str, skill_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    if skill_id not in repo.skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    repo.project_skills[(project_id, skill_id)] = False


@app.post("/api/v1/skills", response_model=SkillResponse, status_code=201)
async def create_skill(payload: SkillCreate, user_id: str = Depends(current_user_id)):
    return repo.create_skill(payload.name, payload.description, payload.scope, payload.body)


@app.post("/api/v1/skills/upload", response_model=SkillResponse, status_code=201)
async def upload_skill(file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    if not (file.filename or "").endswith(".zip"):
        raise HTTPException(status_code=415, detail="Skills must be uploaded as .zip")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Skill archive exceeds size limit")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temporary:
            temporary.write(data)
            temporary_path = Path(temporary.name)
        package = validate_skill_archive(temporary_path)
    except (OSError, ValueError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid skill archive: {exc}") from exc
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)
    skill = repo.create_skill(package.frontmatter.name, package.frontmatter.description, "user", package.body, fast=True, engine="generic")
    skill["scripts_approved"] = False
    return skill


@app.patch("/api/v1/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: str, enabled: bool, user_id: str = Depends(current_user_id)):
    skill = repo.skills.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill["enabled"] = enabled
    return skill


@app.post("/api/v1/skills/{skill_id}/approve-scripts", response_model=SkillResponse)
async def approve_skill_scripts(skill_id: str, user_id: str = Depends(current_user_id)):
    skill = repo.skills.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill["scripts_approved"] = True
    return skill


@app.get("/api/v1/skills/{skill_id}/files")
async def skill_files(skill_id: str, user_id: str = Depends(current_user_id)):
    skill = repo.skills.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"SKILL.md": skill["body"]}


@app.post("/api/v1/projects/{project_id}/images", response_model=GeneratedImageResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def generate_image(project_id: str, payload: ImageCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    image_id = str(uuid4())
    record = {"id": image_id, "project_id": project_id, "prompt": payload.prompt, "model": "configured-image-model", "size": payload.size, "cache_key": str(hash((payload.prompt, payload.size, payload.transparent_background))), "status": "queued", "created_at": now()}
    repo.images[image_id] = record
    await enqueue_job("generate_image", {"image_id": image_id, "project_id": project_id, "prompt": payload.prompt, "size": payload.size, "transparent_background": payload.transparent_background})
    return record


@app.get("/api/v1/generated-images/{image_id}", response_model=GeneratedImageResponse)
async def generated_image(image_id: str, user_id: str = Depends(current_user_id)):
    record = repo.images.get(image_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generated image not found")
    await require_project_access(record["project_id"], user_id)
    return record


@app.post("/api/v1/style-extractions", response_model=StyleExtractionResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def create_style_extraction(payload: StyleExtractionCreate, user_id: str = Depends(current_user_id)):
    if not settings.style_extraction_enabled:
        raise HTTPException(status_code=403, detail="Style extraction is disabled")
    try:
        urls = validate_user_urls(split_urls(payload.urls))
        name = slugify_skill_name(payload.name)
        if len(urls) > 6:
            raise ValueError("Use at most 6 reference videos")
        if payload.base and payload.base not in BASE_STYLES:
            raise ValueError(f"Unknown base style; choose one of {', '.join(BASE_STYLES)}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if any(skill["name"] == name and skill["scope"] != "user" for skill in repo.skills.values()):
        raise HTTPException(status_code=409, detail=f"{name} is a built-in style; pick another name")
    extraction_id = str(uuid4())
    record = {"id": extraction_id, "status": "queued", "urls": urls, "name": name, "notes": payload.notes, "base": payload.base, "skill_name": None, "error": None, "style_spec": None, "owner_id": user_id, "created_at": now()}
    repo.extractions[extraction_id] = record
    await publish_event(extraction_id, {"type": "style.created", "record": record})
    await enqueue_job("style_extraction", {"extraction_id": extraction_id, "owner_id": user_id, "urls": urls, "name": name, "notes": payload.notes, "base": payload.base})
    return record


@app.post("/api/v1/skill-edits", response_model=StyleExtractionResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def create_skill_edit(payload: SkillEditCreate, user_id: str = Depends(current_user_id)):
    """Ask Claude to change a style; built-in styles are saved under a new name."""

    if not settings.style_extraction_enabled:
        raise HTTPException(status_code=403, detail="Style editing is disabled")
    source = next((skill for skill in repo.skills.values() if skill["name"] == payload.skill and skill.get("enabled", True)), None)
    if source is None or str(payload.skill).startswith(("hyperframes", "media-use")):
        raise HTTPException(status_code=404, detail="Style not found")
    try:
        target = slugify_skill_name(payload.save_as) if payload.save_as and payload.save_as.strip() else payload.skill
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if skill_editing.is_builtin(target):
        raise HTTPException(status_code=409, detail=f"{target} is a built-in style; save your version under a new name")
    if target != payload.skill and any(skill["name"] == target for skill in repo.skills.values()):
        raise HTTPException(status_code=409, detail=f"A style named {target} already exists")
    if any(record.get("kind") == "edit" and record.get("name") == target and record["status"] in ("queued", "analyzing") for record in repo.extractions.values()):
        raise HTTPException(status_code=409, detail=f"{target} is already being edited")
    extraction_id = str(uuid4())
    record = {"id": extraction_id, "kind": "edit", "status": "queued", "urls": [], "name": target, "notes": payload.request, "base": payload.skill, "skill_name": None, "error": None, "style_spec": None, "owner_id": user_id, "created_at": now()}
    repo.extractions[extraction_id] = record
    await publish_event(extraction_id, {"type": "style.created", "record": record})
    await enqueue_job("skill_edit", {"extraction_id": extraction_id, "owner_id": user_id, "source": payload.skill, "name": target, "request": payload.request})
    return record


@app.get("/api/v1/skills/{name}/versions")
async def list_skill_versions(name: str, user_id: str = Depends(current_user_id)):
    return [{"id": path.name, "saved_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)} for path in skill_editing.versions(settings_projects_root(), slugify_or_404(name))]


@app.post("/api/v1/skills/{name}/restore", response_model=SkillResponse)
async def restore_skill_version(name: str, user_id: str = Depends(current_user_id)):
    """Undo the last edit of a style: put the version before it back."""

    name = slugify_or_404(name)
    try:
        target = skill_editing.restore_previous(settings_projects_root(), name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    summary = skill_summary(target)
    await publish_event(f"skill:{name}", {"type": "skill.restored", "skill": summary})
    return next(skill for skill in repo.skills.values() if skill["name"] == name and skill["scope"] == "user")


def slugify_or_404(name: str) -> str:
    try:
        return slugify_skill_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Style not found") from exc


def settings_projects_root() -> Path:
    return Path(settings.projects_root).resolve()


@app.get("/api/v1/style-extractions", response_model=list[StyleExtractionResponse])
async def list_style_extractions(user_id: str = Depends(current_user_id)):
    records = [record for record in repo.extractions.values() if record.get("owner_id") == user_id]
    return sorted(records, key=lambda record: str(record.get("created_at") or ""), reverse=True)


@app.get("/api/v1/style-extractions/{extraction_id}", response_model=StyleExtractionResponse)
async def get_style_extraction(extraction_id: str, user_id: str = Depends(current_user_id)):
    record = repo.extractions.get(extraction_id)
    if not record or record["owner_id"] != user_id:
        raise HTTPException(status_code=404, detail="Style extraction not found")
    return record


@app.get("/api/v1/style-extractions/{extraction_id}/events")
async def style_extraction_events(request: Request, extraction_id: str, user_id: str = Depends(current_user_id), last_event_id: str | None = None):
    record = repo.extractions.get(extraction_id)
    if not record or record["owner_id"] != user_id:
        raise HTTPException(status_code=404, detail="Style extraction not found")
    return sse_response(request, extraction_id, last_event_id)


@app.post("/api/v1/style-extractions/{extraction_id}/approve")
async def approve_style_extraction(extraction_id: str, user_id: str = Depends(current_user_id)):
    record = repo.extractions.get(extraction_id)
    if not record or record["owner_id"] != user_id:
        raise HTTPException(status_code=404, detail="Style extraction not found")
    record["status"] = "approved"
    return record
