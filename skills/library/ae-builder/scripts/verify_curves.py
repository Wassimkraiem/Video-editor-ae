#!/usr/bin/env python3
"""
verify_curves.py - prove the keys a build script writes reproduce the source animation.

  DUMP_KEYS=/tmp/keys.json node ae_mock_dryrun.js Build.jsx
  python3 verify_curves.py /tmp/keys.json checks.json

checks.json: [{"key": "S1_Editor > Mascot > ADBE Position_1", "curve": "gravity", "t0": 3.78, "dur": 0.53,
               "from": -110, "to": 195, "dim": 0, "offset": 0}, ...]
  curve: a preset name from ease_fit.PRESETS ("spring elegant ...", "easeOutCubic"...) or a short alias below.
  t0 is in the COMP's own time (subtract the comp's offset in its parent if you authored in parent time).
Error is measured where the MP4 shows it: every frame and 4 sub-frames per frame across the move.
Exit code 1 if any check is worse than 2 % of its move.
"""
import json, math, sys
import numpy as np
from ease_fit import PRESETS
ALIAS = {"springElegant": "spring elegant (1-e^-5u cos 8u)", "springSnappy": "spring snappy (1-e^-7u cos 13u)", "outBack": "outBack (c1=1.70158)",
         "outBackSoft": "outBack soft (c1=1.1)", "outCubic": "easeOutCubic", "inOutCubic": "easeInOutCubic", "outExpo": "easeOutExpo",
         "inOutExpo": "easeInOutExpo", "gravity": "easeInQuad (gravity drop)", "outQuad": "easeOutQuad", "inOutSine": "easeInOutSine"}

def ae_curve(rec, dim=0):
    K, E, ts, vs = rec["keys"], rec["eases"], [], []
    for i in range(len(K) - 1):
        a, b = K[i], K[i + 1]; T = b["t"] - a["t"]
        pick = lambda v: v[dim] if isinstance(v, list) else v
        va, vb = pick(a["v"]), pick(b["v"])
        eo, ei = E.get(str(i + 1)), E.get(str(i + 2))
        so, fo = (eo[1][min(dim, len(eo[1]) - 1)] if eo else (0, 33.33))
        si, fi = (ei[0][min(dim, len(ei[0]) - 1)] if ei else (0, 33.33))
        s = np.linspace(0, 1, 600); P = [(0, va), (fo / 100 * T, va + so * fo / 100 * T), (T - fi / 100 * T, vb - si * fi / 100 * T), (T, vb)]
        B = [(1 - s) ** 3, 3 * (1 - s) ** 2 * s, 3 * (1 - s) * s ** 2, s ** 3]
        ts += list(a["t"] + sum(B[j] * P[j][0] for j in range(4))); vs += list(sum(B[j] * P[j][1] for j in range(4)))
    ts, vs = np.array(ts), np.array(vs); o = np.argsort(ts); return ts[o], vs[o]

if __name__ == "__main__":
    dump, checks = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])); bad = 0
    for c in checks:
        f = PRESETS[ALIAS.get(c["curve"], c["curve"])]
        if c["key"] not in dump: print("MISSING", c["key"]); bad += 1; continue
        ts, vs = ae_curve(dump[c["key"]], c.get("dim", 0))
        t0, dur, a, b = c["t0"], c["dur"], c["from"], c["to"]
        tt = np.arange(math.floor(t0 * 25) / 25, math.ceil((t0 + dur) * 25) / 25 + 1e-9, 0.01)
        ref = np.array([a + (b - a) * f(min(1, max(0, (x - t0) / dur))) for x in tt]); ae = np.interp(tt, ts, vs)
        e = np.abs(ae - ref).max() / abs(b - a) * 100; bad += e > 2
        print(f"{'OK ' if e <= 2 else 'BAD'} {e:5.2f}%  {c['key']}")
    sys.exit(1 if bad else 0)
