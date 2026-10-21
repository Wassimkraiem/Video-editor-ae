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


def test_restarted_worker_releases_jobs_it_was_running():
    import asyncio

    from services.worker.handlers import failure_event
    from services.worker.jobs import INTERRUPTED, PostgresJobQueue

    rows = [
        {"id": "j1", "type": "style_extraction", "payload": {"extraction_id": "x1"}, "attempts": 1},
        {"id": "j2", "type": "render", "payload": {"render_id": "r1"}, "attempts": 1},
    ]
    updates: list[dict] = []

    class Result:
        def mappings(self):
            return iter(rows)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, statement, params):
            if str(statement).startswith("UPDATE"):
                updates.append(params)
            else:
                assert params == {"worker_id": "local-worker"}
            return Result()

        async def commit(self):
            pass

    dead = asyncio.run(PostgresJobQueue(lambda: Session()).recover("local-worker", {"agent_run", "style_extraction"}))
    # Credit-spending jobs are not repeated behind the user's back; renders are.
    assert {update["id"]: update["status"] for update in updates} == {"j1": "dead", "j2": "queued"}
    assert [job.id for job in dead] == ["j1"]
    assert failure_event(dead[0], INTERRUPTED) == ("x1", {"type": "style.failed", "error": INTERRUPTED})


def test_skill_frontmatter_with_a_colon_in_the_description_is_repaired(tmp_path):
    from services.worker.skill_parser import parse_skill, repair_skill_file

    # The perfect-caption clone failed to install on exactly this line.
    description = 'Edit a clip with "perfect-caption" captions — a stacked caption block on the chest: small white Inter lead-in words, ONE huge keyword. Use whenever the user says "perfect caption".'
    skill = tmp_path / "SKILL.md"
    skill.write_text(f"---\nname: perfect-caption\ndescription: {description}\n---\n\n# perfect-caption\nBody: stays as written.\n", encoding="utf-8")
    assert parse_skill(skill).frontmatter.description == description
    assert repair_skill_file(skill)
    assert skill.read_text(encoding="utf-8").endswith("# perfect-caption\nBody: stays as written.\n")
    assert not repair_skill_file(skill)  # already valid: left alone
    assert parse_skill(skill).frontmatter.description == description

    valid = tmp_path / "valid" / "SKILL.md"
    valid.parent.mkdir()
    original = '---\nname: ok\ndescription: "Already: quoted"\ntags: [a, b]\n---\nbody\n'
    valid.write_text(original, encoding="utf-8")
    assert not repair_skill_file(valid) and valid.read_text(encoding="utf-8") == original
