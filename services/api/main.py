from __future__ import annotations

import asyncio
import json
import logging
import secrets
import tempfile
import zipfile
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
)
from .security import create_token, current_user_id, hash_password, verify_password, decode_token
from .storage import LocalStorage, sniff_mime
from .queue import enqueue_postgres_job
from .persistence import PostgresPersistence
from services.worker.skill_parser import validate_skill_archive
from services.worker.style_extraction import validate_user_urls
from .rate_limit import expensive_rate_limit
from services.worker.quality_harness.models import ProjectProfile
from services.worker.project_bootstrap import bootstrap_project
from services.worker.quality_harness.models import Storyboard, StoryScene
from services.worker.quality_harness.planning import requires_plan, write_storyboard


settings = get_settings()
logger = logging.getLogger("video-editor-api")
repo = MemoryRepository()
database = PostgresPersistence(settings.database_url)
storage = LocalStorage(settings.storage_root, settings.access_token_secret)
app = FastAPI(title="AI Video Editing Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
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
    root = Path(__file__).resolve().parents[2] / "skills" / "builtin"
    if not root.is_dir() or repo.skills:
        return
    for skill_path in sorted(root.glob("*/SKILL.md")):
        try:
            text = skill_path.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            import yaml
            metadata = yaml.safe_load(frontmatter) or {}
            repo.create_skill(str(metadata["name"]), str(metadata["description"]), "builtin", text)
        except (OSError, KeyError, ValueError):
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


def event_stream(stream_id: str, last_event_id: str | None):
    events = repo.events.get(stream_id, [])
    try:
        after = int(last_event_id or 0)
    except ValueError:
        after = 0
    for event in events:
        if int(event["id"]) <= after:
            continue
        yield f"id: {event['id']}\ndata: {json.dumps(event, default=str)}\n\n"
    yield ": heartbeat\n\n"


async def enqueue_job(job_type: str, payload: dict[str, Any]) -> None:
    """Publish locally and durably when a Postgres queue is configured."""

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
    database = "memory"
    if settings.database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                database = "ready"
            finally:
                await engine.dispose()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
    return {"status": "ready", "database": database, "storage": "ready"}


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
    del repo.projects[project_id]


@app.get("/api/v1/projects/{project_id}/timeline/versions", response_model=list[TimelineVersionResponse])
async def timeline_versions(project_id: str, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
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
    versions = repo.timelines[project_id]
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
    await enqueue_job("ingest", {"asset_id": asset["id"], "project_id": project_id, "storage_key": key})
    return asset


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
    await asset_for(asset_id, user_id)
    return {"asset_id": asset_id, "words": []}


@app.get("/api/v1/assets/{asset_id}/url", response_model=AssetURLResponse)
async def asset_url(asset_id: str, user_id: str = Depends(current_user_id)):
    asset = await asset_for(asset_id, user_id)
    return {"url": storage.url(asset["storage_key"]), "expires_in": 900}


@app.get("/api/v1/media/{key:path}")
async def media(key: str, request: Request, user_id: str = Depends(current_user_id)):
    # Resolve project ownership from the storage key before serving bytes.
    parts = Path(key).parts
    if len(parts) < 2 or parts[0] != "projects":
        raise HTTPException(status_code=404, detail="Media not found")
    await require_project_access(parts[1], user_id)
    expires = request.query_params.get("expires")
    signature = request.query_params.get("signature")
    if expires is not None or signature is not None:
        try:
            valid = storage.verify(key, int(expires or "0"), signature or "")
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(status_code=403, detail="Media URL has expired or is invalid")
    try:
        path = storage.path(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Media not found") from exc
    return FileResponse(path)


@app.post("/api/v1/projects/{project_id}/runs", response_model=RunResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def create_run(project_id: str, payload: RunCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    run_id = str(uuid4())
    planned = requires_plan(scene_count=payload.scene_count, motion_graphics=payload.motion_graphics, brief=payload.brief)
    status_value = "waiting_for_approval" if planned else "queued"
    run = {"id": run_id, "project_id": project_id, "status": status_value, "brief": payload.brief, "sdk_session_id": None, "usage": {}, "created_at": now()}
    repo.runs[run_id] = run
    if database.enabled:
        await database.create_agent_run(run_id, project_id, payload.brief, {"max_turns": 40, "max_budget_usd": 10.0, "wall_clock_timeout_s": 900})
    if planned:
        duration = max(1000, int(repo.timelines[project_id][-1]["data"]["duration_ms"] / payload.scene_count))
        storyboard = Storyboard(project_id=project_id, brief=payload.brief, scenes=[StoryScene(id=f"scene-{index + 1}", title=f"Scene {index + 1}", start_ms=index * duration, end_ms=(index + 1) * duration) for index in range(payload.scene_count)])
        write_storyboard(Path(settings.projects_root) / project_id, storyboard)
    else:
        await enqueue_job("agent_run", {"run_id": run_id, "project_id": project_id, "brief": payload.brief})
    repo.append_event(run_id, {"type": "run.created", "status": status_value})
    return run


async def run_for(run_id: str, user_id: str) -> dict[str, Any]:
    run = repo.runs.get(run_id)
    if database.enabled:
        run = await database.agent_run(run_id, user_id) or run
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
    repo.append_event(run_id, {"type": "user.answer", "answer": payload.answer})
    if run["status"] == "waiting_for_approval":
        if payload.answer.strip().lower() not in {"approve", "approved", "yes"}:
            run["status"] = "revision_requested"
            return {"accepted": True, "status": run["status"]}
        run["status"] = "queued"
        await enqueue_job("agent_run", {"run_id": run_id, "project_id": run["project_id"], "brief": run["brief"]})
    else:
        run["status"] = "running"
    return {"accepted": True}


@app.post("/api/v1/runs/{run_id}/cancel")
async def cancel_run(run_id: str, user_id: str = Depends(current_user_id)):
    run = await run_for(run_id, user_id)
    run["status"] = "cancelled"
    repo.append_event(run_id, {"type": "run.cancelled"})
    return run


@app.get("/api/v1/runs/{run_id}/events")
async def run_events(request: Request, run_id: str, user_id: str = Depends(current_user_id), last_event_id: str | None = None):
    await run_for(run_id, user_id)
    return StreamingResponse(event_stream(run_id, request.headers.get("Last-Event-ID") or last_event_id), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/v1/projects/{project_id}/renders", response_model=RenderResponse, status_code=202, dependencies=[Depends(expensive_rate_limit)])
async def create_render(project_id: str, payload: RenderCreate, user_id: str = Depends(current_user_id)):
    await require_project_access(project_id, user_id)
    render = {"id": str(uuid4()), "project_id": project_id, "preset": payload.preset, "status": "queued", "output_url": None, "verification": None, "created_at": now()}
    repo.renders[render["id"]] = render
    await enqueue_job("render", {"render_id": render["id"], "project_id": project_id, "preset": payload.preset, "brief": payload.brief or "", "frame_extracts": payload.frame_extracts})
    repo.append_event(render["id"], {"type": "render.created", "status": "queued"})
    return render


def render_for(render_id: str, user_id: str) -> dict[str, Any]:
    render = repo.renders.get(render_id)
    if not render:
        raise HTTPException(status_code=404, detail="Render not found")
    require_project(render["project_id"], user_id)
    return render


@app.get("/api/v1/renders/{render_id}", response_model=RenderResponse)
async def get_render(render_id: str, user_id: str = Depends(current_user_id)):
    return render_for(render_id, user_id)


@app.get("/api/v1/renders/{render_id}/events")
async def render_events(request: Request, render_id: str, user_id: str = Depends(current_user_id), last_event_id: str | None = None):
    render_for(render_id, user_id)
    return StreamingResponse(event_stream(render_id, request.headers.get("Last-Event-ID") or last_event_id), media_type="text/event-stream")


@app.get("/api/v1/renders/{render_id}/download", response_model=DownloadResponse)
async def download_render(render_id: str, user_id: str = Depends(current_user_id)):
    render = render_for(render_id, user_id)
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
    return StreamingResponse(event_stream(extraction_id, request.headers.get("Last-Event-ID") or last_event_id), media_type="text/event-stream")


@app.post("/api/v1/style-extractions/{extraction_id}/approve")
async def approve_style_extraction(extraction_id: str, user_id: str = Depends(current_user_id)):
    record = repo.extractions.get(extraction_id)
    if not record or record["owner_id"] != user_id:
        raise HTTPException(status_code=404, detail="Style extraction not found")
    record["status"] = "approved"
    return record
