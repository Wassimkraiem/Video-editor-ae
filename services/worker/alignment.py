"""Put the user's own script on Whisper's timing.

The user pastes the exact words they said (their script, with the spelling and
mix of Darija / French / English they want on screen). Whisper already gave
every spoken word a time; this aligns the two word lists (Needleman-Wunsch on
a fuzzy similarity) so each script word takes the time of the Whisper word it
matches, and script words with no match share the time between their
neighbours, proportionally to their length.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

GAP = -0.45
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_KEEP = re.compile(r"[^\w]+", re.UNICODE)
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def normalize(token: str) -> str:
    text = unicodedata.normalize("NFKC", token).lower()
    text = _DIACRITICS.sub("", text).translate(_ARABIC_FOLD)
    return _KEEP.sub("", text)


def similarity(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _align(script: list[str], heard: list[str]) -> list[tuple[int, int]]:
    """Index pairs (script, heard) on the best alignment's diagonal moves."""

    n, m = len(script), len(heard)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[0] * (m + 1) for _ in range(n + 1)]  # 0 diag, 1 up (script only), 2 left (heard only)
    for i in range(1, n + 1):
        score[i][0], move[i][0] = i * GAP, 1
    for j in range(1, m + 1):
        score[0][j], move[0][j] = j * GAP, 2
    for i in range(1, n + 1):
        row, prev = score[i], score[i - 1]
        for j in range(1, m + 1):
            diag = prev[j - 1] + 2 * similarity(script[i - 1], heard[j - 1]) - 1
            up, left = prev[j] + GAP, row[j - 1] + GAP
            best = max(diag, up, left)
            row[j] = best
            move[i][j] = 0 if best == diag else 1 if best == up else 2
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        if move[i][j] == 0:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif move[i][j] == 1:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def align_script(text: str, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the script as studio transcript words timed from ``words``.

    ``words`` is the studio format (``text``, ``start_ms``, ``end_ms``). Line
    breaks in the script become segments.
    """

    tokens: list[tuple[str, int]] = []
    for line_no, line in enumerate(line for line in text.splitlines() if line.strip()):
        tokens.extend((token, line_no) for token in line.split())
    if not tokens:
        return []
    if not words:
        raise ValueError("there is no speech timing to align to yet")
    heard = [str(word["text"]) for word in words]
    anchors = dict(_align([token for token, _ in tokens], heard))

    timed: list[tuple[int, int] | None] = [None] * len(tokens)
    for i, j in anchors.items():
        timed[i] = (int(words[j]["start_ms"]), int(words[j]["end_ms"]))

    # Fill runs of unmatched script words between the times around them.
    i = 0
    while i < len(tokens):
        if timed[i] is not None:
            i += 1
            continue
        k = i
        while k < len(tokens) and timed[k] is None:
            k += 1
        before = timed[i - 1][1] if i > 0 else int(words[0]["start_ms"])
        after = timed[k][0] if k < len(tokens) else int(words[-1]["end_ms"])
        if after - before < 80 * (k - i):
            # No room between the neighbours: share the previous word's slot.
            if i > 0:
                before = timed[i - 1][0]
                i -= 1
            after = max(after, before + 80 * (k - i))
        lengths = [max(1, len(tokens[x][0])) for x in range(i, k)]
        total, cursor = sum(lengths), float(before)
        for x, length in zip(range(i, k), lengths):
            end = cursor + (after - before) * length / total
            timed[x] = (round(cursor), round(end))
            cursor = end
        i = k

    out = []
    for index, ((token, segment), span) in enumerate(zip(tokens, timed)):
        start, end = span or (0, 0)
        if out and start < out[-1]["end_ms"]:
            start = out[-1]["end_ms"]
        out.append({"id": f"s{index}", "text": token, "start_ms": start, "end_ms": max(start + 40, end), "segment": segment})
    return out
