import asyncio
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.event_state import record_event
from services.api.main import app, project_dir, repo
from services.worker import ae_export, handlers
from services.worker.fast_edit import is_helper, is_style
from services.worker.handlers import WorkerContext, handle_job, skills_for
from services.worker.jobs import JobRecord
from services.worker.project_bootstrap import SKILLS_ROOT, bootstrap_project

INDEX = '<div id="root" data-composition-id="main" data-width="1080" data-height="1920" data-duration="12"></div>'


def login(client: TestClient) -> dict[str, str]:
    repo.users.clear()
    token = client.post("/api/v1/auth/register", json={"email": "ae@example.com", "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_ae_builder_is_a_tool_not_a_style():
    assert is_helper("ae-builder") and not is_style(SKILLS_ROOT / "library" / "ae-builder")
    assert not is_helper("wassim-style")


def test_export_request_starts_an_agent_run_with_the_skill_and_fixed_paths():
    with TestClient(app) as client:
        headers = login(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "AE"}).json()["id"]
        reel = project_dir(project_id) / "compositions" / "promo"
        reel.mkdir(parents=True, exist_ok=True)
        (reel / "index.html").write_text(INDEX, encoding="utf-8")
        repo.jobs.clear()
        run = client.post(f"/api/v1/projects/{project_id}/ae-exports", headers=headers, json={"composition": "compositions/promo"})
        assert run.status_code == 202 and run.json()["skill"] == "ae-builder" and run.json()["status"] == "queued"
        payload = repo.jobs[-1]["payload"]
        assert payload["mode"] == "agent" and payload["ae_export"] == "compositions/promo"
        assert "`ae-builder` skill" in payload["brief"] and "exports/ae/promo/" in payload["brief"] and "1080x1920" in payload["brief"]
        assert "do not ask the user" in payload["brief"]
        # Not waiting for a storyboard approval.
        assert repo.runs[run.json()["id"]]["status"] == "queued"
        assert client.post(f"/api/v1/projects/{project_id}/ae-exports", headers=headers, json={"composition": "compositions/missing"}).status_code == 404
        assert client.post(f"/api/v1/projects/{project_id}/ae-exports", headers=headers, json={"composition": "../raw"}).status_code == 422

        # Once the worker reports the zip, the run carries a signed download link.
        bundle = project_dir(project_id) / ae_export.zip_name("compositions/promo")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_bytes(b"zip")
        record_event(repo, run.json()["id"], {"type": "ae.export.ready", "path": ae_export.zip_name("compositions/promo")})
        fetched = client.get(f"/api/v1/runs/{run.json()['id']}", headers=headers).json()
        assert fetched["export_url"].startswith(f"/api/v1/project-files/{project_id}/renders/ae/promo_ae.zip?expires=")
        assert client.get(fetched["export_url"]).content == b"zip"


def test_zip_holds_the_deliverable_but_not_the_generator(tmp_path: Path):
    out = tmp_path / ae_export.export_dir("compositions/promo")
    for relative in ("Promo_Rebuild.jsx", "README.txt", "fonts/Inter.ttf", "assets/logo.png", "generator/build.py", "keys.json"):
        (out / relative).parent.mkdir(parents=True, exist_ok=True)
        (out / relative).write_text("x", encoding="utf-8")
    bundle = ae_export.zip_export(tmp_path, "compositions/promo")
    names = set(zipfile.ZipFile(bundle).namelist())
    assert names == {"promo_ae/Promo_Rebuild.jsx", "promo_ae/README.txt", "promo_ae/fonts/Inter.ttf", "promo_ae/assets/logo.png"}


def test_export_job_loads_the_skill_and_zips_what_the_agent_wrote(tmp_path: Path, monkeypatch):
    project = bootstrap_project(tmp_path / "projects" / "p1")
    assert "ae-builder" in skills_for(project, "ae-builder")
    seen = {}

    class FakeAgent:
        def __init__(self, workspace: Path):
            self.workspace = workspace

        async def run(self, prompt, event_sink=None, resume=None, skills=None):
            seen["prompt"], seen["skills"] = prompt, skills
            out = self.workspace / "exports" / "ae" / "promo"
            out.mkdir(parents=True, exist_ok=True)
            (out / "Promo_Rebuild.jsx").write_text("// build", encoding="utf-8")
            return type("Result", (), {"status": "succeeded", "session_id": "s1", "usage": {}})()

    monkeypatch.setattr(handlers, "AgentSessionRunner", FakeAgent)
    events: list[dict] = []
    context = WorkerContext(tmp_path / "projects", tmp_path / "storage", event_sink=lambda stream, event: events.append(event))
    job = JobRecord(type="agent_run", payload={"run_id": "r1", "project_id": "p1", "brief": "Use the ae-builder skill. Rebuild it.", "skill": "ae-builder", "mode": "agent", "kind": "people", "ae_export": "compositions/promo"})
    asyncio.run(handle_job(job, context))
    assert "ae-builder" in seen["skills"]
    # The export brief leads, with no transcript brief or editing guidance around it
    # (per-skill notes from earlier exports may follow).
    assert seen["prompt"].startswith("Use the ae-builder skill. Rebuild it.")
    assert "Video type:" not in seen["prompt"] and "## Request" not in seen["prompt"] and "The user's ideas" not in seen["prompt"]
    assert {"type": "ae.export.ready", "path": "renders/ae/promo_ae.zip"} in events
    assert zipfile.ZipFile(project / "renders" / "ae" / "promo_ae.zip").namelist() == ["promo_ae/Promo_Rebuild.jsx"]


def test_the_skills_gate_commands_pass_the_agent_sandbox(tmp_path: Path):
    from services.worker.sandbox_policy import ProjectSandboxPolicy

    policy = ProjectSandboxPolicy(tmp_path)
    assert policy.bash_allowed("node .claude/skills/ae-builder/scripts/ae_mock_dryrun.js exports/ae/promo/Promo_Rebuild.jsx --set DUMP_KEYS=exports/ae/promo/keys.json")
    assert policy.bash_allowed("python .claude/skills/ae-builder/scripts/verify_curves.py exports/ae/promo/keys.json exports/ae/promo/checks.json")
    # The env-prefix form the skill documents is what the sandbox rejects, hence --set.
    assert not policy.bash_allowed("DUMP_KEYS=keys.json node .claude/skills/ae-builder/scripts/ae_mock_dryrun.js Build.jsx")
