#!/usr/bin/env python3
"""
Write index.html from the skill template + the project's edit files, and fetch the fonts.

Reads (project root)
  edit/captions.json  from chunk_captions.py
  edit/beats.json     the edit plan (scenes, titles, cards…) — see SKILL.md §5
  edit/subject.json   from prep_cutout.py (head top → where the head lands in paper mode)
  edit/style.json     optional {"startMode": "full", "popout": true, "capY": {"full": 1330, "paper": 1330, "green": 1330},
                                "paper": {"scale": 0.74, "headTop": 0.40, "card": [1180, 100, 36, 100], "radius": 46, "blur": 7}}
  edit/extra.html     optional hand-written elements, inserted before the overlays layer

Usage
  python <skill>/scripts/build_comp.py [--video assets/source.mp4] [--music assets/music.mp3 --music-volume 0.1]

Re-run after every edit-file change: index.html is regenerated each time.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = {
    "montserrat-latin-900.woff2": "montserrat@5/files/montserrat-latin-900-normal.woff2",
    "montserrat-latin-ext-900.woff2": "montserrat@5/files/montserrat-latin-ext-900-normal.woff2",
    "cairo-arabic-900.woff2": "cairo@5/files/cairo-arabic-900-normal.woff2",
    "inter-latin-400.woff2": "inter@5/files/inter-latin-400-normal.woff2",
    "inter-latin-600.woff2": "inter@5/files/inter-latin-600-normal.woff2",
    "plex-arabic-700.woff2": "ibm-plex-sans-arabic@5/files/ibm-plex-sans-arabic-arabic-700-normal.woff2",
    "jetbrains-mono-latin-500.woff2": "jetbrains-mono@5/files/jetbrains-mono-latin-500-normal.woff2",
}


def load(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def duration_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="assets/source.mp4", help="the footage (conformed 1080x1920)")
    ap.add_argument("--cutout", default="assets/subject.webm", help="alpha cut-out of the speaker (optional)")
    ap.add_argument("--music", default="")
    ap.add_argument("--music-volume", type=float, default=0.1)
    a = ap.parse_args()

    os.makedirs("assets/fonts", exist_ok=True)
    for name, rel in FONTS.items():
        dst = os.path.join("assets/fonts", name)
        if not os.path.exists(dst):
            urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/npm/@fontsource/{rel}", dst)
            print("font", name)

    subj = load("edit/subject.json", {})
    dur = round(subj.get("duration") or duration_of("assets/voice.wav"), 3)
    caps = load("edit/captions.json", [])
    beats = load("edit/beats.json", [])
    style = load("edit/style.json", {})

    html = open(os.path.join(SKILL, "templates", "index.template.html"), encoding="utf-8").read()
    html = html.replace("__DURATION__", f"{dur}").replace("__VIDEO__", a.video)
    html = html.replace("/*__CAPS__*/[]", json.dumps(caps, ensure_ascii=False))
    html = html.replace("/*__BEATS__*/[]", json.dumps(beats, ensure_ascii=False))
    html = html.replace("/*__SUBJECT__*/{}", json.dumps(subj))
    html = html.replace("/*__STYLE__*/{}", json.dumps(style, ensure_ascii=False))
    if os.path.exists(a.cutout) and style.get("popout", True):
        html = html.replace("<!--__FG__-->",
                            f'<div id="fg" class="full"><div id="cam-fg" class="full cam"><video id="cutout" src="{a.cutout}" muted playsinline '
                            f'data-start="0" data-duration="{dur}" data-track-index="1"></video></div></div>')
    else:
        print("no cut-out found: paper mode will show the footage card without the head pop-out")
    if a.music:
        html = html.replace("<!--__MUSIC__-->", f'<audio id="music" src="{a.music}" data-start="0" data-duration="{dur}" '
                                                 f'data-track-index="4" data-volume="{a.music_volume}"></audio>')
    if os.path.exists("edit/extra.html"):
        html = html.replace('<div id="overlays" class="full"></div>',
                            open("edit/extra.html", encoding="utf-8").read() + '\n      <div id="overlays" class="full"></div>')
    if os.path.exists("index.html"):   # keep the content-hashed sfx track build_sfx.py published
        m = re.search(r'<audio[^>]*id="sfx"[^>]*src="([^"]*)"', open("index.html", encoding="utf-8").read())
        if m and os.path.exists(m.group(1)):
            html = html.replace('src="assets/audio/sfx.wav"', f'src="{m.group(1)}"')
    open("index.html", "w", encoding="utf-8").write(html)
    print(f"index.html: {dur}s, {len(caps)} pills, {len(beats)} beats")


if __name__ == "__main__":
    main()
