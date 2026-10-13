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
import subprocess

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--lang", default="ar")
    ap.add_argument("--prompt", default="", help="brand / product words to bias spelling")
    ap.add_argument("--model", default="large-v3")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download

    path = snapshot_download(f"Systran/faster-whisper-{a.model}",
                             local_dir=os.path.expanduser(f"~/.cache/fw-{a.model}"))
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
