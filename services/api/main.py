from __future__ import annotations

import asyncio
import json
import logging
import secrets
import os
import tempfile
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .repository import MemoryRepository, now
from .schemas import (
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
    MemoryUpdate,
    OutputResponse,
)
from .security import create_token, current_user_id, hash_password, optional_user_id, verify_password, decode_token
from .storage import LocalStorage, sniff_mime
from .local_worker import LocalJobRunner
from .event_state import record_event
from .queue import enqueue_postgres_job
from .persistence import PostgresPersistence
from services.worker.skill_parser import validate_skill_archive
from services.worker.style_extraction import validate_user_urls
from .rate_limit import expensive_rate_limit
from services.worker.quality_harness.models import ProjectProfile
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
local_runner: LocalJobRunner | None = None
TERMINAL_EVENTS = {"agent.succeeded", "agent.failed", "run.cancelled", "render.completed", "render.failed"}


def export_agent_environment() -> None:
    """Expose `.env` values the agent subprocess reads from its environment.

    pydantic-settings parses `.env` into ``settings`` only; the Claude Code
    CLI spawned by the in-process worker needs real environment variables.
    """

    for name, value in (("ANTHROPIC_API_KEY", settings.anthropic_api_key), ("CLAUDE_CODE_OAUTH_TOKEN", settings.claude_code_oauth_token), ("AGENT_MODEL", settings.agent_model)):
        if value and not os.environ.get(name):
            os.environ[name] = value


async def tail_job_events() -> None:
    """Mirror events that worker containers write to Postgres.

    Workers run in another process, so their progress arrives through the
    ``job_events`` table. Each row is appended to the in-memory SSE stream
    and applied to the asset, run or render it describes.
    """

    after = await database.latest_job_event_id()
    while True:
        try:
            rows = await database.job_events_after(after)
        except Exception:
            logger.exception("job_event_tail_failed")
            await asyncio.sleep(2)
            continue
        for event_id, stream_id, event in rows:
            after = event_id
            record_event(repo, stream_id, event)
        if not rows:
            await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global local_runner
    tail: asyncio.Task[None] | None = None
    if database.enabled:
        tail = asyncio.create_task(tail_job_events())
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
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
                repo.create_skill(str(metadata["name"]), " ".join(str(metadata["description"]).split()), scope, text)
            except (OSError, KeyError, ValueError, IndexError, yaml.YAMLError):
                logger.exception("builtin_skill_seed_failed", extra={"path": str(skill_path)})


seed_builtin_skills()


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
    repo.refresh_tokens.add(refresh)
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
    repo.refresh_tokens.add(refresh)
    set_auth_cookies(response, refresh)
    return TokenResponse(access_token=access)


@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response):
    require_csrf(request)
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token required")
    if token not in repo.refresh_tokens:
        raise HTTPException(status_code=401, detail="Refresh token has already been rotated")
    user_id = str(decode_token(token, "refresh")["sub"])
    repo.refresh_tokens.remove(token)
    access = create_token(user_id, "access", settings.access_token_ttl_seconds)
    rotated = create_token(user_id, "refresh", settings.refresh_token_ttl_seconds)
    repo.refresh_tokens.add(rotated)
    set_auth_cookies(response, rotated)
    return TokenResponse(access_token=access)


