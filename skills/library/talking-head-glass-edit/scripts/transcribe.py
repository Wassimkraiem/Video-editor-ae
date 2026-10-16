#!/usr/bin/env python3
"""
Local word-level transcription with faster-whisper large-v3 (good on Arabic / Darija / French mixes).

Writes into the project root:
  transcript.json  — flat word array [{text, start, end}, …]
  segments.txt     — one line per Whisper segment with times (show this to the user to correct)

Usage (from the project root):
  python <skill>/scripts/transcribe.py assets/source.mp4 --lang ar --prompt "قشابية، كشمير، camping"

Notes learned the hard way on Windows:
  * the model is downloaded with local_dir (no symlinks — WinError 1314 otherwise)
  * audio is decoded with ffmpeg and passed as a numpy array (PyAV 'metadata_errors' bug)
Needs: pip install faster-whisper soundfile ; ffmpeg on PATH. First run downloads ~3 GB.
"""
import argparse
import json
import os
import sys
import subprocess

import numpy as np


def resolve_model(name):
    """Return a local faster-whisper model folder, downloading only as a last resort.

    Looks in $WHISPER_MODELS_DIR/fw-<name> (the studio mounts preinstalled
    models there) and then ~/.cache/fw-<name>. With WHISPER_OFFLINE=1 a
    missing model is an error instead of a multi-GB download.
    """
    roots = [os.environ.get("WHISPER_MODELS_DIR"), os.path.expanduser("~/.cache")]
    for root in filter(None, roots):
        candidate = os.path.join(root, f"fw-{name}")
        if os.path.isfile(os.path.join(candidate, "model.bin")):
            return candidate
    if os.environ.get("WHISPER_OFFLINE") == "1":
        sys.exit(f"faster-whisper model '{name}' is not installed (looked in {', '.join(filter(None, roots))}). "
                 "Use the default model or install it with scripts/fetch_models.py.")
    from huggingface_hub import snapshot_download

    return snapshot_download(f"Systran/faster-whisper-{name}", local_dir=os.path.expanduser(f"~/.cache/fw-{name}"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--lang", default="ar")
    ap.add_argument("--prompt", default="", help="brand / product words to bias spelling")
    ap.add_argument("--model", default="large-v3")
    a = ap.parse_args()

    from faster_whisper import WhisperModel

    path = resolve_model(a.model)
    model = WhisperModel(path, device="cpu", compute_type="int8")

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", a.video, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768

    segs, _ = model.transcribe(audio, language=a.lang, word_timestamps=True, beam_size=5,
                               initial_prompt=a.prompt or None)
    words, lines = [], []
    for s in segs:
        lines.append(f"{s.start:6.2f}-{s.end:6.2f}  {s.text.strip()}")
        for w in s.words:
            words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})
    json.dump(words, open("transcript.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open("segments.txt", "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))
    print(f"\n{len(words)} words → transcript.json  (word indices: python -c \"import json;"
          f"[print(i,w['start'],w['text']) for i,w in enumerate(json.load(open('transcript.json',encoding='utf-8')))]\")")


if __name__ == "__main__":
    main()
