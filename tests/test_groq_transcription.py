import io
import json
import shutil
import subprocess
import urllib.error
from pathlib import Path

import pytest

from services.worker import groq_transcription as groq
from services.worker.transcription import FasterWhisperTranscriber, TranscriptWord

RESPONSE = {
    "language": "arabic",
    "segments": [{"id": 0, "start": 0.0, "end": 1.2, "text": "a b"}, {"id": 1, "start": 1.5, "end": 2.6, "text": "c"}],
    "words": [{"word": " إيجا", "start": 0.0, "end": 0.5}, {"word": "AI", "start": 0.6, "end": 1.1}, {"word": " ", "start": 1.1, "end": 1.2}, {"word": "خدمتك", "start": 1.6, "end": 2.4}],
}


def test_words_are_placed_on_the_clip_timeline_with_their_segment():
    words = groq.words_from_response(RESPONSE, offset_s=600, first_id=10)
    assert [(word.id, word.text, word.start_ms, word.end_ms, word.segment) for word in words] == [
        ("w10", "إيجا", 600000, 600500, 0), ("w11", "AI", 600600, 601100, 0), ("w12", "خدمتك", 601600, 602400, 1),
    ]


def test_request_sends_word_timestamps_language_and_a_short_prompt(tmp_path: Path, monkeypatch):
    chunk = tmp_path / "chunk.flac"
    chunk.write_bytes(b"fLaC")
    sent = {}

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        sent["url"], sent["auth"], sent["body"] = request.full_url, request.headers["Authorization"], request.data
        return Reply(json.dumps(RESPONSE).encode())

    monkeypatch.setattr(groq.urllib.request, "urlopen", fake_urlopen)
    payload = groq.GroqTranscriber("gsk_test")._request(chunk, "ar", "x" * 1000)
    body = sent["body"].decode("latin-1")
    assert sent["url"] == groq.ENDPOINT and sent["auth"] == "Bearer gsk_test" and payload["language"] == "arabic"
    assert 'name="model"\r\n\r\nwhisper-large-v3\r\n' in body and 'name="response_format"\r\n\r\nverbose_json' in body
    assert body.count('name="timestamp_granularities[]"') == 2 and 'name="language"\r\n\r\nar\r\n' in body
    assert "x" * groq.PROMPT_CHARS + "\r\n" in body and "x" * (groq.PROMPT_CHARS + 1) not in body


def test_rate_limit_is_retried_then_reported(tmp_path: Path, monkeypatch):
    chunk = tmp_path / "chunk.flac"
    chunk.write_bytes(b"fLaC")
    calls = []

    def limited(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {"retry-after": "0"}, io.BytesIO(b'{"error":"rate"}'))

    monkeypatch.setattr(groq.urllib.request, "urlopen", limited)
    monkeypatch.setattr(groq.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="429"):
        groq.GroqTranscriber("gsk_test", retries=2)._request(chunk, None, None)
    assert len(calls) == 3


def test_a_groq_failure_falls_back_to_the_local_model():
    class Broken:
        def transcribe(self, *args):
            raise RuntimeError("network down")

    class Local:
        def transcribe(self, audio_path, language=None, prompt=None):
            return [TranscriptWord(id="w0", text="ok", start_ms=0, end_ms=100)], "ar"

    words, language = groq.FallbackTranscriber(Broken(), Local()).transcribe("clip.wav", "ar", None)
    assert [word.text for word in words] == ["ok"] and language == "ar"


def test_transcriber_choice_follows_the_environment(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("TRANSCRIBER", raising=False)
    assert isinstance(groq.default_transcriber(), FasterWhisperTranscriber)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    chosen = groq.default_transcriber()
    assert isinstance(chosen, groq.FallbackTranscriber) and isinstance(chosen.primary, groq.GroqTranscriber)
    monkeypatch.setenv("TRANSCRIBER", "local")
    assert isinstance(groq.default_transcriber(), FasterWhisperTranscriber)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_long_audio_is_split_into_small_flac_chunks(tmp_path: Path):
    audio = tmp_path / "audio.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=5", "-ar", "48000", "-ac", "2", str(audio)], check=True)
    chunks = groq.flac_chunks(audio, tmp_path, chunk_seconds=2)
    assert [offset for _, offset in chunks] == [0, 2, 4]
    assert all(path.suffix == ".flac" and path.stat().st_size > 0 for path, _ in chunks)
