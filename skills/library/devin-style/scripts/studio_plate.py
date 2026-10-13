#!/usr/bin/env python3
"""
Paint a professional, softly-lit studio background plate (1080x1920 PNG) to put behind a
background-removed speaker. Fully procedural and offline, so every run looks the same.

Presets
  penthouse  night penthouse: floor-to-ceiling window, out-of-focus city lights + hills,
             warm LED shelf strips on the right, dark desk. Devin Jatho's signature set.
  studio     seamless charcoal backdrop with a soft key-light pool behind the head, a cool
             hair-light falloff at the edges and a faint floor. Classic professional studio.
  lounge     warm evening lounge: window with fairy-light bokeh, a fireplace glow bottom right,
             wood-dark walls. The cosy variant (used in his "story algorithm" reel).

Usage
  python studio_plate.py assets/plate.png --preset penthouse [--seed 7] [--accent "#ff2a2a"]
         [--head-y 0.30]     # where the speaker's head sits (0..1); the light pool centres there
  python studio_plate.py out.png --preset studio --preview   # also writes out_preview.jpg

Needs: numpy, Pillow (pip install numpy pillow).
"""
import argparse

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def vgrad(top, bottom, y0=0.0, y1=1.0):
    """Vertical gradient image (H, W, 3) from colour top at y0 to bottom at y1."""
    y = np.clip((np.linspace(0, 1, H) - y0) / max(1e-6, y1 - y0), 0, 1)[:, None, None]
    return np.broadcast_to(hexrgb(top) * (1 - y) + hexrgb(bottom) * y, (H, W, 3)).copy()


