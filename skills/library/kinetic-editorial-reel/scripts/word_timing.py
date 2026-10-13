#!/usr/bin/env python3
"""
Word timings from a voiceover WITHOUT a transcription model.

Uses the voice's loudness envelope: finds speech segments (pauses), then splits each
segment's known words proportionally to word length, snapping each cut to the nearest
loudness dip. Output is an ESTIMATE — always confirm with the user in the preview and
pin any word they correct (see --pin), then re-run.

Usage
  python3 word_timing.py segments VOICE.wav            # print speech segments + write env plot
  python3 word_timing.py align VOICE.wav SCRIPT.json   # words -> words.json

SCRIPT.json = list of segments, each {"start": s, "end": e, "text": "word word word"}.
Get start/end from the `segments` command, then assign the spoken text to each segment
(use the user's transcript timestamps as a guide). Optional per-word pins:
  {"start": 14.52, "end": 15.62, "text": "هكّا لا لا", "pin": {"1": 15.04, "2": 15.24}}
("pin" keys are 0-based word indexes inside that segment).

Options
  --thr -34        dB threshold for speech (segments)
  --plot out.png   envelope plot with a 0.1 s grid (default: ./voice_envelope.png)
  --from 12 --to 19  plot a zoomed window
  --out words.json
"""
import json
import subprocess
import sys

import numpy as np

HOP = 0.01  # 10 ms frames


def envelope(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = int(16000 * HOP)
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    db = 20 * np.log10(rms + 1e-6)
    return np.convolve(db, np.ones(3) / 3, "same")


def segments(db, thr=-34.0, min_gap=0.08, min_len=0.05):
    on = db > thr
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        if not v and s is not None:
            segs.append([s, i]); s = None
    if s is not None:
        segs.append([s, len(db)])
    merged = []
    for a, b in segs:
        if merged and (a - merged[-1][1]) * HOP < min_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a * HOP, b * HOP) for a, b in merged if (b - a) * HOP >= min_len]


def plot(db, out, t0=None, t1=None, thr=-34.0):
    from PIL import Image, ImageDraw
    a = int((t0 or 0) / HOP); b = int((t1 or len(db) * HOP) / HOP)
    W, H = max(1600, (b - a) * 4), 360
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    for i in range(a, b):
        X = int((i - a) / (b - a) * W); v = max(0, (db[i] + 60) / 60)
        d.line([X, H, X, H - int(v * H * 0.9)], fill=(40, 40, 40), width=max(1, W // (b - a)))
    for k in range(int(a * HOP * 10), int(b * HOP * 10) + 1):
        X = int((k / 10 / HOP - a) / (b - a) * W)
        col = (255, 0, 0) if k % 10 == 0 else (160, 160, 255)
        d.line([X, 0, X, H], fill=col); d.text((X + 2, 2), f"{k / 10:.1f}", fill=col)
    Y = H - int((thr + 60) / 60 * H * 0.9); d.line([0, Y, W, Y], fill=(0, 160, 0))
    im.save(out)


def align(db, script):
    wlen = lambda w: 7 if "/" in w else max(2, len(w.replace("ّ", "")))
    out = []
    for seg in script:
        a, b, words = seg["start"], seg["end"], seg["text"].split()
        pins = {int(k): float(v) for k, v in (seg.get("pin") or {}).items()}
        tot = sum(wlen(w) for w in words); starts = [a]; acc = 0
        for i, w in enumerate(words[:-1]):
            acc += wlen(w)
            if i + 1 in pins:
                starts.append(pins[i + 1]); continue
            tg = a + (b - a) * acc / tot
            i0, i1 = int((tg - 0.08) / HOP), int((tg + 0.08) / HOP)
            starts.append(round((i0 + int(np.argmin(db[i0:i1]))) * HOP, 2))
        if 0 in pins:
            starts[0] = pins[0]
        for k, w in enumerate(words):
            out.append({"w": w, "s": round(starts[k], 2),
                        "e": round(starts[k + 1] if k + 1 < len(words) else b, 2)})
    return out


def opt(name, default=None, cast=str):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("segments", "align"):
        print(__doc__); sys.exit(1)
    db = envelope(sys.argv[2])
    thr = opt("--thr", -34.0, float)
    if sys.argv[1] == "segments":
        for a, b in segments(db, thr):
            print(f"{a:6.2f} - {b:6.2f}   ({b - a:.2f}s)")
        print(f"voice length: {len(db) * HOP:.2f}s")
        out = opt("--plot", "voice_envelope.png")
        plot(db, out, opt("--from", None, float), opt("--to", None, float), thr)
        print("plot:", out)
    else:
        words = align(db, json.load(open(sys.argv[3])))
        out = opt("--out", "words.json")
        json.dump(words, open(out, "w"), ensure_ascii=False, indent=0)
        for w in words:
            print(f'{w["s"]:6.2f} {w["e"]:6.2f}  {w["w"]}')
        print("wrote", out)
