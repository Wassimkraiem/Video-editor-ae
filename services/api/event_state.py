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


def record_event(repo: MemoryRepository, stream_id: str, event: dict[str, Any]) -> None:
    """Append an event to its SSE stream and update the matching record."""

    repo.append_event(stream_id, event)
    apply_event(repo, stream_id, event)
