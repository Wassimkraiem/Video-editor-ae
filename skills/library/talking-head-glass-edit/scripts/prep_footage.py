#!/usr/bin/env python3
"""
Footage + brand prep for a talking-head glass edit. Run from the project root.

  python <skill>/scripts/prep_footage.py <input.mp4> [--logo logo.png]

Does:
  1. re-encodes the clip to assets/source.mp4 with a 1-second GOP (sparse keyframes freeze or
     judder under the renderer's seek-by-frame capture) — picture and sound otherwise unchanged
  2. prints duration / size / fps and the shot cuts (ffmpeg scene score > 0.25)
  3. writes a 2 fps contact sheet to edit/contact.jpg (11 per row → each row = 5.5 s) so you can
     see where faces, garments and empty wall sit in every shot
  4. with --logo: turns a dark-on-light logo into transparent PNGs assets/logo-white.png and
     assets/logo-ink.png (use white on liquid glass)
"""
import argparse
import json
import os
import re
import subprocess


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--logo")
    a = ap.parse_args()
    os.makedirs("assets", exist_ok=True)
    os.makedirs("edit", exist_ok=True)

    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.video, "-c:v", "libx264", "-crf", "17",
                    "-preset", "slow", "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "assets/source.mp4"], check=True)

    p = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json",
                        "assets/source.mp4"]).stdout)
    st, dur = p["streams"][0], float(p["format"]["duration"])
    print(f"duration {dur:.3f}s  size {st['width']}x{st['height']}  fps {st['r_frame_rate']}")

    log = run(["ffmpeg", "-i", "assets/source.mp4", "-vf", "select='gt(scene,0.25)',showinfo",
               "-an", "-f", "null", "-"]).stderr
    cuts = [round(float(t), 3) for t in re.findall(r"pts_time:([0-9.]+)", log)]
    print("shot cuts:", cuts)

    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "assets/source.mp4", "-vf",
                    "fps=2,scale=180:320,tile=11x6", "-frames:v", "1", "edit/contact.jpg"], check=True)
    print("contact sheet → edit/contact.jpg (2 fps, 11 per row = 5.5 s per row)")
    json.dump({"duration": round(dur, 3), "shot_cuts": cuts}, open("edit/footage.json", "w"), indent=1)

    if a.logo:
        import numpy as np
        from PIL import Image
        g = np.array(Image.open(a.logo).convert("L")).astype(float) / 255
        alpha = np.clip((1 - g - 0.05) / 0.9, 0, 1)
        ys, xs = np.where(alpha > 0.1)
        alpha = alpha[max(0, ys.min() - 8): ys.max() + 8, max(0, xs.min() - 8): xs.max() + 8]
        for name, col in [("logo-white.png", (255, 255, 255)), ("logo-ink.png", (27, 23, 18))]:
            rgba = np.zeros(alpha.shape + (4,), np.uint8)
            rgba[..., :3] = col
            rgba[..., 3] = (alpha * 255).astype(np.uint8)
            Image.fromarray(rgba).save(os.path.join("assets", name))
        print("logo → assets/logo-white.png, assets/logo-ink.png", alpha.shape[::-1])


if __name__ == "__main__":
    main()
