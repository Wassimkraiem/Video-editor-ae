#!/usr/bin/env python3
"""
Write index.html from the skill template + the project's edit files, and fetch the fonts.

Reads (project root)
  edit/captions.json  from chunk_captions.py
  edit/beats.json     the edit plan: [{"type": "punch", "t": 2.4, "scale": 1.18}, ...]  (see SKILL.md §5)
  edit/subject.json   from prep_subject.py (head/chest position → glow + caption height)
  edit/style.json     optional {"look": "devin"|"apple", "bg": "studio"|"original", "smoothCam": false,
                                "maxZoom": 1.08, "pushDur": 1.4, "captionFont": "sans"|"pixel",
                                "autoFlash": true, "capOffset": 0.0, "glowBase": 0.0, "glowPeak": 0.6}
Usage
  python <skill>/scripts/build_comp.py [--plate assets/plate.png] [--music assets/music.mp3 --music-volume 0.12]

Re-run after every edit-file change (it overwrites index.html — put hand-written b-roll <video>
elements in edit/extra.html; they are inserted before the overlays layer).
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = {
    "montserrat-latin-900.woff2": "montserrat/files/montserrat-latin-900-normal.woff2",
    "montserrat-latin-ext-900.woff2": "montserrat/files/montserrat-latin-ext-900-normal.woff2",
    "cairo-arabic-900.woff2": "cairo/files/cairo-arabic-900-normal.woff2",
    "silkscreen-latin-700.woff2": "silkscreen/files/silkscreen-latin-700-normal.woff2",
    "inter-latin-600.woff2": "inter/files/inter-latin-600-normal.woff2",
    "inter-latin-400.woff2": "inter/files/inter-latin-400-normal.woff2",
    "inter-latin-700.woff2": "inter/files/inter-latin-700-normal.woff2",
    "plex-arabic-700.woff2": "ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-700-normal.woff2",
}


def load(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def duration_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", default="assets/plate.png")
    ap.add_argument("--video", default="assets/subject.webm",
                    help="speaker layer; pass the original footage (e.g. assets/source.mp4) with style bg=original")
    ap.add_argument("--music", default="")
    ap.add_argument("--music-volume", type=float, default=0.12)
    a = ap.parse_args()

    os.makedirs("assets/fonts", exist_ok=True)
    for name, rel in FONTS.items():
        dst = os.path.join("assets/fonts", name)
        if not os.path.exists(dst):
            urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/npm/@fontsource/{rel.split('/')[0]}@5/{'/'.join(rel.split('/')[1:])}", dst)
            print("font", name)

    subj = load("edit/subject.json", {})
    dur = round(subj.get("duration") or duration_of("assets/voice.wav"), 3)
    caps = load("edit/captions.json", [])
    beats = load("edit/beats.json", [])
    style = load("edit/style.json", {})

    html = open(os.path.join(SKILL, "templates", "index.template.html"), encoding="utf-8").read()
    html = html.replace("__DURATION__", f"{dur}").replace("__PLATE__", a.plate).replace('src="assets/subject.webm"', f'src="{a.video}"')
    html = html.replace("/*__CAPS__*/[]", json.dumps(caps, ensure_ascii=False))
    html = html.replace("/*__BEATS__*/[]", json.dumps(beats, ensure_ascii=False))
    html = html.replace("/*__SUBJECT__*/{}", json.dumps(subj))
    html = html.replace("/*__STYLE__*/{}", json.dumps(style))
    if a.music:
        html = html.replace("<!--__MUSIC__-->", f'<audio id="music" src="{a.music}" data-start="0" data-duration="{dur}" '
                                                 f'data-track-index="4" data-volume="{a.music_volume}"></audio>')
    if os.path.exists("edit/extra.html"):
        html = html.replace('<div id="overlays" class="full"></div>',
                            open("edit/extra.html", encoding="utf-8").read() + '\n      <div id="overlays" class="full"></div>')
    # keep the sfx src that build_sfx.py published, if any
    if os.path.exists("index.html"):
        import re
        m = re.search(r'<audio[^>]*id="sfx"[^>]*src="([^"]*)"', open("index.html", encoding="utf-8").read())
        if m and os.path.exists(m.group(1)):
            html = html.replace('src="assets/audio/sfx.wav"', f'src="{m.group(1)}"')
    open("index.html", "w", encoding="utf-8").write(html)
    print(f"index.html: {dur}s, {len(caps)} captions, {len(beats)} beats")


if __name__ == "__main__":
    main()
