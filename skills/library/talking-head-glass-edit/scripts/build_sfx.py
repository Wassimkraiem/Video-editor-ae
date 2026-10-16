#!/usr/bin/env python3
"""
Build assets/sfx.wav — every zoom / card / caption sound on one timeline the length of the video.

Reads edit/sfx.json:
  {
    "duration": 32.766,
    "cues": [["whoosh", 2.95, 0.22], ["pop", 5.0, 0.22], ["sparkle", 8.7, 0.2]],
    "caption_ticks": true
  }
  cue = [sound name or path to an audio file, start time (s), gain]. Sounds come from the bundled HyperFrames library
  (~/.claude/skills/media-use/audio/assets/sfx): whoosh, whoosh-short, whoosh-cinematic, pop,
  click, click-soft, key-press, typing, sparkle, chime, ping, riser, impact-bass-1/2, glitch-1/2/3.

caption_ticks: adds a very soft click-soft (0.13) on each visible caption phrase, skipped when
another cue is within 0.18 s so sounds never stack. Needs compositions/captions.html built first.

Level guide (client-approved): pops 0.22, card-exit whoosh-short 0.10, keyword whoosh 0.2,
shimmer sparkle 0.14–0.2, zoom whoosh 0.22, checklist click-soft 0.16, caption tick 0.13.
No heavy impacts — they were cut for being too loud. The track plays at data-volume ~0.55.

Run from the project root:  python <skill>/scripts/build_sfx.py
"""
import json
import os
import re
import subprocess

import numpy as np
from scipy.io import wavfile

SR = 48000
# media-use is a sibling skill: resolve it next to this skill (works in
# ~/.claude/skills and in a project's .claude/skills), else fall back to home.
_SIBLING_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "media-use", "audio", "assets", "sfx")
LIB = os.path.normpath(_SIBLING_LIB) if os.path.isdir(_SIBLING_LIB) else os.path.expanduser("~/.claude/skills/media-use/audio/assets/sfx")


def load(name):
    # A library name ("whoosh") or a path to the user's own sound file.
    source = name if os.path.isfile(name) else os.path.join(LIB, name + ".mp3")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", source,
                          "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
    return x / (np.max(np.abs(x)) or 1)


def caption_starts():
    s = open("compositions/captions.html", encoding="utf-8").read()
    m = re.search(r"const GROUPS = (\[.*?\]);", s, re.S)
    return [g["s"] for g in json.loads(m.group(1))] if m else []


def main():
    spec = json.load(open("edit/sfx.json", encoding="utf-8"))
    cues = [tuple(c) for c in spec["cues"]]
    if spec.get("caption_ticks", True):
        taken = [c[1] for c in cues]
        cues += [("click-soft", max(0.0, t - 0.04), 0.13) for t in caption_starts()
                 if all(abs(t - u) > 0.18 for u in taken)]
    out = np.zeros((int(SR * spec["duration"]), 2))
    cache = {}
    for name, at, gain in cues:
        x = cache.setdefault(name, load(name))
        i = int(at * SR)
        x = x[: max(0, len(out) - i)]
        out[i: i + len(x)] += x * gain
    out /= max(1.0, np.max(np.abs(out)) / 0.89)
    os.makedirs("assets", exist_ok=True)
    wavfile.write("assets/sfx.wav", SR, (out * 32767).astype(np.int16))
    print(f"wrote assets/sfx.wav ({len(cues)} cues)")


if __name__ == "__main__":
    main()
