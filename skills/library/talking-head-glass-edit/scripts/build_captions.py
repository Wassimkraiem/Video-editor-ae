#!/usr/bin/env python3
"""
Build compositions/captions.html from:
  transcript.json   — Whisper word timings (scripts/transcribe.py)
  edit/captions.json — the approved wording, grouped into short phrases:

  {
    "duration": 32.766,
    "shot_cuts": [3.033, 12.3, 18.0],
    "groups": [
      {"words": [["انت", [0]], ["والمدام", [1]], ["تلبسوا", [2]]]},
      {"words": [["قشابية", [3]], ["الكشمير", [4]]], "hidden": "intro card"},
      {"words": [["حتى", [5]], ["الولاد", [6]], ["يلبسوها", [7]]], "keys": [0, 1, 2]}
    ]
  }

  words  : [display text, [ASR word indices]] — display text replaces the ASR spelling,
           timing comes from the indices (first start → last end).
  hidden : truthy (use a short reason) when an animation already shows these words —
           the caption is skipped so nothing is ever written twice.
  keys   : word positions that get the keyword treatment (grow + stay gold).

Timing rules baked in (all came from client feedback):
  * every word start is snapped to the real voice onset measured from the audio —
    Whisper often stamps a word inside the pause before it, so captions showed early
  * a caption never starts in the last 0.25 s before a shot cut (it would flash over the
    previous shot) — it starts on the cut instead
  * a phrase holds through short pauses but never past the next phrase

Run from the project root:  python <skill>/scripts/build_captions.py
"""
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "captions.template.html")


def voice_db(video):
    """10 ms RMS envelope (dB) of the source audio."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(float) / 32768
    return np.array([20 * np.log10(np.sqrt(np.mean(a[i:i + 400] ** 2)) + 1e-9)
                     for i in range(0, len(a) - 400, 160)])


def snap_onsets(w, db, quiet=-42.0, min_gap=12, voiced=-32.0):
    """If a word's span contains a real pause (>=120 ms below `quiet`), the word starts after the
    last such pause; then step forward to the first voiced 10 ms frame."""
    for x in w:
        i0, end = int(x["start"] * 100), min(int(x["end"] * 100), len(db) - 1)
        start, run = i0, 0
        for i in range(i0, max(i0, end - 5)):
            run = run + 1 if db[i] < quiet else 0
            if run >= min_gap:
                start = i + 1
        while start < end - 5 and db[start] < voiced:
            start += 1
        x["start"] = round(start / 100, 3)
    return w


def main():
    spec = json.load(open("edit/captions.json", encoding="utf-8"))
    video = spec.get("video", "assets/source.mp4")
    w = snap_onsets(json.load(open("transcript.json", encoding="utf-8")), voice_db(video))
    G = spec["groups"]
    out = []
    for gi, g in enumerate(G):
        if g.get("hidden"):
            continue
        keys = set(g.get("keys", []))
        words = [{"t": t, "s": w[idx[0]]["start"], "e": w[idx[-1]]["end"],
                  "latin": t.isascii() and not t.replace(".", "").isdigit(), "k": i in keys}
                 for i, (t, idx) in enumerate(g["words"])]
        start = words[0]["s"]
        for cut in spec.get("shot_cuts", []):
            if cut - 0.25 < start < cut:
                start = cut
        nxt = w[G[gi + 1]["words"][0][1][0]]["start"] if gi + 1 < len(G) else spec["duration"] - 0.3
        end = min(nxt, words[-1]["e"] + 0.9)
        out.append({"s": round(start, 3), "e": round(end, 3), "w": words})

    tpl = open(TEMPLATE, encoding="utf-8").read()
    os.makedirs("compositions", exist_ok=True)
    open("compositions/captions.html", "w", encoding="utf-8").write(
        tpl.replace("/*__GROUPS__*/[]", json.dumps(out, ensure_ascii=False)))
    for g in out:
        print(f"{g['s']:6.2f}-{g['e']:6.2f}  " + " ".join(f"{x['t']}@{x['s']:.2f}" for x in g["w"]))
    print(f"wrote compositions/captions.html ({len(out)} visible phrases)", file=sys.stderr)


if __name__ == "__main__":
    main()