def radial(cx, cy, rx, ry, power=2.0):
    """Soft radial falloff 1 at (cx,cy) → 0 at the ellipse edge. Coordinates in 0..1."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx / W - cx) / rx) ** 2 + ((yy / H - cy) / ry) ** 2)
    return np.clip(1 - d, 0, 1) ** power


def add_light(img, mask, colour, gain):
    return img + mask[..., None] * hexrgb(colour) * gain


def to_pil(a):
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def from_pil(im):
    return np.asarray(im.convert("RGB"), np.float32) / 255


def bokeh_layer(rng, n, region, colours, rmin, rmax, alpha=(0.35, 1.0)):
    """Draw n light discs in region=(x0,y0,x1,y1) (0..1) on a black RGB layer; returns float array."""
    lay = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(lay)
    x0, y0, x1, y1 = region
    for _ in range(n):
        x = rng.uniform(x0, x1) * W
        y = rng.uniform(y0, y1) * H
        r = rng.uniform(rmin, rmax)
        c = colours[rng.integers(len(colours))]
        a = rng.uniform(*alpha)
        rgb = tuple(int(v * 255 * a) for v in hexrgb(c))
        d.ellipse([x - r, y - r, x + r, y + r], fill=rgb)
    return from_pil(lay)


def blur(a, r):
    return from_pil(to_pil(a).filter(ImageFilter.GaussianBlur(r)))


def screen(a, b):
    return 1 - (1 - np.clip(a, 0, 1)) * (1 - np.clip(b, 0, 1))


def finish(img, rng, vignette=0.55, grain=0.018):
    v = radial(0.5, 0.42, 0.95, 0.75, power=0.9)
    img = img * (1 - vignette + vignette * v[..., None])
    img = img + rng.normal(0, grain, (H, W, 1)).astype(np.float32)
    return np.clip(img, 0, 1)


def penthouse(rng, head_y, accent):
    img = vgrad("#0b1220", "#05070b", 0.0, 0.75)
    # window glass: dusk sky → hills → city band
    win = vgrad("#1a2a44", "#0e1a2c", 0.0, 0.32)
    hills = np.zeros((H, W), np.float32)
    xs = np.arange(W)
    ridge = 0.335 + 0.018 * np.sin(xs / 140.0 + rng.uniform(0, 6)) + 0.01 * np.sin(xs / 47.0)
    yy = np.arange(H)[:, None] / H
    hills[(yy > ridge[None, :])] = 1
    win = win * (1 - hills[..., None]) + hills[..., None] * hexrgb("#080d16")
    # horizon glow, then two depths of city lights: tiny far points and big soft near discs
    win = add_light(win, radial(0.45, 0.35, 0.9, 0.06, 1.2), "#ff9a4a", 0.18)
    far = bokeh_layer(rng, 260, (0.0, 0.345, 1.0, 0.42), ["#ffb766", "#ffd9a0", "#ffffff", "#9ec5ff"], 1.5, 3.5)
    near = bokeh_layer(rng, 70, (0.0, 0.33, 1.0, 0.5), ["#ffb766", "#ffcf8a", "#ff8a3d", "#bcd4ff"], 9, 24, (0.18, 0.55))
    win = screen(win, blur(far, 3) * 1.3)
    win = screen(win, blur(near, 5) * 0.9)
    win_mask = np.zeros((H, W), np.float32)
    win_mask[: int(0.58 * H), :] = 1
    img = img * (1 - win_mask[..., None]) + win * win_mask[..., None]
    # mullions + ceiling soffit
    mull = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mull)
    for x in (0.07, 0.36, 0.66, 0.93):
        d.rectangle([x * W - 14, 0, x * W + 14, 0.58 * H], fill=255)
    d.rectangle([0, 0.565 * H, W, 0.6 * H], fill=255)
    m = np.asarray(mull, np.float32)[..., None] / 255
    img = img * (1 - m * 0.85) + m * 0.85 * hexrgb("#05080d")
    # reflections of interior lights on the glass (soft diagonal streaks)
    streak = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(streak)
    for i in range(5):
        y = rng.uniform(0.05, 0.5) * H
        d.line([(0.1 * W, y), (0.62 * W, y - 40)], fill=(150, 120, 90), width=6)
    img = screen(img, blur(from_pil(streak), 10) * 0.35)
    # right wall with warm LED shelf strips
    wall = np.zeros((H, W), np.float32)
    wall[:, int(0.78 * W):] = 1
    img = img * (1 - wall[..., None] * 0.6)
    shelves = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(shelves)
    for k in range(7):
        y = (0.12 + k * 0.07) * H
        d.rectangle([0.8 * W, y, W, y + 5], fill=(255, 196, 120))
    img = screen(img, blur(from_pil(shelves), 6) * 1.1)
    img = screen(img, blur(from_pil(shelves), 30) * 0.5)
    # interior bounce + soft key glow behind the head
    img = add_light(img, radial(0.5, head_y, 0.55, 0.28, 1.6), "#2a3a5a", 0.35)
    img = add_light(img, radial(0.5, head_y + 0.05, 0.4, 0.2, 2.0), accent or "#3a4e78", 0.12)
    # dark glossy desk
    desk = np.clip((np.arange(H) / H - 0.8) / 0.02, 0, 1)[:, None, None]
    deskcol = vgrad("#12151b", "#030405", 0.8, 1.0)
    img = img * (1 - desk) + deskcol * desk
    img = blur(img, 6)  # depth of field: the whole set is behind the focus plane
    return img


def studio(rng, head_y, accent):
    img = vgrad("#2a2d33", "#0b0c0e", 0.0, 0.95)
    img = img * 0.55
    # soft key-light pool on the backdrop behind the head
    img = add_light(img, radial(0.5, head_y + 0.04, 0.85, 0.48, 1.2), "#c9cfd8", 0.26)
    img = add_light(img, radial(0.5, head_y + 0.04, 0.55, 0.3, 1.5), "#eef2f8", 0.10)
    # cool kicker from the left, warm fill from the right
    img = add_light(img, radial(0.0, 0.35, 0.6, 0.6, 1.5), "#4a6fa5", 0.22)
    img = add_light(img, radial(1.0, 0.45, 0.55, 0.55, 1.6), "#a5703a", 0.14)
    if accent:
        img = add_light(img, radial(0.5, head_y, 0.45, 0.25, 2.0), accent, 0.16)
    # seamless cove: floor slightly lighter then falling off
    floor = np.clip((np.arange(H) / H - 0.74) / 0.06, 0, 1)[:, None, None]
    img = img * (1 - floor * 0.35) + floor * 0.35 * vgrad("#1c1e22", "#050506", 0.74, 1.0)
    img = blur(img, 4)
    return img


def lounge(rng, head_y, accent):
    img = vgrad("#14100c", "#060403", 0.0, 0.9)
    # window with deep-blue night + fairy lights
    win = np.zeros((H, W), np.float32)
    win[int(0.08 * H):int(0.5 * H), int(0.18 * W):int(0.82 * W)] = 1
    win[:, int(0.495 * W):int(0.505 * W)] = 0  # mullion
    win[int(0.285 * H):int(0.292 * H), :] = 0
    win = np.asarray(Image.fromarray((win * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10)), np.float32) / 255
    img = img * (1 - win[..., None]) + win[..., None] * vgrad("#13244a", "#0a1328", 0.08, 0.5)
    fairy = bokeh_layer(rng, 260, (0.0, 0.05, 1.0, 0.75), ["#ffcf7a", "#ffe4b0", "#ffb04a"], 2, 5, (0.4, 1))
    edge = 1 - radial(0.5, 0.4, 0.42, 0.9, 0.6)
    img = screen(img, blur(fairy, 3) * edge[..., None] * 1.3)
    # fireplace glow bottom right + warm lamp left
    img = add_light(img, radial(0.92, 0.72, 0.35, 0.22, 1.5), "#ff7a26", 0.55)
    img = add_light(img, radial(0.05, 0.45, 0.3, 0.25, 1.8), "#ffb05a", 0.25)
    img = add_light(img, radial(0.5, head_y, 0.5, 0.26, 1.7), accent or "#3b2a1c", 0.18)
    img = blur(img, 7)
    return img


PRESETS = {"penthouse": penthouse, "studio": studio, "lounge": lounge}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--preset", choices=PRESETS, default="penthouse")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--head-y", type=float, default=0.30)
    ap.add_argument("--accent", default="")
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    img = PRESETS[a.preset](rng, a.head_y, a.accent)
    img = finish(img, rng)
    im = to_pil(img)
    im.save(a.out)
    if a.preview:
        im.resize((360, 640)).save(a.out.rsplit(".", 1)[0] + "_preview.jpg", quality=88)
    print(f"wrote {a.out} ({a.preset})")


if __name__ == "__main__":
    main()
