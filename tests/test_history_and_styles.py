import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.event_state import record_event
from services.api.main import app, repo
from services.api.repository import MemoryRepository
from services.worker.project_bootstrap import bootstrap_project
from services.worker.style_extraction import install_user_skill, slugify_skill_name


def test_replaying_the_event_log_rebuilds_chats_uploads_and_renders():
    log = [
        ("p1", {"type": "asset.uploaded", "record": {"id": "a1", "project_id": "p1", "status": "uploaded", "probe": {}}}),
        ("p1", {"type": "ingest.completed", "asset_id": "a1", "probe": {"width": 720}}),
        ("r1", {"type": "run.created", "brief": "Edit it", "record": {"id": "r1", "project_id": "p1", "status": "queued", "brief": "Edit it", "usage": {}}}),
        ("r1", {"type": "agent.started"}),
        ("r1", {"type": "agent.message", "message": {"_type": "AssistantMessage", "content": []}}),
        ("r1", {"type": "agent.succeeded", "session_id": "s1", "usage": {}}),
        ("r1", {"type": "user.answer", "answer": "more zoom", "status": "queued"}),
        ("v1", {"type": "render.created", "record": {"id": "v1", "project_id": "p1", "status": "queued"}}),
        ("v1", {"type": "render.failed", "error": "boom"}),
    ]
    fresh = MemoryRepository()
    for stream, event in json.loads(json.dumps(log)):  # as stored in Postgres
        record_event(fresh, stream, event)
    assert fresh.assets["a1"]["status"] == "ready"
    assert fresh.runs["r1"]["status"] == "queued" and fresh.runs["r1"]["sdk_session_id"] == "s1"
    assert [event["type"] for event in fresh.events["r1"]][-2:] == ["agent.succeeded", "user.answer"]
    assert fresh.renders["v1"]["status"] == "failed"


