#!/usr/bin/env python3
"""
Give the music / SFX tracks content-hashed filenames and point index.html at them.

Why: Studio's preview caches audio by URL. After a rebuild that changed the length
(34.5 s → 47.4 s) the preview kept playing the old 34.5 s files, so music and sound
effects stopped before the end. A new name per build makes a stale copy impossible.

Run after build_music.py and build_sfx.py:  python scripts/publish_audio.py
"""
import glob
import hashlib
import os
import re
import shutil

os.makedirs("assets/audio", exist_ok=True)
html = open("index.html", encoding="utf-8").read()
for name in ("music", "sfx"):
    src = f"assets/{name}.wav"
    digest = hashlib.md5(open(src, "rb").read()).hexdigest()[:8]
    dst = f"assets/audio/{name}-{digest}.wav"
    for old in glob.glob(f"assets/audio/{name}-*.wav"):
        if old.replace("\\", "/") != dst:
            os.remove(old)
    shutil.copyfile(src, dst)
    html, n = re.subn(rf'(<audio[^>]*id="{name}"[^>]*src=")[^"]*(")', rf"\g<1>{dst}\g<2>", html)
    assert n == 1, f"audio#{name} not found in index.html"
    print(f"{name}: {dst}")
open("index.html", "w", encoding="utf-8").write(html)
