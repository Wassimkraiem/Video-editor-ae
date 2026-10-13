#!/usr/bin/env python3
"""
Tile HyperFrames snapshot PNGs into one contact sheet you can actually read.

  python3 contact_sheet.py SNAPSHOT_DIR OUT.png [--cols 6] [--w 300]

(`npx hyperframes snapshot` also writes contact-sheet*.jpg; this one is compact, labels each
tile with its timestamp, and works on any subset you capture with --at.)
"""
import glob
import os
import re
import sys

from PIL import Image, ImageDraw


def opt(name, default, cast):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    fs = sorted(glob.glob(os.path.join(sys.argv[1], "frame-*.png")))
    cols, W = opt("--cols", 6, int), opt("--w", 300, int)
    ims = []
    for f in fs:
        im = Image.open(f).convert("RGB"); h = int(im.height * W / im.width)
        ims.append((im.resize((W, h)), re.search(r"at-([\d.]+)s", f).group(1) + "s" if "at-" in f else os.path.basename(f)))
    H = ims[0][0].height if ims else 1
    rows = max(1, (len(ims) + cols - 1) // cols)
    sh = Image.new("RGB", (cols * (W + 6), rows * (H + 24)), (30, 30, 30)); d = ImageDraw.Draw(sh)
    for i, (im, lab) in enumerate(ims):
        x, y = (i % cols) * (W + 6), (i // cols) * (H + 24)
        sh.paste(im, (x, y + 22)); d.text((x + 4, y + 5), lab, fill=(255, 220, 0))
    sh.save(sys.argv[2]); print("sheet:", sys.argv[2], len(ims), "frames")
