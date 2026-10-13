"""Provider interfaces for word-timed transcription."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptWord:
    id: str
    text: str
    start_ms: int
    end_ms: int


class Transcriber(Protocol):
    def transcribe(self, audio_path: str) -> list[TranscriptWord]: ...


class OpenAITranscriber:
    """Adapter boundary for the OpenAI word-timestamp endpoint."""

    def __init__(self, client):
        self.client = client

    def transcribe(self, audio_path: str) -> list[TranscriptWord]:
        with open(audio_path, "rb") as audio:
            result = self.client.audio.transcriptions.create(model="gpt-4o-transcribe", file=audio, response_format="verbose_json", timestamp_granularities=["word"])
        return [TranscriptWord(id=f"word-{index}", text=item.word, start_ms=round(item.start * 1000), end_ms=round(item.end * 1000)) for index, item in enumerate(result.words)]


class FasterWhisperTranscriber:
    """Local adapter with the same interface as the hosted provider."""

    def __init__(self, model):
        self.model = model

    def transcribe(self, audio_path: str) -> list[TranscriptWord]:
        segments, _ = self.model.transcribe(audio_path, word_timestamps=True)
        words: list[TranscriptWord] = []
        for segment in segments:
            for word in segment.words or []:
                words.append(TranscriptWord(id=f"word-{len(words)}", text=word.word.strip(), start_ms=round(word.start * 1000), end_ms=round(word.end * 1000)))
        return words
