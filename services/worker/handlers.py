"""Job handlers shared by local and Postgres worker loops."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from .agent_runtime import AgentSessionRunner
from .ingest import ingest_asset
from .jobs import JobRecord
from .quality_harness.models import ReviewInput, TimelineSpec
from .quality_harness.verification import verify_render
from .quality_harness.review import run_blind_sdk_review
from .style_extraction import validate_user_urls, write_extracted_style_skill


@dataclass
class WorkerContext:
    projects_root: Path
    storage_root: Path
    event_sink: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None
    agent_persistence: Any = None

    def project_dir(self, project_id: str) -> Path:
        root = (self.projects_root / project_id).resolve()
        if not root.is_relative_to(self.projects_root.resolve()):
            raise ValueError("Project path escapes worker root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def emit(self, stream_id: str, event: dict[str, Any]) -> None:
        if self.event_sink:
            result = self.event_sink(stream_id, event)
            if asyncio.iscoroutine(result):
                await result


def _storage_path(context: WorkerContext, key: str) -> Path:
    path = (context.storage_root / key).resolve()
    if not path.is_relative_to(context.storage_root.resolve()):
        raise ValueError("Storage path escapes storage root")
    if not path.is_file():
        raise FileNotFoundError(key)
    return path


def failure_event(job: JobRecord, error: str) -> tuple[str, dict[str, Any]] | None:
    """The event a failed job reports, so the studio stops waiting on it."""

    payload, error = job.payload, error[:2000]
    if job.type == "ingest":
        return str(payload.get("project_id", "")), {"type": "ingest.failed", "asset_id": payload.get("asset_id"), "error": error}
    if job.type == "agent_run":
        return str(payload["run_id"]), {"type": "agent.failed", "reason": error}
    if job.type == "render":
        return str(payload["render_id"]), {"type": "render.failed", "error": error}
    return None


async def handle_job(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    payload = job.payload
    project_id = str(payload.get("project_id", ""))
    if job.type == "ingest":
        source = _storage_path(context, str(payload["storage_key"]))
        project = context.project_dir(project_id)
        raw_dir = project / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_copy = raw_dir / source.name
        if not raw_copy.exists():
            shutil.copyfile(source, raw_copy)
        await context.emit(project_id, {"type": "ingest.started", "asset_id": payload["asset_id"]})
        metadata = {"id": str(payload["asset_id"]), "filename": str(payload.get("filename") or source.name), "mime_type": payload.get("mime_type")}
        # ffmpeg is CPU-bound and blocking; keep the event loop (and the API
        # when the worker runs in-process) responsive.
        result = await asyncio.to_thread(ingest_asset, raw_copy, project / "proxies" / str(payload["asset_id"]), asset=metadata)
        await context.emit(project_id, {"type": "ingest.completed", "asset_id": payload["asset_id"], "probe": result["manifest"]["probe"]})
        return result

    if job.type == "agent_run":
        prompt = str(payload.get("prompt") or payload.get("brief") or "Inspect the project and make the requested edit.")
        runner = AgentSessionRunner(context.project_dir(project_id))
        async def on_agent_event(event: dict[str, Any]) -> None:
            await context.emit(str(payload["run_id"]), event)
            if context.agent_persistence and event.get("type") == "agent.message":
                await context.agent_persistence.add_agent_message(str(payload["run_id"]), "assistant", dict(event.get("message", {})))

        if context.agent_persistence:
            await context.agent_persistence.update_agent_run(str(payload["run_id"]), {"status": "running"})
        await context.emit(str(payload["run_id"]), {"type": "agent.started"})
        result = await runner.run(prompt, event_sink=on_agent_event, resume=payload.get("resume") or None)
        if context.agent_persistence:
            await context.agent_persistence.update_agent_run(str(payload["run_id"]), {"status": result.status, "sdk_session_id": result.session_id, "budget_json": result.usage})
        return {"status": result.status, "session_id": result.session_id, "usage": result.usage}

    if job.type == "style_extraction":
        urls = validate_user_urls([str(url) for url in payload["urls"]])
        # Fetching and model analysis are provider adapters. The durable
        # artifact is created only from derived metadata and never copies the
        # source media into the project.
        spec = {"source_urls": urls, "extraction_version": "1", "pacing": {}, "typography": {}, "color": {}, "motion": {}}
        target = write_extracted_style_skill(context.project_dir(project_id or "style-library") / "skills", f"extracted-{payload['extraction_id']}", spec)
        await context.emit(str(payload["extraction_id"]), {"type": "style.completed", "skill_path": str(target)})
        return {"style_spec": spec, "skill_path": str(target)}

    if job.type == "render":
        return await render_job(job, context)

    if job.type == "composition_preview":
        composition = Path(str(payload["composition_path"])).resolve()
        if not composition.is_relative_to(context.project_dir(project_id)):
            raise ValueError("Composition is outside the project folder")
        await context.emit(str(payload["job_id"]), {"type": "preview.queued", "composition_path": str(composition)})
        return {"status": "queued", "composition_path": str(composition)}

    if job.type in {"generate_image", "generate_voiceover"}:
        # Provider adapters are injected by the deployment worker; keeping the
        # job type explicit makes retries and usage accounting observable.
        return {"status": "queued", "provider": "openai" if job.type == "generate_image" else "voice"}

    raise ValueError(f"Unknown job type: {job.type}")


def latest_composition(project: Path) -> Path | None:
    """Most recently edited HyperFrames project under ``compositions/``."""

    candidates = [path for path in (project / "compositions").glob("*/index.html") if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime).parent if candidates else None


def hyperframes_render_command(output: Path) -> list[str]:
    # On Windows npx is ``npx.cmd``; which() returns the launcher to execute.
    return [shutil.which("npx") or "npx", "hyperframes", "render", "--output", str(output)]


async def render_job(job: JobRecord, context: WorkerContext) -> dict[str, Any]:
    project = context.project_dir(str(job.payload["project_id"]))
    render_id = str(job.payload["render_id"])
    output = project / "renders" / f"{render_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = project / "render.ffconcat"
    composition = None if manifest.is_file() else latest_composition(project)
    await context.emit(render_id, {"type": "render.started", "source": "timeline" if composition is None else f"compositions/{composition.name}"})

    if composition is not None:
        # HyperFrames projects (wassim-style and friends) carry their own
        # timing; the CLI renders them and ffprobe verifies the file exists
        # and is playable rather than comparing it to timeline.json.
        completed = await asyncio.to_thread(subprocess.run, hyperframes_render_command(output), cwd=composition, capture_output=True, text=True)
        if completed.returncode != 0 or not output.is_file():
            raise RuntimeError(f"hyperframes render failed: {(completed.stderr or completed.stdout).strip()[-2000:]}")
        from .quality_harness.verification import FFProbeRunner, parse_probe

        probe = parse_probe(await asyncio.to_thread(FFProbeRunner().probe, output))
        verification = {"ok": bool(probe.duration_ms), "source": "hyperframes", "observed": probe.model_dump(mode="json", exclude={"raw"})}
        await context.emit(render_id, {"type": "render.completed", "output_path": str(output), "verification": verification, "review": None})
        return {"status": "succeeded", "output_path": str(output), "verification": verification, "review": None}

    timeline_path = project / "timeline.json"
    if not timeline_path.is_file():
        raise FileNotFoundError("timeline.json")
    if not manifest.is_file():
        raise FileNotFoundError("Nothing to render yet: ask the agent to build a composition under compositions/ or a render.ffconcat from the timeline")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    spec = TimelineSpec(duration_ms=int(timeline["duration_ms"]), width=int(timeline["width"]), height=int(timeline["height"]), fps=float(timeline["fps"]))
    from .media import render_timeline_command, run_media_command

    await asyncio.to_thread(run_media_command, render_timeline_command(manifest, output, fps=round(spec.fps), width=spec.width, height=spec.height))
    report = await asyncio.to_thread(verify_render, output, spec)
    if not report.ok:
        raise RuntimeError(report.model_dump_json())
    review = None
    if str(job.payload.get("preset", "preview")) != "preview" and os.getenv("ANTHROPIC_API_KEY"):
        review_input = ReviewInput(original_brief=str(job.payload.get("brief", "Verify the final render against the timeline.")), timeline=timeline, frame_extracts=[str(item) for item in job.payload.get("frame_extracts", [])], verification_report=report)
        passed, issues = await run_blind_sdk_review(review_input, model=os.getenv("AGENT_MODEL", "claude-opus-5-5"))
        review = {"passed": passed, "issues": issues, "cycle": 1}
        if not passed:
            raise RuntimeError(json.dumps({"review_failed": issues}))
    await context.emit(render_id, {"type": "render.completed", "output_path": str(output), "verification": report.model_dump(mode="json"), "review": review})
    return {"status": "succeeded", "output_path": str(output), "verification": report.model_dump(mode="json"), "review": review}
