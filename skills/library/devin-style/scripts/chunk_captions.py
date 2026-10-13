#!/usr/bin/env python3
"""
Turn word timings into Devin-style caption cards: 1-4 short words, swapped hard on the spoken word,
max 2 short lines, one coloured glowing keyword line.

Inputs (project root)
  edit/words.json   [{"t","s","e"}] from transcribe.py (edit the "t" values to fix spelling)
  edit/keys.json    optional keyword colours, longest match wins:
                    {"stop using": "red", "luxurious": "yellow", "$6000": "red", "super easy": "green"}
                    colours: red | green | yellow | blue | purple | pink | orange

Output
  edit/captions.json  [{"s": start, "e": end, "key": colour|null, "lines": [[{"t": word, "k": bool}], ...]}]
  and a readable table on stdout.

Usage
  python <skill>/scripts/chunk_captions.py [--max-words 4] [--max-chars 16] [--gap 0.28] [--lead 0.03]
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
FPS = 30
END_PUNCT = re.compile(r"[.,!?;:…،؛؟]$")


def norm(t):
    return re.sub(r"[^\w$%€£'’\-]", "", t.lower())


def snap(t):
    return round(round(t * FPS) / FPS, 3)


def mark_keys(words, keys):
    """Set w['k'] = colour on words covered by the longest matching key phrase."""
    phrases = sorted(((k.split(), c) for k, c in keys.items()), key=lambda x: -len(x[0]))
    toks = [norm(w["t"]) for w in words]
    for w in words:
        w["k"] = None
    i = 0
    while i < len(words):
        for ph, col in phrases:
            n = len(ph)
            if [norm(p) for p in ph] == toks[i:i + n]:
                for j in range(i, i + n):
                    words[j]["k"] = col
                words[i]["kstart"] = n
                i += n - 1
                break
        i += 1


WEAK = {"a", "an", "the", "my", "your", "his", "her", "our", "their", "to", "of", "for", "and", "or",
        "if", "no", "i", "in", "on", "at", "with", "but", "so", "is", "be", "it's", "this", "that"}


def clean(t):
    """Display text: drop trailing , . ; : (keep ? and !)."""
    return re.sub(r"[,.;:…،؛]+$", "", t.strip())


def merge_numbers(words):
    """Whisper splits '$6,000' into '$6' + ',000' — glue such pieces back together."""
    out = []
    for w in words:
        if (out and re.match(r"^[,.]\d", w["t"]) and re.search(r"\d$", out[-1]["t"])
                and w["s"] - out[-1]["e"] < 0.15):
            out[-1] = {**out[-1], "t": out[-1]["t"] + w["t"], "e": w["e"]}
        else:
            out.append(dict(w))
    return out


def should_break(cur, w, max_words, max_chars, gap):
    prev = cur[-1]
    if w["s"] - prev["e"] > gap or END_PUNCT.search(prev["t"]):
        return True
    has_k = any(x["k"] for x in cur)
    if w["k"] and prev["k"] == w["k"] and not w.get("kstart"):
        return False  # never split a keyword phrase
    if w.get("kstart"):  # a keyword phrase may keep one short lead-in word ("MY $6000")
        return not (len(cur) == 1 and len(cur[0]["t"]) <= 3 and not has_k)
    if has_k:  # after the keyword: at most one trailing content word ("MY $6000 / CAMERA")
        last_k = max(i for i, x in enumerate(cur) if x["k"])
        return len(cur) - 1 - last_k >= 1 or len(clean(w["t"])) < 4
    chars = len(" ".join(clean(x["t"]) for x in cur + [w]))
    return len(cur) >= max_words or chars > max_chars


def chunk(words, max_words, max_chars, gap):
    cards, cur = [], []
    for w in words:
        if cur and should_break(cur, w, max_words, max_chars, gap):
            cards.append(cur)
            cur = []
        cur.append(w)
    if cur:
        cards.append(cur)
    # don't end a card on a dangling weak word ("... FOR THE") — push it to the next card
    for i in range(len(cards) - 1):
        c, n = cards[i], cards[i + 1]
        while (len(c) > 1 and norm(c[-1]["t"]) in WEAK and not c[-1]["k"] and not END_PUNCT.search(c[-1]["t"])
               and n[0]["s"] - c[-1]["e"] <= gap
               and len(" ".join(clean(x["t"]) for x in [c[-1]] + n)) <= max_chars + 4):
            n.insert(0, c.pop())
    # don't leave a tiny orphan card ("BE.") — fold it into the card before
    merged = []
    for c in cards:
        if (merged and len(c) == 1 and len(clean(c[0]["t"])) <= 3 and not c[0]["k"]
                and c[0]["s"] - merged[-1][-1]["e"] <= gap
                and not END_PUNCT.search(merged[-1][-1]["t"])
                and len(" ".join(clean(x["t"]) for x in merged[-1] + c)) <= max_chars + 4):
            merged[-1].append(c[0])
        else:
            merged.append(c)
    return [c for c in merged if c]


def lines_of(card, max_line):
    toks = [{"t": clean(w["t"]), "k": bool(w["k"]), "s": snap(w["s"])} for w in card]
    total = sum(len(t["t"]) for t in toks) + len(toks) - 1
    if len(toks) == 1 or total <= max_line:
        return [toks]
    # keyword words stay together on their own line
    if any(t["k"] for t in toks) and not all(t["k"] for t in toks):
        a = [t for t in toks if t["k"]]
        first_k = next(i for i, t in enumerate(toks) if t["k"])
        before, after = toks[:first_k], toks[first_k + len(a):]
        if before and after:
            return [before + a, after] if len(before) <= len(after) else [before, a + after]
        return [before or a, a if before else after]
    best, cut = 1e9, 1
    for c in range(1, len(toks)):
        l1 = sum(len(t["t"]) for t in toks[:c]) + c - 1
        l2 = sum(len(t["t"]) for t in toks[c:]) + len(toks) - c - 1
        if abs(l1 - l2) < best:
            best, cut = abs(l1 - l2), c
    return [toks[:cut], toks[cut:]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--max-chars", type=int, default=16)
    ap.add_argument("--line-chars", type=int, default=13)
    ap.add_argument("--gap", type=float, default=0.28)
    ap.add_argument("--hold", type=float, default=0.6, help="hide a card if the next starts later than this after its last word")
    ap.add_argument("--lead", type=float, default=0.03, help="show the card this much before the word")
    a = ap.parse_args()

    words = [dict(w) for w in json.load(open("edit/words.json", encoding="utf-8")) if w["t"].strip()]
    keys = json.load(open("edit/keys.json", encoding="utf-8")) if os.path.exists("edit/keys.json") else {}
    words = merge_numbers(words)
    mark_keys(words, keys)
    cards = chunk(words, a.max_words, a.max_chars, a.gap)

    out = []
    for i, c in enumerate(cards):
        s = snap(max(0, c[0]["s"] - a.lead))
        nxt = snap(max(0, cards[i + 1][0]["s"] - a.lead)) if i + 1 < len(cards) else None
        e = nxt if nxt is not None and nxt - c[-1]["e"] <= a.hold else snap(c[-1]["e"] + 0.25)
        key = next((w["k"] for w in c if w["k"]), None)
        out.append({"s": s, "e": max(e, s + 2 / FPS), "key": key, "lines": lines_of(c, a.line_chars)})
    json.dump(out, open("edit/captions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    for c in out:
        txt = " / ".join(" ".join(("*" + t["t"] + "*") if t["k"] else t["t"] for t in ln) for ln in c["lines"])
        print(f"{c['s']:6.2f}-{c['e']:6.2f}  {(c['key'] or ''):7} {txt.upper()}")
    dur = [c["e"] - c["s"] for c in out]
    print(f"\n{len(out)} cards, avg {sum(dur) / max(1, len(dur)):.2f}s on screen -> edit/captions.json")


if __name__ == "__main__":
    main()