@app.post("/api/v1/auth/logout", status_code=204)
async def logout(request: Request, response: Response):
    require_csrf(request)
    if token := request.cookies.get("refresh_token"):
        repo.refresh_tokens.discard(token)
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
async def upload_asset(project_id: str, file: UploadFile = File(...), user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    try:
        sample = file.file.read(4096)
        file.file.seek(0)
        mime_type = sniff_mime(file.filename or "upload", file.content_type, sample)
        key = f"projects/{project_id}/raw/{uuid4()}-{Path(file.filename or 'upload').name}"
        size, checksum = storage.put_stream(key, file.file, settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    asset = {"id": str(uuid4()), "project_id": project_id, "filename": Path(file.filename or "upload").name, "kind": mime_type.split("/", 1)[0], "mime_type": mime_type, "size_bytes": size, "storage_key": key, "status": "uploaded", "probe": {"sha256": checksum}, "created_at": now()}
    repo.assets[asset["id"]] = asset
    if database.enabled:
        await database.create_asset(asset)
    await enqueue_job("ingest", {"asset_id": asset["id"], "project_id": project_id, "storage_key": key, "filename": asset["filename"], "mime_type": mime_type})
    repo.append_event(project_id, {"type": "asset.uploaded", "asset_id": asset["id"], "filename": asset["filename"]})
    return asset


@app.get("/api/v1/projects/{project_id}/assets", response_model=list[AssetResponse])
async def list_assets(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    assets = [asset for asset in repo.assets.values() if asset["project_id"] == project_id]
    return sorted(assets, key=lambda asset: asset["created_at"], reverse=True)


async def asset_for(asset_id: str, user_id: str) -> dict[str, Any]:
    asset = repo.assets.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    await require_project_access(asset["project_id"], user_id)
    return asset


@app.get("/api/v1/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str, user_id: str = Depends(current_user_id)):
    return await asset_for(asset_id, user_id)


@app.get("/api/v1/assets/{asset_id}/transcript", response_model=TranscriptResponse)
async def asset_transcript(asset_id: str, user_id: str = Depends(current_user_id)):
    asset = await asset_for(asset_id, user_id)
    transcript = project_dir(asset["project_id"]) / "proxies" / asset_id / "transcript.json"
    try:
        words = json.loads(transcript.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        words = []
    return {"asset_id": asset_id, "words": words}


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
    files = [path for pattern in ("renders/**/*.mp4", "compositions/**/*.mp4") for path in root.glob(pattern) if path.is_file() and "node_modules" not in path.parts]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    outputs = []
    for path in files[:50]:
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        outputs.append({"name": path.name, "path": relative, "size_bytes": stat.st_size, "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc), "url": project_files.url(f"{project_id}/{relative}")})
    return outputs


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
async def create_run(project_id: str, payload: RunCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    run_id = str(uuid4())
    planned = requires_plan(scene_count=payload.scene_count, motion_graphics=payload.motion_graphics, brief=payload.brief)
    status_value = "waiting_for_approval" if planned else "queued"
    run = {"id": run_id, "project_id": project_id, "status": status_value, "brief": payload.brief, "skill": payload.skill, "sdk_session_id": None, "usage": {}, "created_at": now()}
    repo.runs[run_id] = run
    if database.enabled:
        await database.create_agent_run(run_id, project_id, payload.brief, {"max_turns": 80, "max_budget_usd": 10.0, "wall_clock_timeout_s": 1800})
    repo.append_event(run_id, {"type": "run.created", "status": status_value, "brief": payload.brief, "skill": payload.skill})
    if planned:
        repo.timelines.setdefault(project_id, [])
        repo.create_initial_timeline(project_id)
        duration = max(1000, int(repo.timelines[project_id][-1]["data"]["duration_ms"] / payload.scene_count))
        storyboard = Storyboard(project_id=project_id, brief=payload.brief, scenes=[StoryScene(id=f"scene-{index + 1}", title=f"Scene {index + 1}", start_ms=index * duration, end_ms=(index + 1) * duration) for index in range(payload.scene_count)])
        write_storyboard(project_dir(project_id), storyboard)
    else:
        await enqueue_job("agent_run", {"run_id": run_id, "project_id": project_id, "brief": run_prompt(payload.brief, payload.skill)})
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
    repo.append_event(run_id, {"type": "user.answer", "answer": payload.answer})
    if run["status"] == "waiting_for_approval":
        if payload.answer.strip().lower() not in {"approve", "approved", "yes"}:
            await set_run_status(run, "revision_requested")
            return {"accepted": True, "status": run["status"]}
        await set_run_status(run, "queued")
        storyboard_path = project_dir(run["project_id"]) / "storyboard.json"
        if storyboard_path.is_file():
            storyboard = Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))
            storyboard.status, storyboard.approved_by = "approved", user_id
            write_storyboard(storyboard_path.parent, storyboard)
        await enqueue_job("agent_run", {"run_id": run_id, "project_id": run["project_id"], "brief": run_prompt(run["brief"], run.get("skill"))})
        return {"accepted": True, "status": run["status"]}
    # Any other answer is a follow-up turn in the same SDK session, so the
    # agent keeps its context: the plan, the files it read, its questions.
    await set_run_status(run, "queued")
    await enqueue_job("agent_run", {"run_id": run_id, "project_id": run["project_id"], "prompt": payload.answer, "resume": run.get("sdk_session_id")})
    return {"accepted": True, "status": run["status"]}


@app.post("/api/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user_id: str = Depends(current_user_id)):
    run = await run_for(run_id, user_id)
    if local_runner is not None:
        local_runner.cancel(run_id)
    await set_run_status(run, "cancelled")
    repo.append_event(run_id, {"type": "run.cancelled"})
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
    repo.append_event(render["id"], {"type": "render.created", "status": "queued"})
    await enqueue_job("render", {"render_id": render["id"], "project_id": project_id, "preset": payload.preset, "brief": payload.brief or "", "frame_extracts": payload.frame_extracts})
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
    return list(repo.skills.values())


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
    skill = repo.create_skill(package.frontmatter.name, package.frontmatter.description, "user", package.body)
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
        urls = validate_user_urls(payload.urls)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    extraction_id = str(uuid4())
    record = {"id": extraction_id, "status": "queued", "urls": urls, "style_spec": None, "owner_id": user_id}
    repo.extractions[extraction_id] = record
    await enqueue_job("style_extraction", {"extraction_id": extraction_id, "owner_id": user_id, "urls": urls})
    return record


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
