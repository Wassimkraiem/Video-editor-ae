import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.main import app, project_dir, repo
from services.api.repository import now
from services.worker import manual_edit
from services.worker.manual_edit import CaptionLine, Clip, EditDoc, TextLayer

WORDS = [
    {"text": "one", "start_ms": 0, "end_ms": 300},
    {"text": "two", "start_ms": 300, "end_ms": 600},
    {"text": "three.", "start_ms": 600, "end_ms": 900},
    {"text": "cut", "start_ms": 1000, "end_ms": 1400},
    {"text": "four", "start_ms": 2000, "end_ms": 2300},
    {"text": "five", "start_ms": 2300, "end_ms": 2600},
]


def test_captions_follow_the_cuts():
    # Keep 0-0.95 s and 2-3 s: "cut" is dropped and "four five" slides left.
    clips = [Clip(asset_id="a", in_ms=0, out_ms=950), Clip(asset_id="a", in_ms=2000, out_ms=3000)]
    lines = manual_edit.captions_from_words(clips, {"a": WORDS})
    assert [(line.text, line.start_ms, line.end_ms) for line in lines] == [("one two three.", 0, 900), ("four five", 950, 1550)]


def test_long_runs_and_pauses_split_lines():
    words = [{"text": f"w{index}", "start_ms": index * 300, "end_ms": index * 300 + 250} for index in range(6)]
    words.append({"text": "later", "start_ms": 4000, "end_ms": 4300})
    lines = manual_edit.captions_from_words([Clip(asset_id="a", in_ms=0, out_ms=5000)], {"a": words}, max_words=4)
    assert [line.text for line in lines] == ["w0 w1 w2 w3", "w4 w5", "later"]


def test_ass_script_places_captions_and_texts():
    doc = EditDoc(width=1080, height=1920, clips=[Clip(asset_id="a", in_ms=0, out_ms=3000)],
                  captions=[CaptionLine(text="hello {world}", start_ms=0, end_ms=1000)],
                  texts=[TextLayer(text="Price\n99 DT", start_ms=500, end_ms=2500, x=0.5, y=0.25, color="#FFCC00", background="#000000")])
    script = manual_edit.build_ass(doc)
    assert "PlayResY: 1920" in script
    assert "Dialogue: 1,0:00:00.00,0:00:01.00,Caption,,0,0,0,,{\\an5\\pos(540,1498)}hello (world)" in script
    assert "{\\an5\\pos(540,480)}Price\\N99 DT" in script
    assert "&H0000CCFF" in script  # #FFCC00 as ASS BGR
    doc.caption_style.enabled = False
    doc.texts = []
    assert manual_edit.build_ass(doc) is None


def test_export_command_concats_clips_and_chains_audio(tmp_path: Path):
    doc = EditDoc(width=720, height=1280, clips=[Clip(asset_id="a", in_ms=1000, out_ms=2500, volume=1.5), Clip(asset_id="b", in_ms=0, out_ms=1000)])
    doc.audio.normalize = doc.audio.denoise = True
    doc.audio.fade_out_ms = 500
    argv = manual_edit.export_command(doc, {"a": tmp_path / "a.mp4", "b": tmp_path / "b.mp4"}, {"b": False}, tmp_path / "out.mp4", subtitles="overlay.ass")
    assert argv[argv.index("-ss") + 1] == "1.000" and argv[argv.index("-t") + 1] == "1.500"
    graph = argv[argv.index("-filter_complex") + 1]
    assert "volume=1.500" in graph and "anullsrc" in graph  # clip b has no audio track
    assert "concat=n=2:v=1:a=1" in graph and "[vcat]ass=overlay.ass[vout]" in graph
    assert "afftdn" in graph and "loudnorm" in graph and "afade=t=out:st=2.000:d=0.500" in graph


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_export_renders_a_real_video(tmp_path: Path):
    source = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x568:rate=25:duration=3", "-f", "lavfi", "-i", "sine=duration=3", "-shortest", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True)
    doc = EditDoc(width=320, height=568, fps=25, clips=[Clip(asset_id="a", in_ms=0, out_ms=1000), Clip(asset_id="a", in_ms=2000, out_ms=3000)],
                  captions=[CaptionLine(text="hello", start_ms=0, end_ms=900)], texts=[TextLayer(text="TITLE", start_ms=0, end_ms=2000)])
    doc.audio.normalize = True
    (tmp_path / "overlay.ass").write_text(manual_edit.build_ass(doc), encoding="utf-8")
    output = tmp_path / "out.mp4"
    subprocess.run(manual_edit.export_command(doc, {"a": source}, {"a": True}, output, subtitles="overlay.ass"), cwd=tmp_path, check=True, capture_output=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)], check=True, capture_output=True, text=True).stdout)
    assert abs(float(probe["format"]["duration"]) - 2.0) < 0.15
    assert {stream["codec_type"] for stream in probe["streams"]} == {"video", "audio"}


def test_manual_edit_api_round_trip():
    with TestClient(app) as client:
        repo.users.clear()
        token = client.post("/api/v1/auth/register", json={"email": "manual@example.com", "password": "correct horse battery staple"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Manual"}).json()["id"]
        repo.assets["clip-1"] = {"id": "clip-1", "project_id": project_id, "filename": "a.mp4", "kind": "video", "role": "clip", "storage_key": f"projects/{project_id}/raw/a.mp4", "status": "ready",
                                 "probe": {"duration_ms": 3000, "width": 1080, "height": 1920, "fps": 30, "has_audio": True}, "created_at": now()}
        words = project_dir(project_id) / "proxies" / "clip-1" / "transcript.json"
        words.parent.mkdir(parents=True, exist_ok=True)
        words.write_text(json.dumps(WORDS), encoding="utf-8")

        created = client.post(f"/api/v1/projects/{project_id}/edits", headers=headers, json={"name": "Promo", "asset_ids": ["clip-1"]})
        assert created.status_code == 201
        doc = created.json()
        assert (doc["width"], doc["height"]) == (1080, 1920) and doc["clips"][0]["out_ms"] == 3000
        assert doc["captions"][0]["text"] == "one two three."

        doc["clips"] = [{**doc["clips"][0], "out_ms": 1500}]
        saved = client.put(f"/api/v1/projects/{project_id}/edits/{doc['id']}", headers=headers, json=doc)
        assert saved.status_code == 200 and saved.json()["clips"][0]["out_ms"] == 1500
        assert [line["text"] for line in client.post(f"/api/v1/projects/{project_id}/edits/{doc['id']}/captions", headers=headers).json()["captions"]] == ["one two three.", "cut"]

        stranger = {**doc, "clips": [{**doc["clips"][0], "asset_id": "someone-elses"}]}
        assert client.put(f"/api/v1/projects/{project_id}/edits/{doc['id']}", headers=headers, json=stranger).status_code == 422

        repo.jobs.clear()
        render = client.post(f"/api/v1/projects/{project_id}/edits/{doc['id']}/render", headers=headers)
        assert render.status_code == 202
        job = repo.jobs[-1]
        assert job["type"] == "manual_render" and job["payload"]["sources"] == {"clip-1": f"projects/{project_id}/raw/a.mp4"}
        assert [item["id"] for item in client.get(f"/api/v1/projects/{project_id}/edits", headers=headers).json()] == [doc["id"]]
        assert client.delete(f"/api/v1/projects/{project_id}/edits/{doc['id']}", headers=headers).status_code == 204
        assert client.get(f"/api/v1/projects/{project_id}/edits/{doc['id']}", headers=headers).status_code == 404
