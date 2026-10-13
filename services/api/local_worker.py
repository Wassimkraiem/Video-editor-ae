"""In-process job runner for local development without Postgres.

Deployed stacks publish jobs to Postgres and a separate worker claims them.
Locally there is no queue consumer, so jobs would sit in memory forever; this
runner executes the same ``handle_job`` handlers inside the API process.
Outcomes reach the repository the same way as in Docker: through events
applied by ``record_event``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from services.worker.handlers import WorkerContext, failure_event, handle_job
from services.worker.jobs import JobRecord

from .event_state import record_event
from .repository import MemoryRepository

logger = logging.getLogger("video-editor-local-worker")

# Agent runs are long and expensive: one at a time. Media jobs get their own
# lane so an upload is ingested while the agent is still working.
LANES = {"agent_run": "agent", "style_extraction": "agent"}
LANE_LIMITS = {"agent": 1, "media": 2}


class LocalJobRunner:
    def __init__(self, repo: MemoryRepository, projects_root: str | Path, storage_root: str | Path):
        self.repo = repo
        self.context = WorkerContext(Path(projects_root).resolve(), Path(storage_root).resolve(), event_sink=self._emit)
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def _emit(self, stream_id: str, event: dict[str, Any]) -> None:
        record_event(self.repo, stream_id, event)

    def submit(self, job_type: str, payload: dict[str, Any]) -> JobRecord:
        job = JobRecord(job_type, payload)
        task = asyncio.get_running_loop().create_task(self._run(job))
        key = str(payload.get("run_id") or payload.get("render_id") or job.id)
        self._tasks[key] = task
        task.add_done_callback(lambda _: self._tasks.pop(key, None))
        return job

    def cancel(self, key: str) -> bool:
        task = self._tasks.get(key)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    async def _run(self, job: JobRecord) -> None:
        lane = LANES.get(job.type, "media")
        semaphore = self._semaphores.setdefault(lane, asyncio.Semaphore(LANE_LIMITS[lane]))
        async with semaphore:
            logger.info("local_job_started id=%s type=%s", job.id, job.type)
            try:
                await handle_job(job, self.context)
            except asyncio.CancelledError:
                self._fail(job, "cancelled")
                raise
            except Exception as exc:
                logger.exception("local_job_failed id=%s type=%s", job.id, job.type)
                self._fail(job, str(exc) or type(exc).__name__)

    def _fail(self, job: JobRecord, error: str) -> None:
        if failed := failure_event(job, error):
            self._emit(*failed)