def login(client: TestClient) -> dict[str, str]:
    repo.users.clear()
    token = client.post("/api/v1/auth/register", json={"email": "styles@example.com", "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_studio_state_and_open_request():
    with TestClient(app) as client:
        headers = login(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Studio"}).json()["id"]
        assert client.get(f"/api/v1/projects/{project_id}/studio", headers=headers).json() == {"status": "closed"}
        repo.jobs.clear()
        assert client.post(f"/api/v1/projects/{project_id}/studio", headers=headers).json()["status"] == "starting"
        assert repo.jobs[-1]["type"] == "studio_open"
        record_event(repo, project_id, {"type": "studio.ready", "url": "http://localhost:3400/#project/reel", "composition": "compositions/reel"})
        assert client.get(f"/api/v1/projects/{project_id}/studio", headers=headers).json()["url"].endswith("#project/reel")


def test_style_clone_requests_are_validated_and_listed():
    with TestClient(app) as client:
        headers = login(client)
        repo.jobs.clear()
        created = client.post("/api/v1/style-extractions", headers=headers, json={"urls": ["https://www.youtube.com/watch?v=abc"], "name": "My Cool Style!"})
        assert created.status_code == 202 and created.json()["name"] == "my-cool-style"
        assert repo.jobs[-1]["payload"]["name"] == "my-cool-style"
        assert client.post("/api/v1/style-extractions", headers=headers, json={"urls": ["http://localhost/x.mp4"], "name": "local"}).status_code == 422
        assert client.post("/api/v1/style-extractions", headers=headers, json={"urls": ["https://x.com/v"], "name": "wassim-style"}).status_code == 409
        assert [item["name"] for item in client.get("/api/v1/style-extractions", headers=headers).json()][0] == "my-cool-style"


def test_finished_style_is_installed_into_every_project(tmp_path: Path):
    projects = tmp_path / "projects"
    workspace = projects / "_styles" / "e1"
    skill = workspace / "skill-out" / "neon-reel"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: neon-reel\ndescription: Neon captions\n---\n\nSteps.\n", encoding="utf-8")
    (skill / "clip.mp4").write_bytes(b"not copied")
    installed = install_user_skill(workspace, "neon-reel", projects)
    assert (installed / "SKILL.md").is_file() and not (installed / "clip.mp4").exists()
    project = bootstrap_project(projects / "p1")
    assert (project / ".claude" / "skills" / "neon-reel" / "SKILL.md").is_file()
    assert slugify_skill_name("  Neon Reel  ") == "neon-reel"


def test_clone_forks_a_base_engine_and_renames_it(tmp_path: Path):
    from services.worker.project_bootstrap import SKILLS_ROOT
    from services.worker.style_extraction import fork_base

    fork_base(tmp_path, "warm-reel", "wassim-style", SKILLS_ROOT / "library")
    skill = tmp_path / "skill-out" / "warm-reel"
    assert (skill / "scripts" / "build_comp.py").is_file() and (skill / "templates" / "index.template.html").is_file()
    assert "name: warm-reel" in (skill / "SKILL.md").read_text(encoding="utf-8")
    assert (skill / "BASE").read_text(encoding="utf-8") == "wassim-style"


def test_agent_fork_tool_copies_the_chosen_base(tmp_path: Path):
    import shutil
    import subprocess
    import sys

    from services.worker.project_bootstrap import SKILLS_ROOT
    from services.worker.style_extraction import write_fork_tool

    shutil.copytree(SKILLS_ROOT / "library" / "devin-style", tmp_path / ".claude" / "skills" / "devin-style")
    write_fork_tool(tmp_path, "punchy")
    bad = subprocess.run([sys.executable, "tools/fork_base.py", "../etc"], cwd=tmp_path, capture_output=True, text=True)
    assert bad.returncode != 0
    ok = subprocess.run([sys.executable, "tools/fork_base.py", "devin-style"], cwd=tmp_path, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert "name: punchy" in (tmp_path / "skill-out" / "punchy" / "SKILL.md").read_text(encoding="utf-8")


def test_clone_request_accepts_comma_separated_links_and_a_base():
    with TestClient(app) as client:
        headers = login(client)
        repo.jobs.clear()
        created = client.post("/api/v1/style-extractions", headers=headers, json={"urls": ["https://youtu.be/a, https://youtu.be/b,https://youtu.be/c"], "name": "triple", "notes": "warmer", "base": "devin-style"})
        assert created.status_code == 202, created.text
        assert created.json()["urls"] == ["https://youtu.be/a", "https://youtu.be/b", "https://youtu.be/c"]
        assert repo.jobs[-1]["payload"]["base"] == "devin-style"
        assert client.post("/api/v1/style-extractions", headers=headers, json={"urls": ["https://youtu.be/a"], "name": "x2", "base": "../hack"}).status_code == 422


def test_runs_use_fast_mode_only_for_styles_with_a_fast_engine():
    with TestClient(app) as client:
        headers = login(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Fast"}).json()["id"]
        repo.jobs.clear()
        fast = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Edit it", "skill": "wassim-style", "mode": "fast", "quick": True}).json()
        assert fast["mode"] == "fast"
        payload = repo.jobs[-1]["payload"]
        assert payload["mode"] == "fast" and payload["quick"] is True and payload["prompt"] == "Edit it"
        recut = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Edit it", "skill": "talking-head-recut", "mode": "fast"}).json()
        assert recut["mode"] == "fast", "every style edits fast, through the generic engine if needed"
        helper = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Edit it", "skill": "hyperframes-core", "mode": "fast"}).json()
        assert helper["mode"] == "agent"
        skills = {skill["name"]: skill["fast"] for skill in client.get("/api/v1/skills", headers=headers).json()}
        assert skills["wassim-style"] and skills["devin-style"] and skills["talking-head-glass-edit"] and skills["talking-head-recut"]
        engines = {skill["name"]: skill["fast_engine"] for skill in client.get("/api/v1/skills", headers=headers).json()}
        assert engines["talking-head-glass-edit"] == "style" and engines["talking-head-recut"] == "generic" and engines["hyperframes-core"] is None


def test_resources_upload_without_transcription_and_attach_to_runs():
    with TestClient(app) as client:
        headers = login(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Res"}).json()["id"]
        other = client.post("/api/v1/projects", headers=headers, json={"name": "Other"}).json()["id"]
        repo.jobs.clear()
        logo = client.post(f"/api/v1/projects/{project_id}/assets", headers=headers, files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n", "image/png")}, data={"role": "resource"})
        assert logo.status_code == 201, logo.text
        assert logo.json()["role"] == "resource" and "/resources/" in logo.json()["storage_key"]
        assert repo.jobs[-1]["payload"]["role"] == "resource"
        foreign = client.post(f"/api/v1/projects/{other}/assets", headers=headers, files={"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")}, data={"role": "resource"}).json()
        listed = client.get(f"/api/v1/projects/{project_id}/assets", headers=headers).json()
        assert [item["role"] for item in listed] == ["resource"]
        assert client.post(f"/api/v1/projects/{project_id}/assets", headers=headers, files={"file": ("x.png", b"x", "image/png")}, data={"role": "boss"}).status_code == 422

        run = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Logo at the end", "skill": "wassim-style", "resources": [logo.json()["id"], foreign["id"], "nope"]}).json()
        assert repo.jobs[-1]["payload"]["resources"] == [logo.json()["id"]], "only this project's files"
        repo.runs[run["id"]].update(status="succeeded")
        reply = client.post(f"/api/v1/runs/{run['id']}/messages", headers=headers, json={"answer": "bigger logo", "resources": [logo.json()["id"]]})
        assert reply.status_code in {200, 202}, reply.text
        assert repo.jobs[-1]["payload"]["resources"] == [logo.json()["id"]]
