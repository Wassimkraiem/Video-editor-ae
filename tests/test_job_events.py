from services.api.event_state import record_event
from services.api.repository import MemoryRepository, now
from services.worker.handlers import failure_event
from services.worker.jobs import JobRecord


def repo_with_records() -> MemoryRepository:
    repo = MemoryRepository()
    repo.assets["a1"] = {"id": "a1", "status": "uploaded", "probe": {"sha256": "x"}, "created_at": now()}
    repo.runs["r1"] = {"id": "r1", "status": "queued", "usage": {}, "sdk_session_id": None}
    repo.renders["v1"] = {"id": "v1", "status": "queued"}
    return repo


def test_worker_events_drive_asset_run_and_render_state():
    repo = repo_with_records()
    record_event(repo, "p1", {"type": "ingest.completed", "asset_id": "a1", "probe": {"width": 720}})
    record_event(repo, "r1", {"type": "agent.started"})
    assert repo.runs["r1"]["status"] == "running"
    record_event(repo, "r1", {"type": "agent.succeeded", "session_id": "s1", "usage": {"total_cost_usd": 0.5}})
    record_event(repo, "v1", {"type": "render.completed", "output_path": "/work/projects/p1/renders/v1.mp4", "verification": {"ok": True}})

    assert repo.assets["a1"]["status"] == "ready"
    assert repo.assets["a1"]["probe"] == {"sha256": "x", "width": 720}
    assert repo.runs["r1"] == {"id": "r1", "status": "succeeded", "usage": {"total_cost_usd": 0.5}, "sdk_session_id": "s1"}
    assert repo.renders["v1"]["status"] == "succeeded" and repo.renders["v1"]["output_path"].endswith("v1.mp4")
    # Every event also lands on its SSE stream.
    assert [event["type"] for event in repo.events["r1"]] == ["agent.started", "agent.succeeded"]


def test_a_cancelled_run_stays_cancelled_when_the_task_fails():
    repo = repo_with_records()
    repo.runs["r1"]["status"] = "cancelled"
    record_event(repo, "r1", {"type": "agent.failed", "reason": "cancelled"})
    assert repo.runs["r1"]["status"] == "cancelled"


def test_failed_jobs_report_an_event_the_studio_understands():
    repo = repo_with_records()
    for job in (
        JobRecord("ingest", {"asset_id": "a1", "project_id": "p1"}),
        JobRecord("agent_run", {"run_id": "r1", "project_id": "p1"}),
        JobRecord("render", {"render_id": "v1", "project_id": "p1"}),
    ):
        stream_id, event = failure_event(job, "boom")
        record_event(repo, stream_id, event)
    assert (repo.assets["a1"]["status"], repo.runs["r1"]["status"], repo.renders["v1"]["status"]) == ("failed", "failed", "failed")
    assert repo.renders["v1"]["error"] == "boom"
    assert failure_event(JobRecord("generate_image", {}), "boom") is None
