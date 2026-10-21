import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.main import app, repo, settings
from services.worker import handlers, skill_editing
from services.worker.handlers import WorkerContext, edit_skill
from services.worker.jobs import JobRecord
from services.worker.skill_parser import parse_skill
from services.worker.style_extraction import user_skills_root


def owner(client: TestClient) -> dict[str, str]:
    repo.users.clear()
    token = client.post("/api/v1/auth/register", json={"email": "skills@example.com", "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def user_style(projects_root: Path, name: str, description: str = "Old look") -> Path:
    folder = user_skills_root(projects_root) / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\nKeyword colour: orange.\n", encoding="utf-8")
    return folder


def test_built_in_styles_are_saved_under_a_new_name():
    with TestClient(app) as client:
        headers = owner(client)
        repo.jobs.clear()
        refused = client.post("/api/v1/skill-edits", headers=headers, json={"skill": "wassim-style", "request": "Make the keyword box yellow"})
        assert refused.status_code == 409 and "new name" in refused.json()["detail"]
        accepted = client.post("/api/v1/skill-edits", headers=headers, json={"skill": "wassim-style", "request": "Make the keyword box yellow", "save_as": "Wassim Yellow"})
        assert accepted.status_code == 202
        record = accepted.json()
        assert (record["kind"], record["name"], record["base"], record["status"]) == ("edit", "wassim-yellow", "wassim-style", "queued")
        job = repo.jobs[-1]
        assert job["type"] == "skill_edit" and job["payload"]["source"] == "wassim-style" and job["payload"]["request"] == "Make the keyword box yellow"
        assert client.post("/api/v1/skill-edits", headers=headers, json={"skill": "hyperframes", "request": "change it"}).status_code == 404
        assert client.post("/api/v1/skill-edits", headers=headers, json={"skill": "wassim-style", "request": "x yz", "save_as": "devin-style"}).status_code == 409


def test_edit_job_changes_a_copy_installs_it_and_keeps_the_old_version(tmp_path: Path, monkeypatch):
    projects_root = tmp_path / "projects"
    user_style(projects_root, "neon")

    class FakeAgent:
        """Stands in for the Claude session: edits the working copy as asked."""

        def __init__(self, workspace: Path):
            self.workspace = workspace

        async def run(self, brief: str, event_sink=None):
            assert "Make the keyword yellow" in brief and "skill-out/neon/" in brief
            skill = self.workspace / "skill-out" / "neon" / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8").replace("orange", "yellow").replace("Old look", "New look: yellow keyword"), encoding="utf-8")
            return type("Result", (), {"status": "succeeded"})()

    monkeypatch.setattr(handlers, "AgentSessionRunner", FakeAgent)
    events: list[tuple[str, dict]] = []
    context = WorkerContext(projects_root, tmp_path / "storage", event_sink=lambda stream, event: events.append((stream, event)))
    job = JobRecord(type="skill_edit", payload={"extraction_id": "e1", "source": "neon", "name": "neon", "request": "Make the keyword yellow"})
    result = asyncio.run(edit_skill(job, context))

    installed = user_skills_root(projects_root) / "neon" / "SKILL.md"
    assert "yellow" in installed.read_text(encoding="utf-8")
    # The agent's unquoted "New look: ..." description was repaired on install.
    assert parse_skill(installed).frontmatter.description == "New look: yellow keyword"
    assert result["name"] == "neon" and events[-1][1]["type"] == "style.completed"
    saved = skill_editing.versions(projects_root, "neon")
    assert len(saved) == 1 and "orange" in (saved[0] / "SKILL.md").read_text(encoding="utf-8")

    skill_editing.restore_previous(projects_root, "neon")
    assert "orange" in installed.read_text(encoding="utf-8") and skill_editing.versions(projects_root, "neon") == []


def test_a_failed_edit_leaves_the_installed_style_alone(tmp_path: Path, monkeypatch):
    projects_root = tmp_path / "projects"
    original = user_style(projects_root, "neon") / "SKILL.md"
    before = original.read_text(encoding="utf-8")

    class StoppedAgent:
        def __init__(self, workspace: Path):
            self.workspace = workspace

        async def run(self, brief: str, event_sink=None):
            (self.workspace / "skill-out" / "neon" / "SKILL.md").write_text("broken", encoding="utf-8")
            return type("Result", (), {"status": "failed"})()

    monkeypatch.setattr(handlers, "AgentSessionRunner", StoppedAgent)
    context = WorkerContext(projects_root, tmp_path / "storage")
    job = JobRecord(type="skill_edit", payload={"extraction_id": "e2", "source": "neon", "name": "neon", "request": "anything"})
    try:
        asyncio.run(edit_skill(job, context))
    except RuntimeError:
        pass
    else:
        raise AssertionError("a failed agent run must fail the job")
    assert original.read_text(encoding="utf-8") == before and skill_editing.versions(projects_root, "neon") == []


def test_saving_a_built_in_under_a_new_name_renames_the_copy(tmp_path: Path):
    source = skill_editing.skill_source_dir("wassim-style", tmp_path)
    copy = skill_editing.prepare_edit(tmp_path / "workspace", source, "wassim-yellow")
    assert parse_skill(copy / "SKILL.md").frontmatter.name == "wassim-yellow"
    assert (source / "SKILL.md").read_text(encoding="utf-8").count("name: wassim-style") == 1  # the original is untouched


def test_restore_endpoint_puts_the_previous_version_back():
    projects_root = Path(settings.projects_root).resolve()
    user_style(projects_root, "restore-me", "Version one")
    skill_editing.backup_installed(projects_root, "restore-me")
    user_style(projects_root, "restore-me", "Version two")
    with TestClient(app) as client:
        headers = owner(client)
        assert len(client.get("/api/v1/skills/restore-me/versions", headers=headers).json()) == 1
        restored = client.post("/api/v1/skills/restore-me/restore", headers=headers)
        assert restored.status_code == 200 and restored.json()["description"] == "Version one"
        assert client.post("/api/v1/skills/restore-me/restore", headers=headers).status_code == 404
