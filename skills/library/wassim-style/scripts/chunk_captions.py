#!/usr/bin/env python3
"""
Group edit/words.json into wassim-style caption pills → edit/captions.json.

A pill holds one short phrase (2-4 words, <= ~24 chars). The pill is sized for the whole phrase when
it appears and the words fill in one by one on their spoken onsets. Keywords (edit/keys.json) get the
maroon highlight box.

edit/keys.json:  ["AI", "impossible", "productivity"]      (case-insensitive substring match per word)
             or  {"AI": "maroon", "برشا": "green"}          (colour per keyword: maroon | green | gold)

edit/phrases.txt (optional, recommended): one pill per line, the transcript words in order, e.g.
  إيجا نفسرلك
  كيفاش تحمي خدمتك
  من الـ AI
Lines only regroup the words (spaces ignored when matching); they never change the wording or timing.

Usage (project root):
  python <skill>/scripts/chunk_captions.py [--max-words 4] [--max-chars 24] [--gap 0.32] [--hold 0.5]
Prints a table; re-run with other keys/limits until it reads like short headline phrases.
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

# a pill should not END on these (they lean on the next word)
DANGLING = {"من", "في", "باش", "اللي", "و", "على", "مع", "ال", "الـ", "هي", "إنك", "أما", "كيفاش", "خاطر", "كل",
            "the", "a", "an", "of", "to", "and", "my", "your", "in", "on", "for", "with", "is", "de", "la", "le", "les", "et"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--max-chars", type=int, default=24)
    ap.add_argument("--gap", type=float, default=0.32, help="a silence longer than this always ends a pill")
    ap.add_argument("--hold", type=float, default=0.5, help="keep a pill this long after its last word if nothing follows")
    a = ap.parse_args()

    words = json.load(open("edit/words.json", encoding="utf-8"))
    keys = json.load(open("edit/keys.json", encoding="utf-8")) if os.path.exists("edit/keys.json") else []
    if isinstance(keys, list):
        keys = {k: "maroon" for k in keys}
    keys = {k.lower(): v for k, v in keys.items()}

    def key_of(t):
        tl = t.lower()
        for k, v in keys.items():
            if k in tl:
                return v
        return None

    groups, cur = [], []
    if os.path.exists("edit/phrases.txt"):
        norm = lambda x: "".join(x.split())
        lines = [norm(l) for l in open("edit/phrases.txt", encoding="utf-8") if l.strip()]
        wi = 0
        for li, line in enumerate(lines):
            g, acc = [], ""
            while wi < len(words) and len(acc) < len(line):
                g.append(words[wi]); acc += norm(words[wi]["t"]); wi += 1
            if acc != line:
                sys.exit(f"phrases.txt line {li + 1} does not match the words: '{line}' vs '{acc}'")
            groups.append(g)
        if wi < len(words):
            groups.append(words[wi:])
        words = []
    for i, w in enumerate(words):
        if cur:
            gap = w["s"] - cur[-1]["e"]
            chars = sum(len(x["t"]) + 1 for x in cur) + len(w["t"])
            full = len(cur) >= a.max_words or chars > a.max_chars
            if gap > a.gap or (full and cur[-1]["t"] not in DANGLING) or len(cur) >= a.max_words + 1:
                groups.append(cur)
                cur = []
        cur.append(w)
    if cur:
        groups.append(cur)

    caps = []
    for gi, g in enumerate(groups):
        s = g[0]["s"]
        nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else None
        e = g[-1]["e"] + a.hold
        if nxt is not None:
            e = min(e, nxt)
        caps.append({"s": round(max(0, s - 0.04), 3), "e": round(e, 3),
                     "words": [{"t": w["t"], "s": w["s"], "e": w["e"], **({"k": key_of(w["t"])} if key_of(w["t"]) else {})} for w in g]})
    json.dump(caps, open("edit/captions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for c in caps:
        txt = " ".join(("[" + w["t"] + "]") if w.get("k") else w["t"] for w in c["words"])
        print(f"{c['s']:6.2f}-{c['e']:6.2f}  {txt}")
    print(f"\n{len(caps)} pills -> edit/captions.json")


if __name__ == "__main__":
    main()
