#!/usr/bin/env python3
"""Footage prep for the generic fast engine (run from the composition folder).

  python prep.py <clip>

Re-encodes the clip to assets/source.mp4 with a 1-second GOP (sparse keyframes judder under
the renderer's frame-by-frame seeking) and writes edit/footage.json {duration, width, height}.
"""
import json
import os
import subprocess
import sys


def main():
    clip = sys.argv[1]
    os.makedirs("assets", exist_ok=True)
    os.makedirs("edit", exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", clip, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-g", "30", "-keyint_min", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-c:a", "aac", "-b:a", "192k", "assets/source.mp4"], check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height:format=duration", "-of", "json", "assets/source.mp4"],
                                      capture_output=True, text=True, check=True).stdout)
    stream = probe["streams"][0]
    footage = {"duration": round(float(probe["format"]["duration"]), 3), "width": stream["width"], "height": stream["height"]}
    with open("edit/footage.json", "w", encoding="utf-8") as handle:
        json.dump(footage, handle)
    print(footage)


if __name__ == "__main__":
    main()
