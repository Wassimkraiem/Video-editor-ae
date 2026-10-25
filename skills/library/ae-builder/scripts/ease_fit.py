#!/usr/bin/env python3
"""
ease_fit.py  -  turn a source easing curve into After Effects keyframes that match it.

The source (an MP4's generating code, a CSS/GSAP ease, a spring) is a function f(u) for u in [0, 1]
that goes from 0 to 1 (springs and back-eases overshoot past 1 on the way).

How it works
  1. Split the curve at every turning point (velocity = 0): overshoot peaks and undershoot troughs
     become real keyframes, so the designer SEES the overshoot in the timeline.
  2. Each key gets the source's exact velocity at that moment (AE "speed").
  3. For each segment, search the out/in influences that make AE's bezier match the source.
  4. If a segment is still off by more than the tolerance, add a key at the worst point and refit.

AE's temporal bezier between key A (tA, vA) and key B (tB, vB), T = tB - tA:
  P1 = (tA + fo*T, vA + so*fo*T)      fo = out influence of A (0..1), so = out speed of A (units/s)
  P2 = (tB - fi*T, vB - si*fi*T)      fi = in influence of B (0..1),  si = in speed of B (units/s)

Usage
  python3 ease_fit.py                    # prints the preset table used in the skill
  from ease_fit import fit_keys
  keys = fit_keys(f, duration=0.65, delta=100)   # list of dicts: t, v, speed_in, infl_in, speed_out, infl_out
"""
import math
import numpy as np

TOL = 0.015          # max error as a fraction of the whole move (1.5 %)
N = 1200             # samples per curve


def deriv(f, u, h=1e-4):
    # measure just inside the ends: some library eases (expo) snap to exactly 0/1 at the ends,
    # which would read as a huge fake velocity
    u = min(max(u, 2e-3), 1 - 2e-3)
    return (f(u + h) - f(u - h)) / (2 * h)


def bez_eval(T, v0, v1, so, fo, si, fi, ts):
    """AE temporal bezier value at times ts (0..T)."""
    p0, p1, p2, p3 = (0.0, v0), (fo * T, v0 + so * fo * T), (T - fi * T, v1 - si * fi * T), (T, v1)
    s = np.linspace(0, 1, 600)
    x = (1 - s) ** 3 * p0[0] + 3 * (1 - s) ** 2 * s * p1[0] + 3 * (1 - s) * s ** 2 * p2[0] + s ** 3 * p3[0]
    y = (1 - s) ** 3 * p0[1] + 3 * (1 - s) ** 2 * s * p1[1] + 3 * (1 - s) * s ** 2 * p2[1] + s ** 3 * p3[1]
    order = np.argsort(x)
    return np.interp(ts, x[order], y[order])


def fit_segment(f, ua, ub, dur, delta):
    """Best influences for one segment; returns (fo, fi, max_err_fraction, worst_u)."""
    T = (ub - ua) * dur
    v0, v1 = f(ua) * delta, f(ub) * delta
    so, si = deriv(f, ua) * delta / dur, deriv(f, ub) * delta / dur
    us = np.linspace(ua, ub, 80)
    src = np.array([f(u) for u in us]) * delta
    ts = (us - ua) * dur
    best = (None, None, 1e9, None)
    grid = [0.1, 1, 5, 10, 15, 20, 25, 30, 33.33, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]
    for coarse in (True, False):
        if coarse:
            cand_o, cand_i = grid, grid
        else:
            bo, bi = best[0], best[1]
            cand_o = [x for x in np.arange(max(0.1, bo - 5), min(100, bo + 5) + 1e-9, 0.5)]
            cand_i = [x for x in np.arange(max(0.1, bi - 5), min(100, bi + 5) + 1e-9, 0.5)]
        for fo in cand_o:
            for fi in cand_i:
                ae = bez_eval(T, v0, v1, so, fo / 100, si, fi / 100, ts)
                err = np.abs(ae - src)
                e = err.max() / abs(delta)
                if e < best[2]:
                    best = (fo, fi, e, us[err.argmax()])
    return best[0], best[1], best[2], best[3], so, si


def turning_points(f):
    us = np.linspace(0, 1, N)
    d = np.array([deriv(f, u) for u in us])
    pts = []
    for i in range(1, N - 1):
        if (d[i - 1] > 0 >= d[i]) or (d[i - 1] < 0 <= d[i]):
            if 0.01 < us[i] < 0.99 and abs(f(us[i]) - 1) > 0.004:   # ignore wiggles smaller than 0.4 %
                pts.append(us[i])
    return pts


