#!/usr/bin/env python3
"""
Prepare a talking-head clip for a studio background swap.

  1. conform to 1080x1920 @ 30 fps (centre-crop / scale), extract the voice → assets/voice.wav
  2. relight the speaker like a studio key light: gentle contrast, warm highlights / cool shadows,
     an off-centre falloff (key from one side), light sharpening  → assets/graded.mp4
  3. cut the speaker out with `npx hyperframes remove-background` (u2net_human_seg)
                                                                  → assets/subject.webm (VP9 alpha)
  4. measure where the head sits (alpha bounding box on a few frames) → printed + edit/subject.json
  5. composite preview over a plate, if one is given → edit/bg_preview.jpg

Run from the project root:
  python <skill>/scripts/prep_subject.py <clip.mp4> [--key left|right|front] [--plate assets/plate.png]
         [--quality best|balanced|fast] [--no-grade] [--skip-cutout]

The source is never modified. Footage shot on a green/blue screen or a plain wall cuts out best;
busy rooms work but check hair edges in the preview.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

W, H, FPS = 1080, 1920, 30
sys.stdout.reconfigure(encoding="utf-8")

GRADES = {
    # off-centre vignette = the key light's falloff; the darker side faces away from the key
    "left": "vignette=angle=0.75:x0=w*0.36:y0=h*0.30",
    "right": "vignette=angle=0.75:x0=w*0.64:y0=h*0.30",
    "front": "vignette=angle=0.6:x0=w*0.5:y0=h*0.32",
}


def run(cmd, **kw):
    print("  $", " ".join(cmd) if isinstance(cmd, list) else cmd, flush=True)
    return subprocess.run(cmd, check=True, **kw)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    return d["streams"][0]["width"], d["streams"][0]["height"], float(d["format"]["duration"])


def alpha_frame(webm, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-ss", f"{t:.2f}", "-i", webm,
                          "-frames:v", "1", "-vf", "alphaextract,scale=270:480", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(480, 270)


def screen_colour(clip, dur):
    """'green' / 'blue' if the frame border is dominated by a chroma-screen colour, else 'none'."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur / 2:.2f}", "-i", clip, "-frames:v", "1",
                          "-vf", "scale=90:160", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(160, 90, 3).astype(float)
    border = np.concatenate([f[:40].reshape(-1, 3), f[:, :12].reshape(-1, 3), f[:, -12:].reshape(-1, 3)])
    r, g, b = np.median(border, axis=0)
    if g > 1.25 * max(r, b) and g > 50:
        return "green"
    if b > 1.25 * max(r, g) and b > 50:
        return "blue"
    return "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--key", choices=GRADES, default="left")
    ap.add_argument("--plate", default="")
    ap.add_argument("--quality", default="best", choices=["best", "balanced", "fast"])
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--despill", choices=["auto", "green", "blue", "none"], default="auto",
                    help="neutralise green/blue-screen colour spill on hair and edges")
    ap.add_argument("--skip-cutout", action="store_true", help="reuse an existing assets/subject.webm")
    a = ap.parse_args()

    os.makedirs("assets", exist_ok=True)
    os.makedirs("edit", exist_ok=True)
    w, h, dur = probe(a.clip)
    print(f"source {w}x{h}, {dur:.2f}s")

    conform = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
    grade = ("eq=contrast=1.07:brightness=-0.015:saturation=1.06,"
             "colorbalance=rs=-0.02:bs=0.035:rh=0.035:gh=0.01:bh=-0.03,"
             f"{GRADES[a.key]},unsharp=5:5:0.35")
    vf = conform if a.no_grade else f"{conform},{grade}"
    spill = a.despill if a.despill != "auto" else screen_colour(a.clip, dur)
    if spill in ("green", "blue"):
        print(f"  {spill} screen detected -> despill")
        vf = f"{conform},despill=type={spill}:mix=0.6:expand=0.15" + ("" if a.no_grade else f",{grade}")

    run(["ffmpeg", "-v", "error", "-y", "-i", a.clip, "-vn", "-ac", "2", "-ar", "48000", "assets/voice.wav"])
    run(["ffmpeg", "-v", "error", "-y", "-i", a.clip, "-an", "-vf", vf, "-c:v", "libx264", "-crf", "14",
         "-preset", "medium", "-pix_fmt", "yuv420p", "-g", "15", "assets/graded.mp4"])

    if not a.skip_cutout:
        npx = "npx.cmd" if sys.platform == "win32" else "npx"
        print("  cutting out the speaker (CPU: roughly 15-20 s per second of video)...", flush=True)
        r = subprocess.run([npx, "hyperframes", "remove-background", "assets/graded.mp4", "-o",
                            "assets/subject.webm", "--quality", a.quality],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            print((r.stdout + r.stderr)[-3000:])
            sys.exit("remove-background failed")

    # where is the speaker? alpha bbox on 5 frames
    tops, bottoms, lefts, rights = [], [], [], []
    for t in np.linspace(0.3, max(0.4, dur - 0.3), 5):
        m = alpha_frame("assets/subject.webm", t) > 128
        ys, xs = np.nonzero(m)
        if len(ys):
            tops.append(ys.min() / 480); bottoms.append(ys.max() / 480)
            lefts.append(xs.min() / 270); rights.append(xs.max() / 270)
    info = {"duration": round(dur, 3), "key": a.key}
    if tops:
        top = float(np.median(tops))
        info.update(top=round(top, 3), bottom=round(float(np.median(bottoms)), 3),
                    left=round(float(np.median(lefts)), 3), right=round(float(np.median(rights)), 3),
                    head_y=round(top + 0.07, 3), chest_y=round(top + 0.30, 3))
    json.dump(info, open("edit/subject.json", "w"), indent=1)
    print(json.dumps(info))

    if a.plate and os.path.exists(a.plate):
        t = min(dur / 2, 3.0)
        run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", a.plate, "-c:v", "libvpx-vp9", "-ss", f"{t:.2f}",
             "-i", "assets/subject.webm", "-filter_complex", "[0][1]overlay=0:0:shortest=1,scale=540:960",
             "-frames:v", "1", "edit/bg_preview.jpg"])
        print("preview → edit/bg_preview.jpg")


if __name__ == "__main__":
    main()
