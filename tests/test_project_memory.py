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
