#!/usr/bin/env python3
"""
Conform the clip and cut the speaker out (for the head-pops-out-of-the-card effect).

  1. conform to 1080x1920 @ 30 fps → assets/source.mp4, voice → assets/voice.wav
  2. `hyperframes remove-background` → assets/subject.webm (VP9 alpha). CPU: ~15-20 s per second of video,
     so start it in the background and write the edit meanwhile.
  3. measure the head (alpha bbox on 5 frames) → edit/subject.json {duration, top, bottom, left, right, head_y, chest_y}

Usage (project root):  python <skill>/scripts/prep_cutout.py <clip.mp4> [--quality best|balanced|fast] [--skip-cutout]

If the newest hyperframes release is not downloadable yet (npm 404 right after a publish), the previous
version is used automatically.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

W, H, FPS = 1080, 1920, 30
sys.stdout.reconfigure(encoding="utf-8")
NPX = "npx.cmd" if sys.platform == "win32" else "npx"


def run(cmd):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def hf(args):
    """npx hyperframes <args>, falling back to the previous release if the latest tarball 404s."""
    r = subprocess.run([NPX, "-y", "hyperframes", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode and ("E404" in r.stdout + r.stderr or "ETARGET" in r.stdout + r.stderr):
        vs = json.loads(subprocess.run([NPX.replace("npx", "npm"), "view", "hyperframes", "versions", "--json"],
                                       capture_output=True, text=True).stdout)
        prev = [v for v in vs if "-" not in v][-2]
        print(f"  latest hyperframes not downloadable, using {prev}")
        r = subprocess.run([NPX, "-y", f"hyperframes@{prev}", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r


def alpha_frame(webm, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{t:.2f}", "-i", webm, "-frames:v", "1",
                          "-vf", "alphaextract,scale=270:480", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(480, 270)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--quality", default="balanced", choices=["best", "balanced", "fast"])
    ap.add_argument("--skip-cutout", action="store_true")
    a = ap.parse_args()
    os.makedirs("assets", exist_ok=True)
    os.makedirs("edit", exist_ok=True)

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.clip],
                               capture_output=True, text=True, check=True).stdout.strip())
    if os.path.abspath(a.clip) != os.path.abspath("assets/source.mp4"):
        run(["ffmpeg", "-v", "error", "-y", "-i", a.clip, "-an", "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
             "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-g", "15", "assets/source.mp4"])
        run(["ffmpeg", "-v", "error", "-y", "-i", a.clip, "-vn", "-ac", "2", "-ar", "48000", "assets/voice.wav"])

    if not a.skip_cutout:
        print("  cutting out the speaker (CPU: ~15-20 s per second of video)...", flush=True)
        r = hf(["remove-background", "assets/source.mp4", "-o", "assets/subject.webm", "--quality", a.quality])
        if r.returncode:
            print((r.stdout + r.stderr)[-3000:])
            sys.exit("remove-background failed — the edit still works without it (no head pop-out)")

    info = {"duration": round(dur, 3)}
    if os.path.exists("assets/subject.webm"):
        tops, bottoms, lefts, rights = [], [], [], []
        for t in np.linspace(0.3, max(0.4, dur - 0.3), 5):
            ys, xs = np.nonzero(alpha_frame("assets/subject.webm", t) > 128)
            if len(ys):
                tops.append(ys.min() / 480); bottoms.append(ys.max() / 480)
                lefts.append(xs.min() / 270); rights.append(xs.max() / 270)
        if tops:
            top = float(np.median(tops))
            info.update(top=round(top, 3), bottom=round(float(np.median(bottoms)), 3), left=round(float(np.median(lefts)), 3),
                        right=round(float(np.median(rights)), 3), head_y=round(top + 0.07, 3), chest_y=round(top + 0.30, 3))
    json.dump(info, open("edit/subject.json", "w"), indent=1)
    print(json.dumps(info))


if __name__ == "__main__":
    main()
