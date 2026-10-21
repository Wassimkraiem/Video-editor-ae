import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.main import app, project_dir, repo, settings
from services.worker import skill_previews
from services.worker.handlers import WorkerContext, keep_as_preview

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def make_video(path: Path, seconds: int = 3) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=1080x1920:rate=30:duration={seconds}", "-f", "lavfi", "-i", f"sine=duration={seconds}",
                    "-shortest", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def login(client: TestClient) -> dict[str, str]:
    repo.users.clear()
    token = client.post("/api/v1/auth/register", json={"email": "previews@example.com", "password": "correct horse battery staple"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@needs_ffmpeg
def test_a_video_becomes_a_light_trailer_and_cover(tmp_path: Path):
    folder = skill_previews.install_preview(tmp_path, "offer-ad", make_video(tmp_path / "render.mp4"))
    assert (folder / "preview.mp4").stat().st_size > 0 and (folder / "cover.jpg").stat().st_size > 0
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width", "-of", "csv=p=0", str(folder / "preview.mp4")], capture_output=True, text=True).stdout
    assert probe.strip() == "720"


@needs_ffmpeg
def test_first_video_in_a_style_becomes_its_trailer_but_not_later_ones(tmp_path: Path):
    context = WorkerContext(tmp_path, tmp_path / "storage")
    first, second = make_video(tmp_path / "a.mp4", 2), make_video(tmp_path / "b.mp4", 4)
    asyncio.run(keep_as_preview(context, {"skill": "offer-ad"}, first))
    cover = (tmp_path / skill_previews.PREVIEWS_DIR / "offer-ad" / "cover.jpg").read_bytes()
    asyncio.run(keep_as_preview(context, {"skill": "offer-ad"}, second))
    assert (tmp_path / skill_previews.PREVIEWS_DIR / "offer-ad" / "cover.jpg").read_bytes() == cover
    # A demo requested for the style always replaces it; a mixed-style video never sets one.
    asyncio.run(keep_as_preview(context, {"skill": "offer-ad", "preview_for": "offer-ad"}, second))
    assert (tmp_path / skill_previews.PREVIEWS_DIR / "offer-ad" / "cover.jpg").read_bytes() != cover
    asyncio.run(keep_as_preview(context, {"skill": "performance-ad", "caption_skill": "offer-ad"}, first))
    assert not skill_previews.has_preview(tmp_path, "performance-ad")


def test_styles_list_signed_trailer_links_and_requests_are_queued():
    root = Path(settings.projects_root)
    folder = root / skill_previews.PREVIEWS_DIR / "kinetic-type-recap"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "preview.mp4").write_bytes(b"video")
    (folder / "cover.jpg").write_bytes(b"jpeg")
    with TestClient(app) as client:
        headers = login(client)
        styles = {skill["name"]: skill for skill in client.get("/api/v1/skills", headers=headers).json()}
        recap = styles["kinetic-type-recap"]
        assert recap["preview_url"].startswith("/api/v1/skill-previews/kinetic-type-recap/preview.mp4?expires=") and recap["cover_url"]
        assert styles["offer-ad"].get("preview_url") is None
        assert client.get(recap["preview_url"]).content == b"video"
        assert client.get("/api/v1/skill-previews/kinetic-type-recap/preview.mp4?expires=9999999999&signature=bad").status_code == 403
        assert client.get("/api/v1/skill-previews/kinetic-type-recap/edit.json").status_code == 404

        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Mine"}).json()["id"]
        render = project_dir(project_id) / "renders" / "promo.mp4"
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b"x")
        repo.jobs.clear()
        assert client.post("/api/v1/skills/offer-ad/preview", headers=headers, json={"project_id": project_id, "path": "renders/promo.mp4"}).status_code == 202
        assert repo.jobs[-1]["type"] == "skill_preview" and repo.jobs[-1]["payload"]["path"] == "renders/promo.mp4"
        assert client.post("/api/v1/skills/offer-ad/preview", headers=headers, json={"project_id": project_id, "path": "../../etc/passwd"}).status_code == 404

        run = client.post("/api/v1/skills/ui-feature-reel/preview/generate", headers=headers)
        assert run.status_code == 202 and run.json()["skill"] == "ui-feature-reel"
        job = repo.jobs[-1]["payload"]
        assert job["preview_for"] == "ui-feature-reel" and job["mode"] == "fast" and "Pulse" in job["prompt"]
        previews = [project for project in client.get("/api/v1/projects", headers=headers).json() if project["name"] == "Style previews"]
        assert len(previews) == 1
        client.post("/api/v1/skills/offer-ad/preview/generate", headers=headers)
        assert len([project for project in client.get("/api/v1/projects", headers=headers).json() if project["name"] == "Style previews"]) == 1
        assert client.post("/api/v1/skills/hyperframes/preview/generate", headers=headers).status_code == 404
