#!/usr/bin/env python3
"""
Mix every sound effect onto one track the length of the video → assets/audio/sfx-<hash>.wav,
and point index.html's <audio id="sfx"> at it (content-hashed name: Studio caches audio by URL,
so a rebuilt track with the same name would keep playing the old one).

Reads edit/sfx.json:
  {
    "duration": 41.2,
    "cues": [["whoosh", 3.10, 0.30], ["pop", 7.95, 0.25], ["click", 12.4, 0.3]],
    "keyword_hits": true,     # soft bass hit + short whoosh on every coloured keyword card
    "card_ticks": false,      # soft tick on every caption card ("tick_gain", default 0.08)
    "word_ticks": false,      # very soft tick (tick_gain default 0.025) on every word as it fills into the pill
    "keyword_sound": "soft"   # "soft" (whoosh + pop, default here) or "impact" (Devin bass hit)
    "keyword_gain": 0.4       # multiplier for the keyword sound (default subtle; 1.0 = full)
    "beat_sounds": true       # default sound for every beat in edit/beats.json (table below)
  }
  cue = [name, time (s), gain]. Library (~/.claude/skills/media-use/audio/assets/sfx):
  whoosh, whoosh-short, whoosh-cinematic, pop, click, click-soft, key-press, typing, sparkle,
  chime, ping, notification, riser, impact-bass-1, impact-bass-2, glitch-1/2/3, error.
  A path to any .wav/.mp3 also works as a name.

Level guide: b-roll whoosh 0.30, zoom-blur whoosh-cinematic 0.25, UI pop 0.25, tap click 0.30,
keyboard typing 0.20, notification 0.30, keyword impact 0.22, glitch 0.20, card tick 0.08.
Voice stays at 1.0; the sfx track plays at data-volume 0.7.

Run from the project root:  python <skill>/scripts/build_sfx.py
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

sys.stdout.reconfigure(encoding="utf-8")
SR = 48000
# media-use is a sibling skill: resolve it next to this skill (works in
# ~/.claude/skills and in a project's .claude/skills), else fall back to home.
_SIBLING_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "media-use", "audio", "assets", "sfx")
LIB = os.path.normpath(_SIBLING_LIB) if os.path.isdir(_SIBLING_LIB) else os.path.expanduser("~/.claude/skills/media-use/audio/assets/sfx")


def load(name):
    path = name if os.path.exists(name) else os.path.join(LIB, name + ".mp3")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
    return x / (np.max(np.abs(x)) or 1)


BEAT_SOUNDS = {  # beat type -> [(sound, offset, gain)]  (Ouerfelli: soft, airy, never harsh)
    "scene": [("whoosh-short", -0.12, 0.22)],
    "hook": [("whoosh-short", -0.08, 0.16), ("pop", 0.0, 0.14)],
    "title": [("pop", 0.0, 0.12)],
    "shot": [("whoosh", -0.1, 0.2), ("pop", 0.12, 0.14)],
    "terminal": [("whoosh", -0.1, 0.2), ("typing", 0.45, 0.16)],
    "stat": [("whoosh-short", -0.05, 0.16), ("chime", 1.2, 0.1)],
    "people": [("sparkle", 0.0, 0.12)],
    "icons": [("whoosh-cinematic", -0.05, 0.16)],
    "list": [("whoosh-short", -0.05, 0.16)],
    "tag": [("pop", 0.0, 0.16)],
    "push": [("whoosh-short", -0.05, 0.08)],
}


def main():
    spec = json.load(open("edit/sfx.json", encoding="utf-8"))
    cues = [tuple(c) for c in spec.get("cues", [])]
    caps = json.load(open("edit/captions.json", encoding="utf-8")) if os.path.exists("edit/captions.json") else []
    taken = [c[1] for c in cues]
    free = lambda t, d=0.2: all(abs(t - u) > d for u in taken)
    if spec.get("beat_sounds", True) and os.path.exists("edit/beats.json"):
        for b in json.load(open("edit/beats.json", encoding="utf-8")):
            for name, off, gain in BEAT_SOUNDS.get(b["type"], []):
                cues.append((name, max(0.0, b["t"] + off), gain))
            for it in b.get("items", []) or []:   # chips / list rows pop on their own times
                if isinstance(it, dict) and it.get("t") is not None:
                    cues.append(("pop", it["t"], 0.14))
            for h in b.get("hl", []) or []:
                cues.append(("click-soft", h["t"], 0.2))
            if b.get("hotAt"):
                cues.append(("pop", b["hotAt"], 0.16))
        taken = [c[1] for c in cues]
    if spec.get("keyword_hits", True):
        for c in caps:   # Ouerfelli pills: the keyword is a word inside the pill → sound on that word's onset
            for w in c.get("words", []):
                if w.get("k"):
                    c = {"s": w["s"], "key": w["k"]}
                    break
            if c.get("key") and free(c["s"]):
                kg = spec.get("keyword_gain", 0.4)   # scale the keyword sound (0.4 = subtle)
                if spec.get("keyword_sound", "soft") == "soft":
                    cues += [("whoosh-short", max(0, c["s"] - 0.06), 0.16 * kg), ("pop", c["s"], 0.14 * kg)]
                else:
                    cues += [("impact-bass-1", c["s"], 0.22), ("whoosh-short", max(0, c["s"] - 0.06), 0.14)]
    if spec.get("word_ticks", False):  # one soft tick per spoken word (captions + kinetic beats)
        g = spec.get("tick_gain", 0.025)
        times = {round(w["s"], 2) for c in caps for w in c.get("words", []) if w.get("s") is not None}
        if os.path.exists("edit/beats.json"):
            for b in json.load(open("edit/beats.json", encoding="utf-8")):
                for ln in b.get("lines", []):
                    if isinstance(ln, dict):
                        times |= {round(w["s"], 2) for w in ln.get("words", []) if w.get("s") is not None}
        cues += [("click-soft", max(0.0, t - 0.02), g) for t in sorted(times) if free(t, 0.08)]
    if spec.get("card_ticks", False):
        g = spec.get("tick_gain", 0.025)
        cues += [("click-soft", c["s"], g) for c in caps if not c.get("key") and free(c["s"], 0.15)]

    out = np.zeros((int(SR * spec["duration"]), 2))
    cache = {}
    for name, at, gain in cues:
        x = cache.setdefault(name, load(name))
        i = int(at * SR)
        if i >= len(out):
            continue
        x = x[: len(out) - i]
        out[i: i + len(x)] += x * gain
    out /= max(1.0, np.max(np.abs(out)) / 0.89)

    data = (out * 32767).astype(np.int16)
    digest = hashlib.md5(data.tobytes()).hexdigest()[:8]
    os.makedirs("assets/audio", exist_ok=True)
    dst = f"assets/audio/sfx-{digest}.wav"
    for old in glob.glob("assets/audio/sfx-*.wav"):
        if old.replace("\\", "/") != dst:
            os.remove(old)
    wavfile.write(dst, SR, data)
    if os.path.exists("index.html"):
        html = open("index.html", encoding="utf-8").read()
        html, n = re.subn(r'(<audio[^>]*id="sfx"[^>]*src=")[^"]*(")', rf"\g<1>{dst}\g<2>", html)
        if n:
            open("index.html", "w", encoding="utf-8").write(html)
    print(f"{len(cues)} cues -> {dst}")


if __name__ == "__main__":
    main()
