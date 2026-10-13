#!/usr/bin/env python3
"""
Word-level transcription with faster-whisper (local, CPU).

Writes into the project root:
  edit/words.json    flat word list [{"t": "word", "s": start, "e": end}, ...]
  edit/segments.txt  one line per segment with times — show this to the user to correct

Usage (from the project root):
  python <skill>/scripts/transcribe.py assets/voice.wav [--lang en|fr|ar] [--model large-v3|small]
         [--prompt "brand names, jargon"]

Windows notes: the model is downloaded with local_dir (no symlinks, avoids WinError 1314) and the
audio is decoded with ffmpeg and passed as a numpy array (avoids the PyAV 'metadata_errors' bug).
Needs: pip install faster-whisper ; ffmpeg on PATH. large-v3 is ~3 GB on first run.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--lang", default=None, help="language code; omit to auto-detect")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--prompt", default="")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download

    path = snapshot_download(f"Systran/faster-whisper-{a.model}",
                             local_dir=os.path.expanduser(f"~/.cache/fw-{a.model}"))
    model = WhisperModel(path, device="cpu", compute_type="int8")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.audio, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768

    segs, info = model.transcribe(audio, language=a.lang, word_timestamps=True, beam_size=5,
                                  initial_prompt=a.prompt or None, vad_filter=True)
    words, lines = [], []
    for s in segs:
        lines.append(f"{s.start:6.2f}-{s.end:6.2f}  {s.text.strip()}")
        for w in s.words:
            words.append({"t": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)})
    os.makedirs("edit", exist_ok=True)
    json.dump(words, open("edit/words.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    open("edit/segments.txt", "w", encoding="utf-8").write("\n".join(lines))
    print(f"language: {info.language}")
    print("\n".join(lines))
    span = words[-1]["e"] - words[0]["s"] if words else 0
    print(f"\n{len(words)} words, {span:.1f}s, {60 * len(words) / max(span, 1):.0f} wpm -> edit/words.json")


if __name__ == "__main__":
    main()
