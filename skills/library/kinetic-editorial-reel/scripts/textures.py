#!/usr/bin/env python3
"""
Deterministic texture helpers for the editorial look.

  python3 textures.py halftone IN.png OUT.png [--cell 13] [--size 1200] [--gamma 0.9]
      Coarse white-dot halftone of a (transparent) cut-out — the "print cut-out on black"
      look (reference: halftone businessman). Dot radius follows luminance; alpha kept.

  python3 textures.py grunge OUT.png [--seed 7]
      600x600 ink-grunge alpha mask (speckle holes + scratches). Use as CSS mask-image on
      red stamp text / stamp impressions so they read as rubber-stamp ink.

  python3 textures.py split IN.png OUTPREFIX
      Split a sheet of several separate objects (e.g. 3 tape strips on one transparent
      canvas) into OUTPREFIX_1.png, _2.png ... by connected alpha components.
"""
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def opt(name, default, cast):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def halftone(src, out, cell=13, size=1200, gamma=0.9):
    im = Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)
    L = im.convert("L").filter(ImageFilter.GaussianBlur(3)); A = im.getchannel("A")
    S = 4
    big = Image.new("RGBA", (size * S, size * S), (0, 0, 0, 0)); d = ImageDraw.Draw(big)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            cx, cy = x + cell / 2, y + cell / 2
            px = (min(size - 1, int(cx)), min(size - 1, int(cy)))
            if A.getpixel(px) < 60:
                continue
            r = (cell * 0.62) * ((L.getpixel(px) / 255) ** gamma) + 0.9
            d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=(255, 255, 255, 255))
    big.resize((size, size), Image.LANCZOS).save(out)


def grunge(out, seed=7):
    random.seed(seed)
    g = Image.new("L", (600, 600), 255); dg = ImageDraw.Draw(g)
    for _ in range(2600):
        x, y = random.random() * 600, random.random() * 600; r = random.random() ** 3 * 7 + 0.6
        dg.ellipse([x - r, y - r, x + r, y + r], fill=int(random.random() * 120))
    for _ in range(40):
        x, y = random.random() * 600, random.random() * 600; w = random.random() * 60 + 10
        dg.line([x, y, x + w, y + random.random() * 6 - 3], fill=90, width=2)
    g = g.filter(ImageFilter.GaussianBlur(0.7))
    m = Image.new("RGBA", (600, 600), (0, 0, 0, 0)); m.putalpha(g); m.save(out)


def split(src, prefix):
    from scipy import ndimage
    im = Image.open(src).convert("RGBA"); arr = np.array(im); a = arr[:, :, 3] > 30
    lab, n = ndimage.label(a); sizes = ndimage.sum(a, lab, range(1, n + 1))
    k = 0
    for idx in [i + 1 for i, s in enumerate(sizes) if s >= sizes.max() * 0.05]:
        m = lab == idx; ys, xs = np.where(m)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        sub = arr[y0:y1, x0:x1].copy(); sub[:, :, 3] = sub[:, :, 3] * m[y0:y1, x0:x1]
        k += 1; Image.fromarray(sub).save(f"{prefix}_{k}.png"); print(f"{prefix}_{k}.png", (x1 - x0, y1 - y0))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "halftone":
        halftone(sys.argv[2], sys.argv[3], opt("--cell", 13, int), opt("--size", 1200, int), opt("--gamma", 0.9, float))
    elif cmd == "grunge":
        grunge(sys.argv[2], opt("--seed", 7, int))
    elif cmd == "split":
        split(sys.argv[2], sys.argv[3])
    else:
        print(__doc__); sys.exit(1)
