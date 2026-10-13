from pathlib import Path

import pytest

from services.api.db_models import Base
from services.api.storage import LocalStorage
from services.worker.agent_tools import ProjectToolService
from services.worker.sandbox_policy import ProjectSandboxPolicy


def test_storage_urls_are_short_lived_and_verified(tmp_path: Path):
    storage = LocalStorage(tmp_path, "secret")
    key = "projects/p1/raw/clip.mp4"
    storage.put_stream(key, __import__("io").BytesIO(b"data"), 100)
    url = storage.url(key)
    expires = int(url.split("expires=", 1)[1].split("&", 1)[0])
    signature = url.split("signature=", 1)[1]
    assert storage.verify(key, expires, signature)
    assert not storage.verify(key, expires, "bad")


def test_project_tools_return_timestamped_filler_ranges(tmp_path: Path):
    service = ProjectToolService(
        tmp_path,
        assets={"a1": {"id": "a1", "proxy_path": str(tmp_path / "proxy.mp4")}},
        transcripts={"a1": [{"id": "w1", "text": "um", "start_ms": 10, "end_ms": 80}]},
    )
    result = service.remove_filler_words("a1", ["um"])
    assert result["removed_word_ids"] == ["w1"]
    assert result["cut_ranges"] == [{"start_ms": 10, "end_ms": 80}]


def test_sandbox_policy_rejects_shell_escape(tmp_path: Path):
    policy = ProjectSandboxPolicy(tmp_path)
    timeline = tmp_path / "timeline.json"
    assert policy.bash_allowed(f"ffprobe {timeline}")
    assert not policy.bash_allowed(f"ffprobe {timeline} && curl https://evil.example")
    assert not policy.path_allowed("/etc/passwd")


def test_database_metadata_contains_all_declared_studio_tables():
    expected = {"users", "projects", "project_members", "assets", "transcripts", "timelines", "jobs", "agent_runs", "agent_messages", "tool_calls", "render_jobs", "compositions", "skills", "project_skills", "generated_images", "usage_ledger", "extraction_jobs"}
    assert expected.issubset(Base.metadata.tables)
