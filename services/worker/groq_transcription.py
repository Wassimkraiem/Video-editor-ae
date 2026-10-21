"""Transcription through Groq's hosted Whisper, with local faster-whisper as the fallback.

``TRANSCRIBER=groq`` (the default when ``GROQ_API_KEY`` is set) sends the clip's
audio to Groq as 16 kHz mono FLAC, in chunks that stay under the free tier's
25 MB upload cap. Any Groq failure (no key, rate limit, network) falls back
to the local model, so a transcript never fails because of the API.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from .transcription import FasterWhisperTranscriber, TranscriptWord

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3"
# 10-minute FLAC chunks are ~5 MB: far under the 25 MB cap, few requests.
CHUNK_SECONDS = 600
# Groq caps the prompt at 224 tokens; Arabic script costs several per word.
PROMPT_CHARS = 400


def probe_seconds(path: Path) -> float:
    completed = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(completed.stdout.strip() or 0)


def flac_chunks(audio_path: Path, folder: Path, chunk_seconds: int = CHUNK_SECONDS) -> list[tuple[Path, float]]:
    """The audio as 16 kHz mono FLAC pieces, each with its start offset in seconds."""

    total = probe_seconds(audio_path)
    chunks = []
    start = 0.0
    while start < total or not chunks:
        target = folder / f"chunk{len(chunks):03d}.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", str(chunk_seconds), "-i", str(audio_path), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(target)], check=True, capture_output=True)
        chunks.append((target, start))
        start += chunk_seconds
    return chunks


def words_from_response(payload: dict[str, Any], offset_s: float, first_id: int) -> list[TranscriptWord]:
    """Groq's verbose_json words, placed on the clip's timeline.

    Words carry no segment; each gets the index of the segment whose time
    span contains it, so line breaks follow Whisper's phrasing like the local model.
    """

    segments = payload.get("segments") or []
    words = []
    for item in payload.get("words") or []:
        text = str(item.get("word", "")).strip()
        if not text:
            continue
        start, end = float(item["start"]), float(item["end"])
        segment = next((index for index, part in enumerate(segments) if float(part.get("start", 0)) - 0.05 <= start < float(part.get("end", 0)) + 0.05), max(len(segments) - 1, 0))
        words.append(TranscriptWord(id=f"w{first_id + len(words)}", text=text, start_ms=round((offset_s + start) * 1000), end_ms=round((offset_s + end) * 1000), segment=segment))
    return words


def _multipart(fields: list[tuple[str, str]], file_field: str, path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    crlf = "\r\n"
    parts = [f"--{boundary}{crlf}Content-Disposition: form-data; name=\"{name}\"{crlf}{crlf}{value}{crlf}".encode() for name, value in fields]
    parts.append(f"--{boundary}{crlf}Content-Disposition: form-data; name=\"{file_field}\"; filename=\"{path.name}\"{crlf}Content-Type: audio/flac{crlf}{crlf}".encode() + path.read_bytes() + crlf.encode())
    parts.append(f"--{boundary}--{crlf}".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class GroqTranscriber:
    def __init__(self, api_key: str, model: str = DEFAULT_GROQ_MODEL, *, retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.retries = retries

    def _request(self, path: Path, language: str | None, prompt: str | None) -> dict[str, Any]:
        fields = [("model", self.model), ("response_format", "verbose_json"), ("temperature", "0"), ("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment")]
        if language:
            fields.append(("language", language))
        if prompt:
            fields.append(("prompt", prompt[:PROMPT_CHARS]))
        body, content_type = _multipart(fields, "file", path)
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": content_type, "User-Agent": "video-editor-studio"})
            try:
                with urllib.request.urlopen(request, timeout=300) as reply:
                    return json.loads(reply.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:300]
                # Rate limited: wait as told (briefly) and try again.
                if error.code == 429 and attempt < self.retries:
                    time.sleep(min(float(error.headers.get("retry-after") or 5), 30))
                    continue
                raise RuntimeError(f"Groq transcription failed ({error.code}): {detail}") from error
        raise RuntimeError("Groq transcription failed: rate limited")

    def transcribe(self, audio_path: str, language: str | None = None, prompt: str | None = None) -> tuple[list[TranscriptWord], str | None]:
        words: list[TranscriptWord] = []
        detected = None
        segment_base = 0
        with tempfile.TemporaryDirectory(prefix="groq-") as scratch:
            for chunk, offset in flac_chunks(Path(audio_path), Path(scratch)):
                payload = self._request(chunk, language, prompt)
                detected = detected or payload.get("language")
                piece = [replace(word, segment=word.segment + segment_base) for word in words_from_response(payload, offset, len(words))]
                segment_base += len(payload.get("segments") or []) or 1
                words.extend(piece)
        return words, detected


class FallbackTranscriber:
    """Try the hosted transcriber; on any failure use the local model."""

    def __init__(self, primary: Any, fallback: Any):
        self.primary = primary
        self.fallback = fallback

    def transcribe(self, audio_path: str, language: str | None = None, prompt: str | None = None) -> tuple[list[TranscriptWord], str | None]:
        try:
            return self.primary.transcribe(audio_path, language, prompt)
        except Exception:
            logger.exception("hosted_transcription_failed; using local faster-whisper")
            return self.fallback.transcribe(audio_path, language, prompt)


def default_transcriber() -> Any:
    """Groq when configured (``TRANSCRIBER=groq`` or a key with no choice set), else local."""

    key = os.getenv("GROQ_API_KEY", "").strip()
    choice = os.getenv("TRANSCRIBER", "groq" if key else "local").strip().lower()
    if choice == "groq" and key:
        return FallbackTranscriber(GroqTranscriber(key, os.getenv("GROQ_WHISPER_MODEL", DEFAULT_GROQ_MODEL)), FasterWhisperTranscriber())
    if choice == "groq":
        logger.warning("TRANSCRIBER=groq but GROQ_API_KEY is not set; using local faster-whisper")
    return FasterWhisperTranscriber()
