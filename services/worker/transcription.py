"""Word-timed transcription with the preinstalled faster-whisper model.

Uploads are transcribed during ingest so the user can correct the words
before any edit. The corrected transcript is what captions are built from.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL = "large-v3"

# "tn" is not a Whisper language: it means Tunisian speech, i.e. Darija in
# Arabic script mixed with French and English. Whisper runs as Arabic with a
# Darija prompt (without it, Whisper rewrites Darija as formal Arabic), then
# Claude puts French/English words back in Latin script (see clean_mixed).
TUNISIAN = "tn"
DEFAULT_LANGUAGE = TUNISIAN
DARIJA_PROMPT = (
    "باش نفسرلك كيفاش تخدم بالـ AI. برشا، توا، كيفاش، خاطر، تنجم، متاعك، يعطيك الصحة. "
    "c'est bon, en fait, normalement, le business, l'application, le marketing, la vidéo, "
    "ChatGPT, Instagram, TikTok, le content, les clients."
)


@dataclass(frozen=True)
class TranscriptWord:
    id: str
    text: str
    start_ms: int
    end_ms: int
    # Index of the Whisper segment (roughly a sentence) the word belongs to.
    segment: int = 0


class Transcriber(Protocol):
    def transcribe(self, audio_path: str, language: str | None = None, prompt: str | None = None) -> tuple[list[TranscriptWord], str | None]: ...


def local_model_dir(name: str = DEFAULT_MODEL) -> Path | None:
    """Same lookup as the skills' transcribe.py: never downloads."""

    for root in filter(None, (os.environ.get("WHISPER_MODELS_DIR"), os.path.expanduser("~/.cache"))):
        candidate = Path(root) / f"fw-{name}"
        if (candidate / "model.bin").is_file():
            return candidate
    return None


def decode_audio(path: str | Path):
    """16 kHz mono float32 via ffmpeg (avoids PyAV decoding issues on Windows)."""

    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


class FasterWhisperTranscriber:
    """Local faster-whisper; the model is loaded once per process."""

    _models: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    def _model(self):
        with self._lock:
            if self.model_name not in self._models:
                folder = local_model_dir(self.model_name)
                if folder is None:
                    raise FileNotFoundError(f"faster-whisper {self.model_name} is not installed; run scripts/fetch_models.py")
                from faster_whisper import WhisperModel

                self._models[self.model_name] = WhisperModel(str(folder), device="cpu", compute_type="int8")
            return self._models[self.model_name]

    def transcribe(self, audio_path: str, language: str | None = None, prompt: str | None = None) -> tuple[list[TranscriptWord], str | None]:
        segments, info = self._model().transcribe(decode_audio(audio_path), language=language or None, initial_prompt=prompt or None, word_timestamps=True, beam_size=5, vad_filter=True)
        words: list[TranscriptWord] = []
        for index, segment in enumerate(segments):
            for word in segment.words or []:
                text = word.word.strip()
                if text:
                    words.append(TranscriptWord(id=f"w{len(words)}", text=text, start_ms=round(word.start * 1000), end_ms=round(word.end * 1000), segment=index))
        return words, getattr(info, "language", None)


