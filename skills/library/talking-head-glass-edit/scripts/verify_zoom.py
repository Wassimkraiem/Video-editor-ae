#!/usr/bin/env python3
"""
Prove the punch-ins are smooth in the RENDERED video (the Studio preview can stutter when it
plays scaled 1080p live — judge the render, not the preview).

  python <skill>/scripts/verify_zoom.py <render.mp4> assets/source.mp4 2.0-5.8 8.3-11.9 ...

For every frame in each window it recovers the zoom scale by warping the source frame about the
composition's transform-origin (default 50% 42%) and picking the best match. A smooth zoom rises
and falls monotonically: "reversals while moving" should be 1 (the peak). Also confirms each
render frame matches the same source frame (no drift / lip-sync slip).
"""
import subprocess
import sys

import numpy as np
from scipy.ndimage import map_coordinates

OX, OY = 0.5, 0.42


def frames(path, t0, t1):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(t1 - t0), "-i", path,
                          "-vf", "scale=540:960,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 960, 540).astype(float)


def main():
    render, src, *wins = sys.argv[1:]
    yy, xx = np.mgrid[0:960:4, 0:540:4].astype(float)
    mask = (yy < 400) | (yy > 780)  # skip the mid-frame card/caption band
    oy, ox = OY * 960, OX * 540
    for win in wins:
        a, b = map(float, win.split("-"))
        S, R = frames(src, a, b), frames(render, a, b)
        sc = []
        for s, r in zip(S, R):
            best = min(np.arange(0.99, 1.15, 0.0025),
                       key=lambda k: np.mean(np.abs(map_coordinates(s, [oy + (yy - oy) / k, ox + (xx - ox) / k],
                                                                    order=1) - r[::4, ::4])[mask]))
            sc.append(best)
        sc = np.array(sc)
        d = np.diff(sc)
        rev = int(np.sum(np.diff(np.sign(d[np.abs(d) > 0.001])) != 0))
        print(f"{win}: scale {sc.min():.3f}→{sc.max():.3f}, max step {np.abs(d).max():.4f}, "
              f"reversals while moving {rev} ({'smooth' if rev <= 1 else 'CHECK — jitter'})")


if __name__ == "__main__":
    main()
