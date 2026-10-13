from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from packages.timeline_schema import Timeline, TimelineOp, TimelineVersion, apply_timeline_ops


def now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryRepository:
    """Deterministic repository used by tests and local development.

    The same interface is the seam for the Postgres repository used in
    production; routes never depend on storage implementation details.
    """

    def __init__(self):
        self.users: dict[str, dict[str, Any]] = {}
        self.projects: dict[str, dict[str, Any]] = {}
        self.project_members: dict[tuple[str, str], str] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.renders: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.timelines: dict[str, list[dict[str, Any]]] = {}
        self.compositions: dict[str, dict[str, Any]] = {}
        self.skills: dict[str, dict[str, Any]] = {}
        self.project_skills: dict[tuple[str, str], bool] = {}
        self.images: dict[str, dict[str, Any]] = {}
        self.extractions: dict[str, dict[str, Any]] = {}
        self.jobs: list[dict[str, Any]] = []
        self.refresh_tokens: set[str] = set()

    def enqueue_job(self, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        job = {"id": str(uuid4()), "type": job_type, "payload": payload, "status": "queued", "attempts": 0, "run_after": now(), "locked_by": None, "locked_at": None, "last_error": None}
        self.jobs.append(job)
        return job

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        if any(user["email"].lower() == email.lower() for user in self.users.values()):
            raise ValueError("Email already registered")
        record = {"id": str(uuid4()), "email": email.lower(), "password_hash": password_hash, "created_at": now()}
        self.users[record["id"]] = record
        return record

    def create_project(self, owner_id: str, name: str, workflow: str, profile: dict[str, Any]) -> dict[str, Any]:
        project_id = str(uuid4())
        record = {"id": project_id, "owner_id": owner_id, "name": name, "workflow": workflow, "profile": profile, "created_at": now(), "updated_at": now()}
        self.projects[project_id] = record
        self.timelines[project_id] = []
        return record

    def project_for(self, project_id: str, user_id: str) -> dict[str, Any]:
        project = self.projects.get(project_id)
        if not project or (project["owner_id"] != user_id and (project_id, user_id) not in self.project_members):
            raise KeyError(project_id)
        return project

    def add_member(self, project_id: str, user_id: str, role: str = "member") -> None:
        self.project_members[(project_id, user_id)] = role

    def append_event(self, stream_id: str, event: dict[str, Any]) -> None:
        events = self.events.setdefault(stream_id, [])
        events.append({"id": str(len(events) + 1), **event})

    def create_initial_timeline(self, project_id: str) -> None:
        if self.timelines[project_id]:
            return
        timeline = Timeline(fps=30, width=1920, height=1080, duration_ms=1000)
        self.timelines[project_id].append({"version": 1, "parent_version": None, "schema_version": timeline.schema_version, "data": timeline.model_dump(mode="json"), "diff": [], "created_at": now()})

    def apply_version(self, project_id: str, ops: list[dict[str, Any]], timeline_data: dict[str, Any] | None) -> dict[str, Any]:
        self.create_initial_timeline(project_id)
        current = self.timelines[project_id][-1]
        timeline = Timeline.model_validate(timeline_data) if timeline_data else Timeline.model_validate(current["data"])
        updated, diff = apply_timeline_ops(timeline, [TimelineOp.model_validate(op) for op in ops])
        record = {"version": len(self.timelines[project_id]) + 1, "parent_version": current["version"], "schema_version": updated.schema_version, "data": updated.model_dump(mode="json"), "diff": diff, "created_at": now()}
        self.timelines[project_id].append(record)
        return record

    def create_skill(self, name: str, description: str, scope: str, body: str) -> dict[str, Any]:
        skill_id = str(uuid4())
        checksum = hashlib.sha256(body.encode()).hexdigest()
        record = {"id": skill_id, "name": name, "description": description, "scope": scope, "body": body, "checksum": checksum, "enabled": True, "scripts_approved": False}
        self.skills[skill_id] = record
        return record

    def set_project_skill(self, project_id: str, skill_id: str, enabled: bool = True) -> dict[str, Any]:
        if skill_id not in self.skills:
            raise KeyError(skill_id)
        self.project_skills[(project_id, skill_id)] = enabled
        return self.skills[skill_id]