def fit_keys(f, duration=1.0, delta=1.0, tol=TOL, max_keys=8):
    knots = [0.0] + turning_points(f) + [1.0]
    while True:
        segs, worst = [], (0, None)
        for a, b in zip(knots[:-1], knots[1:]):
            fo, fi, e, wu, so, si = fit_segment(f, a, b, duration, delta)
            segs.append((a, b, fo, fi, e, so, si))
            if e > worst[0]:
                worst = (e, wu)
        if worst[0] <= tol or len(knots) >= max_keys:
            break
        knots = sorted(knots + [worst[1]])
    keys = []
    for i, u in enumerate(knots):
        k = {"t": u * duration, "v": f(u) * delta, "speed": deriv(f, u) * delta / duration}
        k["infl_out"] = segs[i][2] if i < len(segs) else None
        k["infl_in"] = segs[i - 1][3] if i > 0 else None
        keys.append(k)
    return keys, max(s[4] for s in segs)


# ------------------------------------------------------------------ presets
def spring(damp, freq):
    return lambda u: 1 - math.exp(-damp * u) * math.cos(freq * u)


def back(c1):
    c3 = c1 + 1
    return lambda u: 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


PRESETS = {
    "spring elegant (1-e^-5u cos 8u)": spring(5, 8),
    "spring snappy (1-e^-7u cos 13u)": spring(7, 13),
    "outBack (c1=1.70158)": back(1.70158),
    "outBack soft (c1=1.1)": back(1.1),
    "easeOutCubic": lambda u: 1 - (1 - u) ** 3,
    "easeInOutCubic": lambda u: 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2,
    "easeOutExpo": lambda u: 1 if u >= 1 else 1 - 2 ** (-10 * u),
    "easeInOutExpo": lambda u: 0 if u <= 0 else 1 if u >= 1 else (2 ** (20 * u - 10) / 2 if u < 0.5 else (2 - 2 ** (-20 * u + 10)) / 2),
    "easeInQuad (gravity drop)": lambda u: u * u,
    "easeOutQuad": lambda u: 1 - (1 - u) ** 2,
    "easeInOutSine": lambda u: -(math.cos(math.pi * u) - 1) / 2,
}

if __name__ == "__main__":
    print("Speeds are in units of (move size / duration); multiply by delta/duration for AE.\n")
    for name, f in PRESETS.items():
        keys, err = fit_keys(f)
        print(f"== {name}   keys={len(keys)}   max error={err*100:.2f}% of the move")
        for k in keys:
            io = "-" if k["infl_in"] is None else f"{k['infl_in']:.1f}"
            oo = "-" if k["infl_out"] is None else f"{k['infl_out']:.1f}"
            print(f"   at {k['t']:.3f}  value {k['v']:.3f}  speed {k['speed']:+.3f}   infl in {io:>5}  out {oo:>5}")
        print()


# ------------------------------------------------------------------ any sampled channel
def fit_samples(times, values, tol=0.02, max_keys=12):
    """Fit AE keys to ANY sampled channel from the source code (camera punch x drift, squash chains...).
    times/values: the channel sampled densely (e.g. 200+ samples per second) over ONE move.
    Returns (keys, max_error_fraction_of_range). Keys: dicts with absolute t, v, speed, infl_in, infl_out."""
    times, values = np.asarray(times, float), np.asarray(values, float)
    t0, t1 = times[0], times[-1]; rng = max(1e-9, values.max() - values.min())
    dur = t1 - t0
    def f(u): return np.interp(t0 + u * dur, times, values)
    def fn(u): return (f(u) - values[0]) / rng       # normalised so the fitter's maths stays the same
    knots = [0.0]
    d = np.gradient(values, times)
    eps = 1e-3 * rng / dur                      # ignore noise on flat stretches
    sgn = np.where(d > eps, 1, np.where(d < -eps, -1, 0))
    last = 0
    for i in range(1, len(d)):
        if sgn[i] == 0: continue
        if last and sgn[i] != last:             # real change of direction = a turning point
            u = (times[i] - t0) / dur
            if 0.01 < u < 0.99: knots.append(u)
        last = sgn[i]
    min_gap = (1 / 25) / dur                    # never two keys in the same frame
    clean = [knots[0]]
    for u in knots[1:]:
        if u - clean[-1] >= min_gap: clean.append(u)
    knots = clean + ([1.0] if 1.0 - clean[-1] >= min_gap else [])
    if knots[-1] != 1.0: knots[-1] = 1.0
    while True:
        segs, worst = [], (0, None)
        for a, b in zip(knots[:-1], knots[1:]):
            fo, fi, e, wu, so, si = fit_segment(fn, a, b, dur, rng)
            segs.append((a, b, fo, fi, e, so, si))
            if e > worst[0]: worst = (e, wu)
        if worst[0] <= tol or len(knots) >= max_keys: break
        if min(abs(worst[1] - k) for k in knots) < min_gap: break
        knots = sorted(knots + [worst[1]])
    keys = []
    for i, u in enumerate(knots):
        keys.append({"t": t0 + u * dur, "v": float(f(u)), "speed": float(deriv(fn, u) * rng / dur),
                     "infl_in": segs[i - 1][3] if i > 0 else None, "infl_out": segs[i][2] if i < len(segs) else None})
    return keys, max(s[4] for s in segs)


