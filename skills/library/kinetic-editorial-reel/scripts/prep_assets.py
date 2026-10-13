#!/usr/bin/env python3
"""
Asset prep for kinetic editorial reels — accepts transparent PNGs AND normal (opaque) images.

  python3 prep_assets.py SRC_DIR OUT_DIR [--keep bg1.png,bg2.png] [--tol 14] [--sheet sheet.png]

For every image in SRC_DIR:
  * already transparent (real alpha)   -> copied as-is (PNG)
  * listed in --keep (full-frame photos meant as backgrounds: a room, a desk...)
                                       -> copied as-is, no cut-out
  * opaque with a plain-ish background -> background removed by EDGE FLOOD-FILL:
        background colour sampled from the image border; every pixel connected to the
        border and within --tol of that colour becomes transparent; mask cleaned (hole
        fill, speck removal), feathered ~2 px, and background colour spill un-mixed from
        the rim. Works well for AI renders / product shots on white, grey or solid bg.
  * opaque with a busy/photographic border, or flood-fill taking <8% / >92% of frame
        -> copied unchanged and flagged NEEDS_CUTOUT. People: `npx hyperframes
           remove-background in.jpg -o out.png` (human-segmentation model). Objects: ask
           the user for a plain-background version, or keep it as a full-frame photo.

Writes OUT_DIR/assets_report.json (per file: mode, size, alpha bbox, alpha-weighted
centre) and a checkerboard contact sheet. Always LOOK at the sheet before building.
"""
import glob
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

EXTS = (".png", ".jpg", ".jpeg", ".webp")


def has_real_alpha(im):
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        a = np.array(im.convert("RGBA"))[:, :, 3]
        return (a < 250).mean() > 0.01
    return False


def border_colour(rgb):
    h, w, _ = rgb.shape
    b = max(2, min(h, w) // 100)
    edge = np.concatenate([rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
                           rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)])
    return np.median(edge, axis=0), edge


def remove_bg(im, tol=14.0):
    rgb = np.array(im.convert("RGB")).astype(np.float32)
    bgc, edge = border_colour(rgb)
    spread = float(np.percentile(np.linalg.norm(edge - bgc, axis=1), 90))
    if spread > 28:  # textured / photographic border -> not a plain backdrop
        return None, 0.0
    # adaptive tolerance: slightly noisy borders (JPEG, soft gradient) get a bit more room
    t = max(tol, min(tol * 2.0, spread * 1.8))
    cand = np.linalg.norm(rgb - bgc, axis=2) < t
    lab, _ = ndimage.label(cand)
    border_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, border_labels[border_labels > 0])
    frac = float(bg.mean())
    if frac < 0.08 or frac > 0.92:
        return None, frac
    fg = ndimage.binary_fill_holes(~bg)
    lab2, n2 = ndimage.label(fg)
    if n2 > 1:  # drop specks smaller than 0.2 % of the largest island
        sizes = ndimage.sum(fg, lab2, range(1, n2 + 1))
        fg = np.isin(lab2, [i + 1 for i, s in enumerate(sizes) if s >= sizes.max() * 0.002])
    # soft edge: ~2 px ramp inside the mask + light blur
    alpha = np.clip(ndimage.distance_transform_edt(fg) / 2.0, 0, 1)
    alpha = np.array(Image.fromarray((alpha * 255).astype(np.uint8))
                     .filter(ImageFilter.GaussianBlur(0.8))) / 255.0
    alpha = np.where(fg, np.maximum(alpha, 0.35), alpha * 0.5)
    # de-spill: un-mix the background colour on the soft rim
    a3 = np.clip(alpha, 0.05, 1)[:, :, None]
    unmixed = np.clip((rgb - (1 - a3) * bgc) / a3, 0, 255)
    rim = (alpha > 0) & (alpha < 0.98)
    out_rgb = np.where(rim[:, :, None], unmixed, rgb)
    return Image.fromarray(np.dstack([out_rgb, alpha * 255]).astype(np.uint8), "RGBA"), frac


def stats(im):
    a = np.array(im.convert("RGBA"))[:, :, 3].astype(np.float32)
    ys, xs = np.nonzero(a > 10)
    if len(xs) == 0:
        return None, None
    cy, cx = ndimage.center_of_mass(a)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], \
           [round(float(cx), 1), round(float(cy), 1)]


def checker(n, c=16):
    im = Image.new("RGB", (n, n), (255, 255, 255)); d = ImageDraw.Draw(im)
    for y in range(0, n, c):
        for x in range(0, n, c):
            if (x // c + y // c) % 2:
                d.rectangle([x, y, x + c - 1, y + c - 1], fill=(200, 200, 200))
    return im


def sheet(paths, out, T=300, cols=5):
    rows = max(1, (len(paths) + cols - 1) // cols)
    sh = Image.new("RGB", (cols * (T + 8), rows * (T + 26)), (40, 40, 40)); d = ImageDraw.Draw(sh)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGBA"); im.thumbnail((T, T))
        bg = checker(T); bg.paste(im, ((T - im.width) // 2, (T - im.height) // 2), im)
        x, y = (i % cols) * (T + 8), (i // cols) * (T + 26)
        sh.paste(bg, (x, y + 22)); d.text((x + 3, y + 5), os.path.basename(p)[:44], fill=(255, 255, 0))
    sh.save(out)


def opt(name, default=None):
    for a in sys.argv:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    keep = set((opt("--keep", "") or "").split(",")) - {""}
    tol = float(opt("--tol", 14))
    os.makedirs(dst, exist_ok=True)
    report, outs = {}, []
    for p in sorted(glob.glob(os.path.join(src, "*"))):
        if not p.lower().endswith(EXTS):
            continue
        name = os.path.basename(p); base = os.path.splitext(name)[0]
        im = Image.open(p)
        if has_real_alpha(im):
            out = os.path.join(dst, base + ".png"); im.convert("RGBA").save(out); mode = "transparent"
        elif name in keep or base in keep:
            out = os.path.join(dst, name)
            if os.path.abspath(out) != os.path.abspath(p):
                shutil.copy(p, out)
            mode = "background-photo"
        else:
            cut, frac = remove_bg(im, tol)
            if cut is None:
                out = os.path.join(dst, name)
                if os.path.abspath(out) != os.path.abspath(p):
                    shutil.copy(p, out)
                mode = ("NEEDS_CUTOUT or --keep (photographic border)" if frac == 0.0
                        else f"NEEDS_CUTOUT (flood-fill covered {frac:.0%})")
            else:
                out = os.path.join(dst, base + ".png"); cut.save(out); mode = f"cutout (bg {frac:.0%})"
        o = Image.open(out)
        bbox, centre = stats(o) if o.mode == "RGBA" else (None, None)
        report[os.path.basename(out)] = {"source": name, "mode": mode, "size": list(o.size),
                                         "bbox": bbox, "centre": centre}
        outs.append(out)
        print(f"{os.path.basename(out):36s} {mode}")
    json.dump(report, open(os.path.join(dst, "assets_report.json"), "w"), indent=2, ensure_ascii=False)
    sp = opt("--sheet", os.path.join(dst, "assets_sheet.png"))
    sheet(outs, sp)
    print("report:", os.path.join(dst, "assets_report.json"), "\nsheet:", sp)
