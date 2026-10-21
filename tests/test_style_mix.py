from pathlib import Path

from fastapi.testclient import TestClient

from services.api.main import app, repo
from services.worker.fast_edit import FastManifest, combine_rule, fast_engine
from services.worker.handlers import skills_for
from services.worker.project_bootstrap import SKILLS_ROOT, bootstrap_project


def login(client: TestClient) -> dict[str, str]:
    repo.users.clear()
    token = client.post("/api/v1/auth/register", json={"email": "mix@example.com", "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_caption_style_adds_its_docs_to_the_generic_plan(tmp_path: Path):
    project = bootstrap_project(tmp_path / "project")
    skills = project / ".claude" / "skills"
    manifest = FastManifest.for_style(skills / "wassim-style", generic=True)
    manifest.caption_dir = skills / "talking-head-glass-edit"
    spec = manifest.spec()
    assert '<doc path="@style/SKILL.md">' in spec and "name: wassim-style" in spec
    assert '<doc path="captions/talking-head-glass-edit/SKILL.md">' in spec and "name: talking-head-glass-edit" in spec
    rule = combine_rule("wassim-style", "talking-head-glass-edit")
    assert "Captions (font, size, colours, position" in rule and "`talking-head-glass-edit`" in rule and "everything else" in rule
    assert combine_rule("wassim-style", None) == ""


def test_the_agent_loads_both_styles(tmp_path: Path):
    project = bootstrap_project(tmp_path / "project")
    names = skills_for(project, "wassim-style", "talking-head-glass-edit")
    assert names[:2] == ["wassim-style", "talking-head-glass-edit"]
    assert skills_for(project, "wassim-style", "wassim-style").count("wassim-style") == 1


def test_auto_style_is_a_fast_style_on_the_generic_engine():
    assert fast_engine(SKILLS_ROOT / "library" / "auto-style") == "generic"


def test_runs_carry_the_caption_style_and_brand_kit():
    with TestClient(app) as client:
        headers = login(client)
        assert any(skill["name"] == "auto-style" for skill in client.get("/api/v1/skills", headers=headers).json())
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Mix"}).json()["id"]
        repo.jobs.clear()
        body = {"brief": "Highlight the price", "skill": "wassim-style", "caption_skill": "talking-head-glass-edit", "kind": "motion",
                "brand": {"colors": ["#ff5a1f", "#111827"], "fonts": ["Montserrat"], "notes": "No emojis"}}
        run = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json=body)
        assert run.status_code == 202
        payload = repo.jobs[-1]["payload"]
        assert payload["caption_skill"] == "talking-head-glass-edit" and payload["brand"]["colors"] == ["#FF5A1F", "#111827"]
        # Same style twice is just that style.
        client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={**body, "caption_skill": "wassim-style"})
        assert repo.jobs[-1]["payload"]["caption_skill"] is None
        assert client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={**body, "caption_skill": "no-such-style"}).status_code == 422
        assert client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={**body, "brand": {"colors": ["red"]}}).status_code == 422


MARKETING_STYLES = ["performance-ad", "ui-feature-reel", "three-step-promo", "kinetic-type-recap", "teaser-countdown", "offer-ad", "testimonial-proof", "listicle-explainer", "auto-style"]


def test_marketing_styles_parse_and_run_on_the_generic_engine():
    from services.worker.skill_parser import parse_skill

    for name in MARKETING_STYLES:
        folder = SKILLS_ROOT / "library" / name
        package = parse_skill(folder / "SKILL.md")
        assert package.frontmatter.name == name and len(package.frontmatter.description) > 80
        assert fast_engine(folder) == "generic"
        assert len((folder / "SKILL.md").read_text(encoding="utf-8")) < 60_000  # fits the planner's doc budget