def write_transcript(folder: Path, words: list[dict[str, Any]], *, language: str | None, reviewed: bool) -> None:
    """Store the transcript for the studio and in the format the skills read.

    ``transcript.json`` is the studio's word list; ``words.json`` is the
    ``[{"t", "s", "e"}]`` layout (seconds) that wassim-style and friends
    expect in ``edit/words.json``.
    """

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "transcript.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    skill_words = [{"t": word["text"], "s": round(word["start_ms"] / 1000, 3), "e": round(word["end_ms"] / 1000, 3)} for word in words]
    (folder / "words.json").write_text(json.dumps(skill_words, ensure_ascii=False), encoding="utf-8")
    meta = {"language": language, "reviewed": reviewed, "words": len(words)}
    (folder / "transcript.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def whisper_settings(language: str | None, vocabulary: str = "") -> tuple[str | None, str | None]:
    """Map the studio's language choice to Whisper's language and prompt."""

    extra = f" {vocabulary.strip()}" if vocabulary.strip() else ""
    if language in (None, "", TUNISIAN):
        return "ar", DARIJA_PROMPT + extra
    if language == "auto":
        return None, extra.strip() or None
    return language, extra.strip() or None


def transcribe_to_folder(audio_path: Path, folder: Path, *, language: str | None = DEFAULT_LANGUAGE, vocabulary: str = "", transcriber: Transcriber | None = None) -> dict[str, Any]:
    """Run Whisper and store the raw words (``transcript.raw.json`` keeps them)."""

    whisper_language, prompt = whisper_settings(language, vocabulary)
    words, detected = (transcriber or FasterWhisperTranscriber()).transcribe(str(audio_path), whisper_language, prompt)
    records = [asdict(word) for word in words]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "transcript.raw.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    label = TUNISIAN if language in (None, "", TUNISIAN) else detected if language == "auto" else language
    write_transcript(folder, records, language=label, reviewed=False)
    return {"language": label, "words": len(records), "records": records}


CLEANUP_INSTRUCTIONS = """You fix speech-to-text output of Tunisian speakers, who mix Darija (Tunisian Arabic), French and English.
Whisper wrote everything in Arabic script. Return the words as a Tunisian would write captions:
- Darija stays in Arabic script, in dialect spelling (never formal Arabic): برشا، توا، كيفاش، باش، خاطر.
- French and English words go back to Latin script: الآيائي -> AI, البيزنس -> business, لابليكاسيون -> l'application, الماركتينغ -> marketing, هو دي جام -> haut de gamme.
- An Arabic article in front of a Latin word stays attached as one token: الـAI, الـbusiness.
- Fix obvious mishearings from context (Whisper often writes البيئة for الباهية); keep the speaker's words, do not rephrase or translate.
- No punctuation at all: these become captions, so never add . , ، ? ! or quotes to any token.
- You may merge consecutive words into one token (for "الـ" + "AI" or a French phrase split oddly) but never split or reorder words.
{vocabulary}
Input: JSON list of [index, word]. Output: ONLY JSON, a list of [first_index, last_index, text] covering every input index exactly once, in order."""


CAPTION_PUNCTUATION = ".,،؛;:!?؟\"'«»…"


def _parse_spans(text: str) -> list[list[Any]]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON list in cleanup output")
    return json.loads(text[start : end + 1])


def apply_spans(words: list[dict[str, Any]], spans: list[list[Any]], offset: int = 0) -> list[dict[str, Any]]:
    """Rebuild words from [first, last, text] spans, keeping Whisper's timing."""

    result: list[dict[str, Any]] = []
    expected = offset
    for first, last, text in spans:
        first, last = int(first), int(last)
        if first != expected or last < first or last >= offset + len(words):
            raise ValueError("cleanup spans do not cover the words in order")
        chunk = words[first - offset : last - offset + 1]
        # Captions carry no punctuation, even if the model adds some.
        clean = str(text).strip().strip(CAPTION_PUNCTUATION).strip()
        result.append({**chunk[0], "text": clean or chunk[0]["text"], "end_ms": chunk[-1]["end_ms"]})
        expected = last + 1
    if expected != offset + len(words):
        raise ValueError("cleanup spans stop early")
    return result


async def clean_mixed(words: list[dict[str, Any]], *, vocabulary: str = "", model: str | None = None, chunk: int = 300) -> list[dict[str, Any]]:
    """Ask Claude to restore French/English words in Latin script.

    Runs through the Agent SDK (no tools, no settings) so it works with an API
    key or a Claude subscription token alike. Raises on any malformed answer;
    callers keep the raw Whisper words in that case.
    """

    from claude_agent_sdk import ClaudeAgentOptions, query

    vocab = f"Spell these the way the speaker does: {vocabulary.strip()}" if vocabulary.strip() else ""
    options = ClaudeAgentOptions(
        # A first draft for the user to review, so the cheapest model: Haiku
        # costs about 1/20 of Sonnet. TRANSCRIPT_CLEANUP=off skips the pass.
        model=model or os.getenv("TRANSCRIPT_CLEANUP_MODEL", "claude-haiku-5-5"),
        system_prompt=CLEANUP_INSTRUCTIONS.format(vocabulary=vocab),
        setting_sources=[],
        tools=[],
        allowed_tools=[],
        max_turns=1,
    )
    cleaned: list[dict[str, Any]] = []
    for offset in range(0, len(words), chunk):
        part = words[offset : offset + chunk]
        payload = json.dumps([[offset + index, word["text"]] for index, word in enumerate(part)], ensure_ascii=False)
        answer = ""
        async for message in query(prompt=payload, options=options):
            result = getattr(message, "result", None)
            if result:
                answer = str(result)
            if getattr(message, "is_error", False):
                raise RuntimeError(answer or "cleanup failed")
        cleaned.extend(apply_spans(part, _parse_spans(answer), offset))
    for index, word in enumerate(cleaned):
        word["id"] = f"w{index}"
    return cleaned
