#!/usr/bin/env python3
"""
Clean the edge of assets/subject.webm: shrink the alpha by N px (removes the coloured fringe a
coloured wall leaves on hair / shoulders), feather it, and re-despill the colour channel.
Writes assets/subject.webm (the original is kept as assets/subject.raw.webm).

  python <skill>/scripts/refine_edges.py [--erode 2] [--feather 1.2] [--despill blue|green|none]

Run it when edit/bg_preview.jpg shows a halo. CPU VP9 encode: ~3-6 min for 40 s.
"""
import argparse
import os
import shutil
import subprocess

ap = argparse.ArgumentParser()
ap.add_argument("--erode", type=int, default=2)
ap.add_argument("--feather", type=float, default=1.2)
ap.add_argument("--despill", default="blue", choices=["blue", "green", "none"])
a = ap.parse_args()

if not os.path.exists("assets/subject.raw.webm"):
    shutil.copyfile("assets/subject.webm", "assets/subject.raw.webm")
colour = f"despill=type={a.despill}:mix=0.9:expand=0.4," if a.despill != "none" else ""
mask = "alphaextract" + ",erosion" * a.erode + f",gblur=sigma={a.feather}"
fc = f"[0:v]split[c][m];[c]{colour}format=yuva420p[cc];[m]{mask}[mm];[cc][mm]alphamerge,format=yuva420p[out]"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-c:v", "libvpx-vp9", "-i", "assets/subject.raw.webm",
                "-filter_complex", fc, "-map", "[out]", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-crf", "16", "-b:v", "0", "-deadline", "good", "-cpu-used", "4", "-row-mt", "1",
                "-auto-alt-ref", "0", "assets/subject.webm"], check=True)
print("refined -> assets/subject.webm")
