#!/usr/bin/env python3
"""
Deterministic offline SFX pack for kinetic editorial reels.

Produces WAV 48 kHz / stereo / 16-bit files into OUT_DIR (default: ./assets/audio/sfx):
  - synthesised sounds (fixed RNG seeds -> identical output every run)
  - bundled Pixabay SFX converted from the media-use skill library
and writes manifest.json.

Every file is: trimmed so sound starts at ~sample 0, given a short fade-out,
peak-normalised to -3 dBFS (set the level in the mix).

Run:  python3 make_sfx.py [OUT_DIR] [--only name1,name2]
Needs: numpy, scipy, ffmpeg (/opt/homebrew/bin/ffmpeg or on PATH).
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = os.path.abspath(_args[0]) if _args else os.path.abspath("assets/audio/sfx")
# media-use is a sibling skill: resolve it next to this skill (works in
# ~/.claude/skills and in a project's .claude/skills), else fall back to home.
_SIBLING_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "media-use", "audio", "assets", "sfx")
LIB = os.path.normpath(_SIBLING_LIB) if os.path.isdir(_SIBLING_LIB) else os.path.expanduser("~/.claude/skills/media-use/audio/assets/sfx")
FFMPEG = "/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else shutil.which("ffmpeg")
TARGET_PEAK_DB = -3.0

MANIFEST = {}


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def tvec(dur):
    return np.arange(int(round(dur * SR))) / SR


def _sos(kind, f, order):
    return butter(order, f, kind, fs=SR, output="sos")


def lp(x, f, order=2):
    return sosfilt(_sos("low", f, order), x, axis=0)


def hp(x, f, order=2):
    return sosfilt(_sos("high", f, order), x, axis=0)


def bp(x, lo, hi, order=2):
    return sosfilt(_sos("band", [lo, hi], order), x, axis=0)


def noise(n, rng, corr=0.6):
    """Stereo gaussian noise with L/R correlation `corr` (1 = mono)."""
    a = rng.standard_normal((n, 2))
    a[:, 1] = corr * a[:, 0] + np.sqrt(1 - corr ** 2) * a[:, 1]
    return a


def st(m):
    """mono -> stereo (N,2)."""
    return np.stack([m, m], axis=1)


def pan(m, p):
    """Equal-power pan of a mono signal, p in [-1, 1]."""
    th = (p + 1) * np.pi / 4
    return np.stack([m * np.cos(th), m * np.sin(th)], axis=1) * np.sqrt(2)


def modal(dur, freqs, amps, taus, phases=None):
    """Sum of exponentially damped sines (starts at 0 -> click-free)."""
    t = tvec(dur)
    y = np.zeros_like(t)
    for i, (f, a, tau) in enumerate(zip(freqs, amps, taus)):
        ph = 0.0 if phases is None else phases[i]
        y += a * np.exp(-t / tau) * np.sin(2 * np.pi * f * t + ph)
    return y


def sweep_sine(freq_curve, harmonics=(1.0,)):
    """Sine (plus harmonics) following an instantaneous-frequency array."""
    ph = 2 * np.pi * np.cumsum(freq_curve) / SR
    y = np.zeros_like(ph)
    for k, a in enumerate(harmonics, start=1):
        y += a * np.sin(k * ph)
    return y


def place(buf, sig, t0):
    """Add `sig` into `buf` at time t0 (both (N,2) or (N,))."""
    i = int(round(t0 * SR))
    if i >= len(buf):
        return buf
    n = min(len(sig), len(buf) - i)
    buf[i:i + n] += sig[:n]
    return buf


def room_ir(dur, tau, rng, lo=180, hi=5500, predelay=0.006):
    """Simple stereo synthetic room impulse response."""
    t = tvec(dur)
    ir = noise(len(t), rng, corr=0.15) * np.exp(-t / tau)[:, None]
    ir = lp(hp(ir, lo), hi)
    ir[: int(predelay * SR)] = 0
    # a few early reflections
    for d, g in [(0.011, 0.5), (0.017, 0.35), (0.026, 0.25), (0.037, 0.18)]:
        i = int(d * SR)
        ir[i, 0] += g * (1 if d != 0.017 else 0.6)
        ir[i + 23, 1] += g
    return ir / np.sqrt((ir ** 2).sum(axis=0).mean())


def soft_sat(x, drive):
    return np.tanh(drive * x) / np.tanh(drive)


def load_lib(name):
    """Decode a bundled mp3 to float32 (N,2) at 48 kHz."""
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-i", os.path.join(LIB, name),
         "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)


# --------------------------------------------------------------------------- #
# finishing
# --------------------------------------------------------------------------- #
def smooth_env(x, win_ms=5):
    m = np.abs(x).max(axis=1)
    w = max(1, int(win_ms * SR / 1000))
    return np.convolve(m, np.ones(w) / w, mode="same")


def finish(x, fname, desc, source, fade_ms=40, head_db=-40.0,
           tail_db=None, max_dur=None, hp_hz=20):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = st(x)
    x = hp(x, hp_hz, order=2)  # remove DC / subsonic rumble
    peak = np.abs(x).max()
    # --- leading trim: first sample above head_db relative to peak, minus 0.5 ms
    thr = peak * 10 ** (head_db / 20)
    idx = np.argmax(np.abs(x).max(axis=1) > thr)
    idx = max(0, idx - int(0.0005 * SR))
    x = x[idx:]
    # --- trailing trim (bundled files): drop tail below tail_db rel peak
    if tail_db is not None:
        env = smooth_env(x, 10)
        above = np.where(env > peak * 10 ** (tail_db / 20))[0]
        if len(above):
            x = x[: min(len(x), above[-1] + int(0.02 * SR))]
    if max_dur is not None:
        x = x[: int(max_dur * SR)]
    # --- short fade-in guard (0.3 ms) against a DC step, fade-out
    fi = int(0.0003 * SR)
    x[:fi] *= np.linspace(0, 1, fi)[:, None]
    fo = min(int(fade_ms * SR / 1000), len(x) // 2)
    x[-fo:] *= (np.cos(np.linspace(0, np.pi / 2, fo)) ** 2)[:, None]
    # --- normalise
    x *= 10 ** (TARGET_PEAK_DB / 20) / np.abs(x).max()
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16)
    wavfile.write(os.path.join(OUT, fname), SR, pcm)
    dur = len(pcm) / SR
    peak_t = int(np.abs(pcm.astype(np.int32)).max(axis=1).argmax()) / SR
    MANIFEST[fname] = {
        "duration_s": round(dur, 3),
        "peak_s": round(peak_t, 3),
        "description": desc,
        "source": source,
    }
    print(f"  {fname:24s} {dur:6.3f}s  peak@{peak_t:.3f}s")


# --------------------------------------------------------------------------- #
# synthesised sounds
# --------------------------------------------------------------------------- #
def stamp_core(dur, rng, big=False):
    t = tvec(dur)
    n = len(t)
    # 1) low body thump: pitch-dropping sine, 2nd/3rd harmonic so it reads on phones
    f_hi, f_lo, tau = (84, 52, 0.11) if big else (98, 62, 0.065)
    f = f_lo + (f_hi - f_lo) * np.exp(-t / 0.03)
    body = sweep_sine(f, harmonics=(1.0, 0.22, 0.07))
    body *= (1 - np.exp(-t / 0.0015)) * np.exp(-t / tau)
    # low noise body (desk mass)
    bn = lp(rng.standard_normal(n), 260, 4) * np.exp(-t / (0.05 if big else 0.035))
    bn /= np.abs(bn).max()
    # 2) woody desk knock: damped modes
    wood_f = np.array([176, 305, 512, 870, 1430, 2250]) * (0.94 if big else 1.0)
    knock = modal(dur, wood_f, [0.45, 0.6, 0.5, 0.32, 0.2, 0.1],
                  [0.055, 0.04, 0.026, 0.016, 0.01, 0.006])
    # 3) rubber transient: dull, short broadband thwack (rubber = no bright ring)
    rub = lp(hp(rng.standard_normal(n), 700), 4200, 2) * np.exp(-t / 0.0035)
    rub /= np.abs(rub).max()
    # rubber pad compressing against paper: low-mid 'thock'
    pad = bp(rng.standard_normal(n), 180, 900, 2) * (1 - np.exp(-t / 0.0008)) * np.exp(-t / 0.011)
    pad /= np.abs(pad).max()
    tick = hp(rng.standard_normal(n), 3000) * np.exp(-t / 0.0009)
    tick /= np.abs(tick).max()
    # 4) paper slap (stereo, slightly decorrelated, 0.4 ms late)
    ps = bp(noise(n, rng, corr=0.55), 1600, 9000) * np.exp(-t / 0.016)[:, None]
    ps /= np.abs(ps).max()
    ps = np.roll(ps, int(0.0004 * SR), axis=0)
    ps[: int(0.0004 * SR)] = 0

    mono = (1.0 * body + 0.25 * bn + 0.8 * knock / np.abs(knock).max()
            + 0.6 * pad + 0.5 * rub + 0.12 * tick)
    # 5) bundled impact-bass-1 sub layer, enveloped to a short hit
    ib = load_lib("impact-bass-1.mp3").mean(axis=1)
    ib = ib[np.argmax(np.abs(ib) > 0.05 * np.abs(ib).max()):][:n]
    ib = lp(ib, 150, 4) * np.exp(-t[: len(ib)] / (0.07 if big else 0.05))  # attack punch only (avoids beating with body)
    ib /= np.abs(ib).max()
    mono[: len(ib)] += 0.28 * ib
    mono = soft_sat(mono / np.abs(mono).max(), 1.6)
    return st(mono) + (0.30 if big else 0.26) * ps


def make_stamp_thud():
    rng = np.random.default_rng(101)
    x = stamp_core(0.42, rng)
    finish(x, "stamp_thud.wav",
           "Heavy rubber stamp on paper over a wooden desk: pitch-dropping low thump + "
           "woody knock + dull rubber thwack + tiny paper slap. Signature sound.",
           "synth+bundled:impact-bass-1", fade_ms=70)


def make_stamp_thud_big():
    rng = np.random.default_rng(102)
    dry = stamp_core(0.72, rng, big=True)
    ir = room_ir(0.7, 0.085, np.random.default_rng(1020))
    wet = np.stack([fftconvolve(dry[:, c], ir[:, c])[: len(dry)] for c in range(2)], axis=1)
    wet *= np.abs(dry).max() / np.abs(wet).max()
    x = dry + 0.28 * wet
    finish(x, "stamp_thud_big.wav",
           "Bigger, lower final stamp with a short wooden-room tail. Use for the last/hero stamp.",
           "synth+bundled:impact-bass-1", fade_ms=180)


def crinkle_grain(rng, lo=1800, hi=8500):
    L = int(rng.uniform(0.002, 0.012) * SR)
    fc = np.exp(rng.uniform(np.log(lo), np.log(hi)))
    g = rng.standard_normal(L + 256)
    g = bp(g, fc / 1.6, min(fc * 1.6, 20000))[256:]
    g *= np.exp(-np.arange(L) / (L / 3.0))
    return g / (np.abs(g).max() + 1e-9)


def make_paper_rustle():
    rng = np.random.default_rng(201)
    dur = 0.5
    t = tvec(dur)
    n = len(t)
    # gesture envelope: quick handle + a second smaller shuffle
    env = (np.minimum(1, t / 0.012) * np.exp(-((t - 0.10) / 0.11) ** 2 * 0.9)
           + 0.6 * np.exp(-((t - 0.31) / 0.07) ** 2)) * np.exp(-np.maximum(0, t - 0.36) / 0.05)
    env = np.maximum(env, np.minimum(1, t / 0.004) * np.exp(-t / 0.05))
    flutter = lp(np.abs(rng.standard_normal(n)), 35, 2)
    flutter = 0.35 + flutter / flutter.max()
    bed = bp(noise(n, rng, corr=0.45), 1100, 7500) * (env * flutter)[:, None]
    body = bp(noise(n, rng, corr=0.6), 300, 1100) * (env * flutter)[:, None]
    x = 0.55 * bed / np.abs(bed).max() + 0.12 * body / np.abs(body).max()
    # crinkle grains, density following the envelope
    times = [0.0, 0.004]
    while len(times) < 70:
        tt = rng.uniform(0, 0.44)
        if rng.uniform() < env[int(tt * SR)]:
            times.append(tt)
    for tt in times:
        g = crinkle_grain(rng) * rng.uniform(0.25, 1.0) * env[int(tt * SR)]
        place(x, pan(g, rng.uniform(-0.6, 0.6)) * 0.45, tt)
    finish(x, "paper_rustle.wav",
           "Dry paper sheets handled/shuffled: band-passed noise bed with flutter + crinkle grains.",
           "synth", fade_ms=60)


def make_paper_flutter():
    rng = np.random.default_rng(301)
    dur = 1.3
    t = tvec(dur)
    n = len(t)
    x = np.zeros((n, 2))
    sheets = [(0.0, 0.85, -0.35), (0.10, 0.9, 0.3), (0.27, 0.8, -0.1), (0.42, 0.75, 0.5)]
    for k, (t0, length, p) in enumerate(sheets):
        tl = tvec(length)
        e = np.minimum(1, tl / (0.015 if k == 0 else 0.07)) * np.exp(-tl / (length * 0.38))
        # flapping rate drifts (sheet tumbling)
        rate = 7 + 3 * np.sin(2 * np.pi * rng.uniform(0.6, 1.4) * tl + rng.uniform(0, 6)) \
            + lp(rng.standard_normal(len(tl)), 3, 2) * 20
        flap = np.abs(np.sin(np.cumsum(2 * np.pi * rate / SR) + rng.uniform(0, 6))) ** 3.0
        s = bp(rng.standard_normal(len(tl)), 450, 4200) * (0.06 + flap) * e
        s /= np.abs(s).max()
        place(x, pan(s, p) * (1.0 - 0.12 * k), t0)
        # soft paper "tick" at a few flap peaks
        pk = np.where((flap[1:-1] > flap[:-2]) & (flap[1:-1] >= flap[2:]) & (flap[1:-1] > 0.97))[0]
        for i in pk[::3]:
            g = crinkle_grain(rng, 1500, 6000) * 0.18 * e[i]
            place(x, pan(g, p), t0 + i / SR)
    air = lp(hp(noise(n, rng, corr=0.3), 150), 1100) * (np.minimum(1, t / 0.05) * np.exp(-t / 0.5))[:, None]
    x += 0.2 * air / np.abs(air).max()
    x = lp(x, 7500)
    finish(x, "paper_flutter.wav",
           "Several sheets tumbling/fluttering through the air, gentle; staggered and panned sheets.",
           "synth", fade_ms=220)


def make_paper_slide():
    rng = np.random.default_rng(401)
    dur = 0.4
    t = tvec(dur)
    n = len(t)
    t_stop = 0.27
    env = (0.35 + 0.65 * np.sin(np.pi * np.clip(t / t_stop, 0, 1)) ** 0.8)
    env *= np.minimum(1, t / 0.004) * np.where(t < t_stop, 1, np.exp(-(t - t_stop) / 0.012))
    grip = 0.6 + 0.4 * lp(rng.standard_normal(n), 60, 2) / 0.15
    grip = np.clip(grip, 0.2, 1.4)
    bright = bp(noise(n, rng, corr=0.7), 2200, 8000)
    mid = bp(noise(n, rng, corr=0.7), 700, 2600)
    w = np.clip(1 - t / t_stop, 0.2, 1)  # decelerating -> less bright
    fr = (0.6 * w[:, None] * bright / np.abs(bright).max() + 0.5 * mid / np.abs(mid).max())
    fr *= (env * grip)[:, None]
    # slides in from the left a bit
    p = np.clip(-0.4 + 0.5 * t / t_stop, -0.4, 0.1)
    th = (p + 1) * np.pi / 4
    fr[:, 0] *= np.cos(th) * np.sqrt(2)
    fr[:, 1] *= np.sin(th) * np.sqrt(2)
    x = 0.6 * fr
    # settle: soft paper tap on the desk
    settle = modal(0.12, [190, 430, 880], [0.5, 0.35, 0.15], [0.02, 0.012, 0.007])
    tl = tvec(0.12)
    snap = hp(rng.standard_normal(len(tl)), 2500) * np.exp(-tl / 0.007)
    settle = settle / np.abs(settle).max() * 0.35 + 0.18 * snap / np.abs(snap).max()
    place(x, pan(settle, 0.1), t_stop - 0.004)
    finish(x, "paper_slide.wav",
           "A sheet sliding across a desk (friction noise that darkens as it slows) ending in a soft settle tap.",
           "synth", fade_ms=60)


def make_pen_scratch():
    rng = np.random.default_rng(501)
    dur = 0.6
    t = tvec(dur)
    n = len(t)
    strokes = [(0.0, 0.17, 3300), (0.2, 0.37, 2800), (0.405, 0.58, 3600)]
    x = np.zeros((n, 2))
    for s0, s1, fres in strokes:
        L = int((s1 - s0) * SR)
        tl = np.arange(L) / SR
        e = np.minimum(1, tl / 0.006) * np.minimum(1, (s1 - s0 - tl) / 0.02) * (0.8 + 0.2 * np.sin(np.pi * tl / (s1 - s0)))
        stick = np.abs(lp(rng.standard_normal(L), 180, 2))
        stick = 0.4 + stick / stick.max()
        fric = bp(noise(L, rng, corr=0.85), 2600, 10000) * (e * stick)[:, None]
        fric /= np.abs(fric).max()
        # nib resonance (the "scratchy" tone), slight glide per stroke
        res = bp(noise(L, rng, corr=0.9), fres * 0.93, fres * 1.07, 2) * (e * stick)[:, None]
        res /= np.abs(res).max()
        seg = 0.7 * fric + 0.35 * res
        # micro stick-slip ticks
        nt = int(170 * (s1 - s0))
        for tt in np.sort(rng.uniform(0, s1 - s0 - 0.003, nt)):
            k = int(tt * SR)
            tick = bp(rng.standard_normal(96 + 64), 3000, 8000)[64:] * np.exp(-np.arange(96) / 14)
            seg[k:k + 96] += st(tick / np.abs(tick).max() * 0.35 * e[k] * rng.uniform(0.3, 1))[: L - k]
        place(x, seg, s0)
    finish(x, "pen_scratch.wav",
           "Fountain-pen nib scratching on paper: three short strokes of high friction noise with nib resonance and stick-slip ticks. Subtle.",
           "synth", fade_ms=40)


def make_pin_click():
    rng = np.random.default_rng(601)
    dur = 0.1
    t = tvec(dur)
    n = len(t)
    pierce = hp(rng.standard_normal(n), 4500) * np.exp(-t / 0.0007)
    pierce /= np.abs(pierce).max()
    head = modal(dur, [2950, 4720, 7150], [1.0, 0.6, 0.3], [0.006, 0.004, 0.0025])
    head /= np.abs(head).max()
    cork = modal(dur, [240, 520, 1100], [0.9, 0.5, 0.25], [0.012, 0.008, 0.005])
    cork /= np.abs(cork).max()
    thud = lp(rng.standard_normal(n), 900, 2) * np.exp(-t / 0.004)
    thud /= np.abs(thud).max()
    m = 0.55 * pierce + 0.45 * head + 0.6 * cork + 0.3 * thud
    # pin seats: tiny second click 7 ms later
    m2 = np.zeros(n)
    place(m2, 0.3 * pierce[:1200] + 0.25 * head[:1200], 0.007)
    m += m2
    finish(st(m), "pin_click.wav",
           "Push-pin pressed into a cork board: sharp metal-tip tick, plastic head click, dull cork body, tiny seating click.",
           "synth", fade_ms=30)


def make_phone_vibrate():
    rng = np.random.default_rng(701)
    pulse, gap = 0.35, 0.15
    dur = 2 * pulse + gap + 0.04
    n = int(dur * SR)
    x = np.zeros((n, 2))
    wood_ir = modal(0.03, [410, 960, 1640, 2620, 3900], [1.0, 0.8, 0.55, 0.35, 0.2],
                    [0.006, 0.005, 0.004, 0.003, 0.002])
    for k, t0 in enumerate([0.0, pulse + gap]):
        L = int((pulse + 0.035) * SR)
        tl = np.arange(L) / SR
        on = tl < pulse
        f0 = 182 - 3 * k
        f = f0 * (1 - 0.28 * np.exp(-tl / 0.025))                   # spin-up
        f = np.where(on, f, f0 * np.exp(-(tl - pulse) / 0.05))      # spin-down
        f += lp(rng.standard_normal(L), 20, 2) * 6                   # motor jitter
        ph = np.cumsum(2 * np.pi * f / SR)
        env = np.minimum(1, tl / 0.012) * np.where(on, 1, np.exp(-(tl - pulse) / 0.012))
        buzz = (np.sin(ph) + 0.45 * np.sin(2 * ph + 0.3) + 0.25 * np.sin(3 * ph + 1.1)
                + 0.12 * np.sin(5 * ph)) * env
        # rattle: the phone taps the desk once per motor cycle
        cyc = np.floor(ph / (2 * np.pi))
        taps = np.zeros(L)
        idx = np.where(np.diff(cyc) > 0)[0] + 1
        taps[idx] = rng.uniform(0.6, 1.0, len(idx)) * env[idx] ** 1.5
        rattle = np.convolve(taps, wood_ir)[:L]
        rattle = hp(rattle, 300)
        rattle /= np.abs(rattle).max()
        buzz /= np.abs(buzz).max()
        rat_st = np.stack([rattle, np.roll(rattle, 9)], axis=1)
        seg = st(0.85 * buzz) + 0.5 * rat_st
        seg = soft_sat(seg / np.abs(seg).max(), 1.3)
        place(x, seg, t0)
    finish(x, "phone_vibrate.wav",
           "Smartphone vibrating on a wooden desk: two 0.35 s buzz pulses (~180 Hz motor with spin-up/down) with per-cycle wood rattle.",
           "synth", fade_ms=25)


def make_clock_tick_accel():
    rng = np.random.default_rng(801)
    T = 2.1
    n = int(T * SR)
    x = np.zeros((n, 2))
    r0, r1 = 4.0, 20.0
    a = np.log(r1 / r0)
    # rate r(t)=r0*exp(a t/T); ticks where integral of r crosses integers
    times = []
    k = 0
    while True:
        tk = T / a * np.log(1 + k * a / (r0 * T))
        if tk > T - 0.035:
            break
        times.append(tk)
        k += 1
    for i, tk in enumerate(times):
        tock = i % 2 == 1
        s = 0.89 if tock else 1.0
        dl = 0.05
        tl = tvec(dl)
        click = hp(rng.standard_normal(len(tl)), 2200) * np.exp(-tl / 0.0006)
        click /= np.abs(click).max()
        ring = modal(dl, np.array([1850, 3320, 5230, 7600]) * s, [0.8, 1.0, 0.6, 0.3],
                     [0.018, 0.011, 0.007, 0.004], phases=rng.uniform(0, 0.3, 4))
        ring /= np.abs(ring).max()
        case = modal(dl, np.array([640, 1120]) * s, [0.6, 0.4], [0.014, 0.01])
        case /= np.abs(case).max()
        tick = 0.6 * click + 0.55 * ring + 0.35 * case
        gain = (0.85 + 0.15 * tk / T) * rng.uniform(0.9, 1.0)   # slight tension build
        place(x, pan(tick, 0.08 if tock else -0.08) * gain, tk)
    finish(x, "clock_tick_accel.wav",
           f"Mechanical clock tick-tock accelerating exponentially from 4 to 20 ticks/s over 2.1 s ({len(times)} ticks).",
           "synth", fade_ms=40)


def make_bell_ding():
    dur = 1.4
    t = tvec(dur)
    rng = np.random.default_rng(901)
    parts = [  # (freq, amp, tau, L-detune, R-detune)
        (1182, 0.10, 0.55, 0.0, 0.0),
        (2364, 1.00, 0.42, 0.0, 0.0),
        (2364, 0.55, 0.40, 4.8, 3.6),     # split mode -> shimmer / beating
        (5486, 0.32, 0.19, 0.0, 0.0),
        (5486, 0.22, 0.17, 7.5, 9.0),
        (9030, 0.14, 0.08, 0.0, 0.0),
        (12880, 0.06, 0.04, 0.0, 0.0),
    ]
    x = np.zeros((len(t), 2))
    for f, a, tau, dl, dr in parts:
        for c, d in enumerate((dl, dr)):
            x[:, c] += a * np.exp(-t / tau) * np.sin(2 * np.pi * (f + d) * t)
    strike = hp(rng.standard_normal(len(t)), 3000) * np.exp(-t / 0.0012)
    strike /= np.abs(strike).max()
    x += st(0.35 * strike)
    finish(x, "bell_ding.wav",
           "Small counter/service bell 'ding': inharmonic modal bell (~2.36 kHz main partial) with split-mode shimmer, clapper strike, ~1.2 s decay.",
           "synth", fade_ms=300)


def make_sub_boom():
    dur = 0.8
    t = tvec(dur)
    n = len(t)
    rng = np.random.default_rng(1101)
    ib = load_lib("impact-bass-2.mp3")
    on = np.argmax(np.abs(ib).max(axis=1) > 0.1 * np.abs(ib).max())
    ib = ib[on:on + n]
    ib = lp(ib, 420, 4) * (np.exp(-t / 0.28))[:, None]
    ib /= np.abs(ib).max()
    f = 40 + 42 * np.exp(-t / 0.05)
    sub = sweep_sine(f, harmonics=(1.0, 0.15)) * (1 - np.exp(-t / 0.002)) * np.exp(-t / 0.32)
    knock = lp(rng.standard_normal(n), 1200, 2) * np.exp(-t / 0.008)
    knock /= np.abs(knock).max()
    x = 0.8 * ib + st(0.75 * sub + 0.18 * knock)
    x = soft_sat(x / np.abs(x).max(), 1.8)
    finish(x, "sub_boom.wav",
           "Low cinematic sub hit for a hard cut to black: impact-bass-2 hit re-enveloped + pitch-dropping 82->40 Hz sub + soft knock, gently saturated.",
           "synth+bundled:impact-bass-2", fade_ms=220, hp_hz=25)


def make_ripple_bubble():
    dur = 0.5
    t = tvec(dur)
    n = len(t)
    x = np.zeros((n, 2))

    def bloop(f0, f1, tau, L=0.18):
        tl = tvec(L)
        f = f0 + (f1 - f0) * (1 - np.exp(-tl / 0.035))
        y = sweep_sine(f, harmonics=(1.0, 0.12))
        return y * (1 - np.exp(-tl / 0.003)) * np.exp(-tl / tau)

    echoes = [(0.0, 1.0, 0.0, 1.0), (0.085, 0.42, -0.35, 0.94),
              (0.17, 0.22, 0.35, 0.89), (0.255, 0.11, -0.2, 0.84)]
    for i, (t0, g, p, s) in enumerate(echoes):
        b = bloop(470 * s, 1050 * s, 0.055 + 0.01 * i)
        b = lp(b, 5000 - 1000 * i)
        place(x, pan(b, p) * g, t0)
    ir = room_ir(0.4, 0.07, np.random.default_rng(1201), lo=250, hi=4000, predelay=0.012)
    wet = np.stack([fftconvolve(x[:, c], ir[:, c])[:n] for c in range(2)], axis=1)
    x = x + 0.22 * wet * np.abs(x).max() / np.abs(wet).max()
    finish(x, "ripple_bubble.wav",
           "Soft digital 'bloop' with three spreading, darker ripple echoes and a light tail — for an expanding circle.",
           "synth", fade_ms=120)

def make_tap():
    """iPhone-keyboard-style tap: ~70 ms bright click with a tiny woody body (for word reveals)."""
    rng = np.random.default_rng(3)
    t = tvec(0.07)
    click = rng.standard_normal(len(t)) * np.exp(-t / 0.0022)
    body = bp(click, 2600, 3900) * 0.9 + bp(click, 1200, 1700) * 0.6 + bp(click, 5600, 7000) * 0.3
    tick = np.sin(2 * np.pi * 700 * t) * np.exp(-t / 0.006) * 0.35
    finish(body + tick, "tap.wav",
           "iPhone-keyboard-style tap — one per caption word reveal (vol ~0.2, keywords ~0.3).",
           "synth", fade_ms=10)


# --------------------------------------------------------------------------- #
# bundled conversions
# --------------------------------------------------------------------------- #
BUNDLED = [
    # out name, source mp3, head_db, fade_ms, description
    ("whoosh.wav", "whoosh.mp3", -40, 40,
     "Punchy whoosh/impact — fast reveal or hard transition accent."),
    ("whoosh_cinematic.wav", "whoosh-cinematic.mp3", -40, 250,
     "Cinematic whoosh build (~5 s) — sweeping transition; align peak_s to the cut."),
    ("pop.wav", "pop.mp3", -30, 40,
     "Quick pop — element appear/spawn, chip/badge in."),
    ("notification.wav", "notification.mp3", -40, 200,
     "Notification chime — message-in / toast appears."),
    ("ping.wav", "ping.mp3", -40, 150,
     "Sharp electronic ping — accent on a key reveal."),
    ("click.wav", "click.mp3", -40, 20,
     "Crisp UI click — button press / selection."),
    ("key_press.wav", "key-press.mp3", -40, 20,
     "Single keyboard key press."),
    ("impact.wav", "impact-bass-1.mp3", -50, 300,
     "Heavy bass impact — a one-word punch frame (e.g. a big red single word)."),
]


def make_bundled(only=None):
    for out, src, head_db, fade_ms, desc in BUNDLED:
        if only is not None and out[:-4] not in only:
            continue
        x = load_lib(src)
        finish(x, out, desc, f"bundled:{os.path.splitext(src)[0]}",
               fade_ms=fade_ms, head_db=head_db, tail_db=-60)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = set(a.split("=", 1)[1].split(","))
    print("synth:")
    for fn in (make_tap, make_stamp_thud, make_stamp_thud_big, make_paper_rustle, make_paper_flutter,
               make_paper_slide, make_pen_scratch, make_pin_click, make_phone_vibrate,
               make_clock_tick_accel, make_bell_ding, make_sub_boom, make_ripple_bubble):
        if only is None or fn.__name__[5:] in only:
            fn()
    print("bundled:")
    make_bundled(only)
    mpath = os.path.join(OUT, "manifest.json")
    if os.path.exists(mpath):  # merge with an existing pack (e.g. --only runs)
        old = json.load(open(mpath))
        old.update(MANIFEST)
        MANIFEST.clear(); MANIFEST.update(old)
    with open(mpath, "w") as fh:
        json.dump(dict(sorted(MANIFEST.items())), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {len(MANIFEST)} files + manifest.json to {OUT}")
