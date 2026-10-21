import asyncio
import io
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.local_worker import LocalJobRunner
from services.api.main import app, repo
from services.api.repository import MemoryRepository, now


def owner(client: TestClient, email: str = "studio@example.com") -> dict[str, str]:
    repo.users.clear()
    token = client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_skill_catalog_includes_house_styles():
    with TestClient(app) as client:
        names = {skill["name"]: skill["scope"] for skill in client.get("/api/v1/skills", headers=owner(client)).json()}
    assert names["wassim-style"] == "library"
    assert names["talking-head-cleanup"] == "builtin"
    assert {"devin-style", "hyperframes", "media-use"} <= names.keys()


def test_project_memory_round_trip_and_assets_listing():
    with TestClient(app) as client:
        headers = owner(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Memory"}).json()["id"]
        memory = client.get(f"/api/v1/projects/{project_id}/memory", headers=headers)
        assert memory.status_code == 200 and "Project memory" in memory.json()["content"]
        saved = client.put(f"/api/v1/projects/{project_id}/memory", headers=headers, json={"content": "# Brand\nBlue only.\n"})
        assert saved.json()["content"].startswith("# Brand")
        assert client.get(f"/api/v1/projects/{project_id}/memory", headers=headers).json()["content"] == "# Brand\nBlue only.\n"

        client.post(f"/api/v1/projects/{project_id}/assets", headers=headers, files={"file": ("clip.mp4", io.BytesIO(b"bytes"), "video/mp4")})
        assets = client.get(f"/api/v1/projects/{project_id}/assets", headers=headers).json()
        assert [asset["filename"] for asset in assets] == ["clip.mp4"]
        assert client.get(f"/api/v1/projects/{project_id}/outputs", headers=headers).json() == []


def test_run_with_skill_points_the_agent_at_it():
    with TestClient(app) as client:
        headers = owner(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Reel"}).json()["id"]
        repo.jobs.clear()
        run = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Edit my clip", "skill": "wassim-style"})
        assert run.status_code == 202 and run.json()["skill"] == "wassim-style"
        job = repo.jobs[-1]
        assert job["type"] == "agent_run"
        assert "`wassim-style` skill" in job["payload"]["brief"]
        assert client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "x", "skill": "../evil"}).status_code == 422


