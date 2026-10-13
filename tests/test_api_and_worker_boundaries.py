import asyncio
import zipfile
from pathlib import Path

from services.worker.jobs import InMemoryJobQueue
from services.worker.media import ffprobe_command, loudness_normalize_command
from services.worker.skill_parser import parse_skill, validate_skill_archive


def test_job_queue_claims_once_and_retries():
    queue = InMemoryJobQueue()
    job = queue.enqueue("ingest", {"asset_id": "a1"})
    assert queue.claim("worker-a") is job
    assert queue.claim("worker-b") is None
    queue.fail(job, "probe failed")
    assert job.status == "queued"


def test_media_commands_are_typed_argv():
    assert ffprobe_command("clip.mp4").argv[0] == "ffprobe"
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in loudness_normalize_command("a.mp4", "b.mp4").argv


def test_skill_parser_and_archive_validation(tmp_path: Path):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo skill\n---\n\nDo the edit.\n", encoding="utf-8")
    parsed = parse_skill(skill_dir / "SKILL.md")
    assert parsed.frontmatter.name == "demo"
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(skill_dir / "SKILL.md", "SKILL.md")
    assert validate_skill_archive(archive).frontmatter.description == "Demo skill"
