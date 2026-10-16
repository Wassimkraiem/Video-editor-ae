from pathlib import Path

import pytest

from worker.quality_harness.models import ProjectProfile
from worker.quality_harness.project_memory import append_project_memory, create_project_memory, load_project_settings


def test_memory_is_created_and_loaded_from_project(tmp_path: Path):
    path = create_project_memory(tmp_path, ProjectProfile(brand_name="Acme", colors=["#fff"], banned_words=["cheap"]))
    assert path.read_text(encoding="utf-8").find("Acme") >= 0
    assert load_project_settings(tmp_path)["setting_sources"] == ["project"]


def test_existing_memory_is_not_overwritten_and_append_requires_approval(tmp_path: Path):
    path = create_project_memory(tmp_path)
    original = path.read_text(encoding="utf-8")
    create_project_memory(tmp_path, ProjectProfile(brand_name="Changed"))
    assert path.read_text(encoding="utf-8") == original
    with pytest.raises(PermissionError):
        append_project_memory(tmp_path, "- New rule", approved=False)
    append_project_memory(tmp_path, "- New rule", approved=True)
    assert "New rule" in path.read_text(encoding="utf-8")


def test_skill_script_edits_reach_existing_projects(tmp_path):
    from services.worker.project_bootstrap import install_skills

    source = tmp_path / "skills"
    (source / "demo" / "scripts").mkdir(parents=True)
    (source / "demo" / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
    script = source / "demo" / "scripts" / "transcribe.py"
    script.write_text("v1", encoding="utf-8")
    project = tmp_path / "project" / ".claude" / "skills"
    assert install_skills(project, [source]) == ["demo"]
    assert install_skills(project, [source]) == []
    script.write_text("v2", encoding="utf-8")  # SKILL.md unchanged
    assert install_skills(project, [source]) == ["demo"]
    assert (project / "demo" / "scripts" / "transcribe.py").read_text(encoding="utf-8") == "v2"