# ------------------------------------------------------------------ frame-aware fit of ONE real move (use this in generators)
def fit_move(f, t0, dur, fps=25, tol=0.02, sub=4, max_keys=10):
    """Fit one move as the MP4 shows it: keys only on whole frames, error measured at the frame times
    (plus `sub` sub-samples per frame, because motion blur shows in-between positions).
    f: normalised source curve u->fraction (0..1, may overshoot). t0/dur: the move's real start and length (s).
    Returns (keys, max_err). keys = [[t, fraction, speed (fraction per s), infl_in %, infl_out %], ...] (absolute t)."""
    fd = 1.0 / fps
    def g(t): return f(min(1.0, max(0.0, (t - t0) / dur)))
    def gd(t, h=1e-4):
        if t <= t0 or t >= t0 + dur: return 0.0
        return (g(t + h) - g(t - h)) / (2 * h)
    ks = math.floor(t0 * fps + 1e-6) / fps                      # last frame at or before the start
    ke = math.ceil((t0 + dur) * fps - 1e-6) / fps               # first frame at or after the end
    snapf = lambda t: round(t * fps) / fps
    knots = sorted(set([ks, ke] + [snapf(t0 + u * dur) for u in turning_points(f)]))
    knots = [k for k in knots if ks <= k <= ke]
    samples = np.arange(ks, ke + 1e-9, fd / sub)

    def seg_fit(a, b):
        T = b - a
        va, vb = g(a), g(b)
        sa, sb = gd(a), gd(b)
        ts = samples[(samples >= a - 1e-9) & (samples <= b + 1e-9)] - a
        src = np.array([g(a + t) for t in ts])
        best = (None, None, None, None, 1e9)
        mults = [1.0] if (a > ks and b < ke) else [0.6, 0.8, 1.0, 1.2, 1.4]     # free speeds only where the move starts/ends between frames
        for ma in (mults if a == ks else [1.0]):
            for mb in (mults if b == ke else [1.0]):
                for fo in [0.1, 5, 10, 15, 20, 25, 30, 33.33, 40, 50, 60, 70, 80, 90, 100]:
                    for fi in [0.1, 5, 10, 15, 20, 25, 30, 33.33, 40, 50, 60, 70, 80, 90, 100]:
                        ae = bez_eval(T, va, vb, sa * ma, fo / 100, sb * mb, fi / 100, ts)
                        e = np.abs(ae - src).max()
                        if e < best[4]: best = (fo, fi, sa * ma, sb * mb, e)
        return best

    while True:
        fits = [seg_fit(a, b) for a, b in zip(knots[:-1], knots[1:])]
        errs = [x[4] for x in fits]
        worst_i = int(np.argmax(errs))
        if errs[worst_i] <= tol or len(knots) >= max_keys: break
        a, b = knots[worst_i], knots[worst_i + 1]
        mid = snapf((a + b) / 2)
        if mid in knots or mid <= a or mid >= b: break
        knots = sorted(knots + [mid])
    keys = []
    for i, t in enumerate(knots):
        s_in = fits[i - 1][3] if i > 0 else (fits[0][2] if fits else 0)
        s_out = fits[i][2] if i < len(fits) else s_in
        keys.append([round(t, 6), float(g(t)), float(s_out if i < len(fits) else s_in),
                     fits[i - 1][1] if i > 0 else 33.33, fits[i][0] if i < len(fits) else 33.33])
    return keys, max(errs) if errs else 0.0
