import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.event_state import record_event
from services.api.main import app, project_dir, repo
from services.worker.transcription import TranscriptWord, transcribe_to_folder


class FakeTranscriber:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio_path, language=None, prompt=None):
        self.calls.append((language, prompt))
        return [TranscriptWord("w0", "هيا", 0, 120, 0), TranscriptWord("w1", "AI", 120, 540, 0)], "ar"


def test_transcription_writes_studio_and_skill_formats(tmp_path: Path):
    fake = FakeTranscriber()
    result = transcribe_to_folder(tmp_path / "audio.wav", tmp_path, transcriber=fake, vocabulary="Kachabiti")
    assert (result["language"], result["words"]) == ("tn", 2)
    # Tunisian mode: Whisper runs as Arabic with the Darija prompt plus vocabulary.
    assert fake.calls[0][0] == "ar" and "برشا" in fake.calls[0][1] and fake.calls[0][1].endswith("Kachabiti")
    assert (tmp_path / "transcript.raw.json").is_file()
    assert json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))[1]["text"] == "AI"
    assert json.loads((tmp_path / "words.json").read_text(encoding="utf-8")) == [{"t": "هيا", "s": 0.0, "e": 0.12}, {"t": "AI", "s": 0.12, "e": 0.54}]
    assert json.loads((tmp_path / "transcript.meta.json").read_text(encoding="utf-8"))["reviewed"] is False


def test_user_corrections_are_saved_and_mark_the_clip_reviewed():
    with TestClient(app) as client:
        repo.users.clear()
        token = client.post("/api/v1/auth/register", json={"email": "words@example.com", "password": "correct horse battery staple"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Words"}).json()["id"]
        asset_id = client.post(f"/api/v1/projects/{project_id}/assets", headers=headers, files={"file": ("clip.mp4", b"x", "video/mp4")}).json()["id"]
        transcribe_to_folder(Path("audio.wav"), project_dir(project_id) / "proxies" / asset_id, transcriber=FakeTranscriber())
        record_event(repo, project_id, {"type": "transcribe.completed", "asset_id": asset_id, "language": "ar"})

        loaded = client.get(f"/api/v1/assets/{asset_id}/transcript", headers=headers).json()
        assert [word["text"] for word in loaded["words"]] == ["هيا", "AI"] and not loaded["reviewed"]

        words = loaded["words"]
        words[1]["text"] = "الـAI"
        words.append({"id": "w2", "text": "  ", "start_ms": 600, "end_ms": 700, "segment": 0})  # blank words are dropped
        saved = client.put(f"/api/v1/assets/{asset_id}/transcript", headers=headers, json={"words": words})
        assert saved.status_code == 200 and saved.json()["reviewed"]
        skill_words = json.loads((project_dir(project_id) / "proxies" / asset_id / "words.json").read_text(encoding="utf-8"))
        assert [word["t"] for word in skill_words] == ["هيا", "الـAI"]
        asset = next(item for item in client.get(f"/api/v1/projects/{project_id}/assets", headers=headers).json() if item["id"] == asset_id)
        assert asset["transcript_reviewed"] and asset["transcript_status"] == "ready"

        bad = [{"id": "w0", "text": "x", "start_ms": 500, "end_ms": 100}]
        assert client.put(f"/api/v1/assets/{asset_id}/transcript", headers=headers, json={"words": bad}).status_code == 422

        repo.jobs.clear()
        assert client.post(f"/api/v1/assets/{asset_id}/transcribe", headers=headers, json={"language": "ar"}).status_code == 202
        assert repo.jobs[-1]["type"] == "transcribe" and repo.jobs[-1]["payload"]["language"] == "ar"
        assert client.post(f"/api/v1/assets/{asset_id}/transcribe", headers=headers, json={"language": "arabic!"}).status_code == 422


def test_whisper_settings_per_language():
    from services.worker.transcription import whisper_settings

    assert whisper_settings("fr") == ("fr", None)
    assert whisper_settings("auto", "Notion") == (None, "Notion")
    assert whisper_settings(None)[0] == "ar"


def test_cleanup_spans_keep_timing_and_allow_merges():
    import pytest
    from services.worker.transcription import apply_spans

    words = [{"id": "w0", "text": "الـ", "start_ms": 0, "end_ms": 100, "segment": 0}, {"id": "w1", "text": "آيائي", "start_ms": 100, "end_ms": 500, "segment": 0}, {"id": "w2", "text": "برشا", "start_ms": 500, "end_ms": 900, "segment": 0}]
    merged = apply_spans(words, [[0, 1, "الـAI"], [2, 2, "برشا"]])
    assert merged[0] == {"id": "w0", "text": "الـAI", "start_ms": 0, "end_ms": 500, "segment": 0}
    assert merged[1]["start_ms"] == 500
    with pytest.raises(ValueError):
        apply_spans(words, [[0, 0, "x"], [2, 2, "y"]])  # skips a word
    with pytest.raises(ValueError):
        apply_spans(words, [[0, 2, "x"], [1, 1, "y"]])  # overlaps


def test_agent_brief_hands_over_the_reviewed_transcript(tmp_path: Path):
    from services.worker.agent_tools import TRANSCRIBING_MARKER, media_brief, pending_transcripts
    from services.worker.transcription import write_transcript

    folder = tmp_path / "proxies" / "a1"
    folder.mkdir(parents=True)
    (folder / "asset.json").write_text(json.dumps({"id": "a1", "filename": "protect.mp4", "path": "/work/raw/x-protect.mp4", "probe": {"duration_ms": 39600, "width": 1080, "height": 1920}}), encoding="utf-8")
    words = [
        {"id": "w0", "text": "خدمتك", "start_ms": 1340, "end_ms": 1900, "segment": 0},
        {"id": "w1", "text": "من", "start_ms": 1900, "end_ms": 2040, "segment": 0},
        {"id": "w2", "text": "الـAI", "start_ms": 2040, "end_ms": 2440, "segment": 0},
        {"id": "w3", "text": "c'est bon", "start_ms": 2600, "end_ms": 3100, "segment": 1},
    ]
    write_transcript(folder, words, language="tn", reviewed=True)
    brief = media_brief(tmp_path)
    assert "Clip `a1`: protect.mp4 (39.6s, 1080x1920)" in brief
    assert "REVIEWED and corrected by the user" in brief and "never re-transcribe" in brief and "Tunisian" in brief
    assert "[1.3-2.4] خدمتك من الـAI" in brief and "[2.6-3.1] c'est bon" in brief
    assert "proxies/a1/words.json" in brief

    assert pending_transcripts(tmp_path) == []
    (folder / TRANSCRIBING_MARKER).touch()
    assert pending_transcripts(tmp_path) == ["a1"]