def test_follow_up_message_resumes_the_sdk_session():
    with TestClient(app) as client:
        headers = owner(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Chat"}).json()["id"]
        run_id = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Trim it"}).json()["id"]
        # Still queued: the agent has not finished its turn.
        assert client.post(f"/api/v1/runs/{run_id}/messages", headers=headers, json={"answer": "go"}).status_code == 409
        repo.runs[run_id].update(status="succeeded", sdk_session_id="session-1")
        reply = client.post(f"/api/v1/runs/{run_id}/messages", headers=headers, json={"answer": "Use the blue palette"})
        assert reply.json()["status"] == "queued"
        assert repo.jobs[-1]["payload"] == {"run_id": run_id, "project_id": project_id, "prompt": "Use the blue palette", "resume": "session-1", "skill": None, "title": "Trim it", "mode": "agent", "asset_id": None, "quick": False, "resources": []}


def test_project_files_need_a_signature_or_the_owner(tmp_path: Path):
    with TestClient(app) as client:
        headers = owner(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Files"}).json()["id"]
        assert client.get(f"/api/v1/project-files/{project_id}/renders/x.mp4").status_code == 401
        assert client.get(f"/api/v1/project-files/{project_id}/.agent-context/events.jsonl", headers=headers).status_code == 404
        assert client.get(f"/api/v1/project-files/{project_id}/renders/x.mp4?expires=1&signature=bad").status_code == 403


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed")
def test_local_runner_ingests_an_upload(tmp_path: Path):
    storage_root, projects_root = tmp_path / "storage", tmp_path / "projects"
    clip = storage_root / "projects" / "p1" / "raw" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=1", "-f", "lavfi", "-i", "sine=duration=1", "-shortest", str(clip)], check=True, capture_output=True)
    local_repo = MemoryRepository()
    local_repo.assets["a1"] = {"id": "a1", "project_id": "p1", "status": "uploaded", "probe": {}, "created_at": now()}

    async def scenario() -> None:
        runner = LocalJobRunner(local_repo, projects_root, storage_root)
        runner.submit("ingest", {"asset_id": "a1", "project_id": "p1", "storage_key": "projects/p1/raw/clip.mp4", "filename": "clip.mp4"})
        for _ in range(600):
            if any(event["type"].startswith("transcribe.") and event["type"] != "transcribe.started" for event in local_repo.events.get("p1", [])):
                break
            await asyncio.sleep(0.1)
        await runner.shutdown()

    asyncio.run(scenario())
    asset = local_repo.assets["a1"]
    assert asset["status"] == "ready", local_repo.events
    assert asset["probe"]["width"] == 320 and asset["probe"]["has_audio"]
    assert (projects_root / "p1" / "proxies" / "a1" / "asset.json").is_file()
    kinds = [event["type"] for event in local_repo.events["p1"]]
    # Transcription follows ingest; with no Whisper model here it fails
    # without undoing the upload.
    assert kinds[:3] == ["ingest.started", "ingest.completed", "transcribe.started"]
    assert kinds[3] in {"transcribe.completed", "transcribe.failed"}


def test_outputs_skip_source_footage_and_scratch_renders():
    from services.api.main import project_dir

    with TestClient(app) as client:
        headers = owner(client, "outputs@example.com")
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Outputs"}).json()["id"]
        root = project_dir(project_id)
        for relative in ("renders/final.mp4", "renders/work-1/frame.mp4", "compositions/reel/assets/source.mp4", "compositions/reel/renders/v2.mp4"):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_bytes(b"x")
        paths = {item["path"] for item in client.get(f"/api/v1/projects/{project_id}/outputs", headers=headers).json()}
        assert paths == {"renders/final.mp4", "compositions/reel/renders/v2.mp4"}


def test_outputs_and_timeline_belong_to_their_run():
    import json

    from services.api.main import project_dir
    from services.worker.catalog import COMPOSITION_META

    with TestClient(app) as client:
        headers = owner(client, "scoped@example.com")
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Scoped"}).json()["id"]
        root = project_dir(project_id)
        for name, run_id in (("first", "run-a"), ("second", "run-b")):
            folder = root / "compositions" / name
            (folder / "renders").mkdir(parents=True, exist_ok=True)
            (folder / "index.html").write_text(f'<div id="root" data-composition-id="{name}" data-width="1080" data-height="1920" data-duration="2"></div>', encoding="utf-8")
            (folder / COMPOSITION_META).write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
            (folder / "renders" / "out.mp4").write_bytes(b"x")
        outputs = client.get(f"/api/v1/projects/{project_id}/outputs", headers=headers).json()
        assert {item["composition"]: item["run_id"] for item in outputs} == {"compositions/first": "run-a", "compositions/second": "run-b"}

        timeline = client.get(f"/api/v1/projects/{project_id}/timeline/composition", headers=headers, params={"composition": "compositions/first"}).json()
        assert timeline["source"] == "compositions/first"
        assert client.get(f"/api/v1/projects/{project_id}/timeline/composition", headers=headers, params={"composition": "../etc"}).status_code == 422


def test_style_is_read_from_old_video_names():
    from services.worker.catalog import guess_style

    skills = ["wassim-style", "talking-head-glass-edit", "neon-3d-blue", "devin-style"]
    assert guess_style(["protect-your-job-neon-3d-blue"], skills) == "neon-3d-blue"
    assert guess_style(["protectyourjob-wassim"], skills) == "wassim-style"
    assert guess_style(["kachabia-3920-glass-reel"], skills) == "talking-head-glass-edit"
    assert guess_style(["781f0b3b-9ea9-4a07", "compositions/protectyourjob-wassim"], skills) == "wassim-style"
    assert guess_style(["final"], skills) is None
