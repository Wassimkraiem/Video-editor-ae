"""Apply job events to the API's view of assets, runs and renders.

Workers report progress only through events (``ingest.completed``,
``agent.succeeded``, ``render.failed``, ...). The in-process runner and the
Postgres event tail both feed them through ``record_event``, so local and
Docker deployments update state the same way.
"""

from __future__ import annotations

from typing import Any

from .repository import MemoryRepository


def apply_event(repo: MemoryRepository, stream_id: str, event: dict[str, Any]) -> None:
    kind = str(event.get("type", ""))
    # Creation events carry the whole record, so replaying the event log
    # after a restart rebuilds chats, uploads and renders.
    record = event.get("record")
    if isinstance(record, dict) and record.get("id"):
        table = {"asset.uploaded": repo.assets, "run.created": repo.runs, "render.created": repo.renders, "style.created": repo.extractions}.get(kind)
        if table is not None:
            table.setdefault(str(record["id"]), dict(record))
            return
    if kind == "user.answer" and stream_id in repo.runs and event.get("status"):
        repo.runs[stream_id]["status"] = event["status"]
        return
    if kind == "ae.export.ready" and stream_id in repo.runs:
        repo.runs[stream_id]["export_path"] = event.get("path")
        return
    if kind == "run.cancelled" and stream_id in repo.runs:
        repo.runs[stream_id]["status"] = "cancelled"
        return
    extraction = repo.extractions.get(stream_id)
    if extraction is not None:
        if kind == "style.downloading":
            extraction["status"] = "downloading"
        elif kind == "agent.started":
            extraction["status"] = "analyzing"
        elif kind == "style.failed":
            extraction.update(status="failed", error=event.get("error"))
        elif kind == "style.completed" and isinstance(event.get("skill"), dict):
            skill = event["skill"]
            extraction.update(status="completed", skill_name=skill.get("name"))
            register_user_skill(repo, skill)
        return
    if kind == "skill.restored" and isinstance(event.get("skill"), dict):
        register_user_skill(repo, event["skill"])
        return
    if kind in {"studio.ready", "studio.failed"}:
        repo.studios[stream_id] = {"status": "ready" if kind == "studio.ready" else "failed", **{key: event.get(key) for key in ("url", "composition", "error")}}
        return
    if kind.startswith("transcribe.") or kind == "transcript.edited":
        asset = repo.assets.get(str(event.get("asset_id", "")))
        if asset is not None:
            if kind in {"transcribe.started", "transcribe.queued"}:
                asset.update(transcript_status="transcribing", transcript_reviewed=False)
            elif kind == "transcribe.cleaning":
                asset["transcript_status"] = "cleaning"
            elif kind == "transcribe.completed":
                asset.update(transcript_status="ready", transcript_language=event.get("language"), transcript_reviewed=False)
            elif kind == "transcribe.failed":
                asset.update(transcript_status="failed", transcript_error=event.get("error"))
            elif kind == "transcript.edited":
                asset.update(transcript_status="ready", transcript_reviewed=True, transcript_language=event.get("language") or asset.get("transcript_language"))
        return
    if kind.startswith("ingest."):
        asset = repo.assets.get(str(event.get("asset_id", "")))
        if asset is None:
            return
        if kind == "ingest.completed":
            asset["status"] = "ready"
            asset["probe"] = {**(asset.get("probe") or {}), **(event.get("probe") or {})}
        elif kind == "ingest.failed":
            asset["status"] = "failed"
    elif kind.startswith("agent."):
        run = repo.runs.get(stream_id)
        if run is None:
            return
        if kind == "agent.started":
            run["status"] = "running"
        elif kind in {"agent.succeeded", "agent.failed"}:
            # A cancel already set the final status; a late failure from the
            # interrupted task must not overwrite it.
            if run.get("status") != "cancelled":
                run["status"] = "succeeded" if kind == "agent.succeeded" else "failed"
            if event.get("session_id"):
                run["sdk_session_id"] = event["session_id"]
            if isinstance(event.get("usage"), dict):
                run["usage"] = event["usage"]
    elif kind.startswith("render."):
        render = repo.renders.get(stream_id)
        if render is None:
            return
        if kind == "render.started":
            render["status"] = "running"
        elif kind == "render.completed":
            render["status"] = "succeeded"
            render["output_path"] = event.get("output_path")
            render["verification"] = event.get("verification")
        elif kind == "render.failed":
            render["status"] = "failed"
            render["error"] = event.get("error")


def register_user_skill(repo: MemoryRepository, skill: dict[str, Any]) -> None:
    """Add (or replace) a cloned style in the skill catalog."""

    for skill_id, existing in list(repo.skills.items()):
        if existing["name"] == skill.get("name") and existing["scope"] == "user":
            del repo.skills[skill_id]
    # Every cloned style edits fast; forks keep their base's engine.
    engine = skill.get("engine") or ("style" if skill.get("fast") else "generic")
    repo.create_skill(str(skill["name"]), str(skill.get("description", "")), "user", str(skill.get("body", "")), fast=True, engine=engine)


def record_event(repo: MemoryRepository, stream_id: str, event: dict[str, Any]) -> None:
    """Append an event to its SSE stream and update the matching record."""

    repo.append_event(stream_id, event)
    apply_event(repo, stream_id, event)
