#!/usr/bin/env python3
"""
Write the SFX <audio> block into a HyperFrames index.html from a cue list.

  python3 place_sfx.py index.html cues.json [--taps] [--tap-vol 0.2] [--tap-key-vol 0.3]
                       [--sfx-dir assets/audio/sfx] [--duration 19.7]

cues.json: [{"name": "stamp_thud", "t": 3.25, "vol": 0.75},
            {"name": "whoosh_cinematic", "t": 0.0, "vol": 0.5, "media_start": 1.35, "dur": 1.7}, ...]
  name        = file stem inside sfx-dir (manifest.json gives durations)
  t           = global start time (s). For hits, start ~0.01 s before the visual impact
  vol         = data-volume (SFX sit under the voice: 0.08–0.4 typical, stamps/impacts 0.75–0.9)
  media_start = optional offset into the file (e.g. to land a whoosh's peak_s on a cut)
  dur         = optional max length (trim long beds/ticks to their scene)

--taps adds one `tap` per caption word: every element with class "w" and data-t (skips
".slam" words, which get a stamp/impact instead). Keywords (class "k") use --tap-key-vol.

The block is written between the markers  <!-- sfx:start -->  and  <!-- sfx:end -->
(inside the root composition div). Tracks are auto-allocated from 11 upward so no two
cues overlap on one Studio lane. Re-running replaces the block (idempotent).
"""
import json
import os
import re
import sys


def opt(name, default=None, cast=str):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    html_path, cues_path = sys.argv[1], sys.argv[2]
    root = os.path.dirname(os.path.abspath(html_path))
    sfx_dir = opt("--sfx-dir", "assets/audio/sfx")
    manifest = json.load(open(os.path.join(root, sfx_dir, "manifest.json")))
    s = open(html_path, encoding="utf-8").read()
    total = opt("--duration", None, float)
    if total is None:
        m = re.search(r'data-composition-id="[^"]+"[^>]*data-duration="([\d.]+)"', s) or \
            re.search(r'data-duration="([\d.]+)"[^>]*data-composition-id', s)
        total = float(m.group(1)) if m else 9999
    cues = json.load(open(cues_path))
    if "--taps" in sys.argv:
        tv, tk = opt("--tap-vol", 0.2, float), opt("--tap-key-vol", 0.3, float)
        for m in re.finditer(r'<span[^>]*class="w( [^"]*)?"[^>]*data-t="([\d.]+)"', s):
            cls = (m.group(1) or "").split()
            if "slam" in cls:
                continue
            cues.append({"name": "tap", "t": round(float(m.group(2)) - 0.02, 2),
                         "vol": tk if "k" in cls else tv})
    cues.sort(key=lambda c: c["t"])
    ends, lines, missing = {}, [], set()
    for i, c in enumerate(cues):
        f = c["name"] + ".wav"
        if f not in manifest:
            missing.add(c["name"]); continue
        ms = float(c.get("media_start", 0))
        d = manifest[f]["duration_s"] - ms
        if "dur" in c:
            d = min(d, float(c["dur"]))
        d = min(d, total - c["t"])
        if d <= 0.01:
            continue
        tr = 11
        while ends.get(tr, -1) > c["t"]:
            tr += 1
        ends[tr] = c["t"] + d
        extra = f' data-media-start="{ms}"' if ms else ""
        lines.append(f'      <audio id="sfx-{i:02d}-{c["name"].replace("_", "-")}" src="{sfx_dir}/{f}" '
                     f'data-start="{c["t"]}" data-duration="{d:.3f}"{extra} '
                     f'data-track-index="{tr}" data-volume="{c["vol"]}"></audio>')
    block = "<!-- sfx:start -->\n" + "\n".join(lines) + "\n      <!-- sfx:end -->"
    if "<!-- sfx:start -->" not in s:
        sys.exit("add <!-- sfx:start --> <!-- sfx:end --> markers inside the root composition first")
    s = re.sub(r"<!-- sfx:start -->.*?<!-- sfx:end -->", lambda _: block, s, flags=re.S)
    open(html_path, "w", encoding="utf-8").write(s)
    if missing:
        print("skipped (not in manifest — run make_sfx.py or add the file):", ", ".join(sorted(missing)))
    print(f"placed {len(lines)} cues on tracks 11–{max(ends) if ends else 11}")
