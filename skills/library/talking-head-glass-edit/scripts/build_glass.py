#!/usr/bin/env python3
"""
Build a whole glass edit from one plan file → index.html, compositions/graphics.html,
compositions/kinetic.html, edit/captions.json, transcript.json and fonts/.

The look, CSS, motion and timing helpers are the client-approved ones from
references/example/ (see references/design-system.md); this script only places the
content and the times the plan asks for, so a plan can be written in one pass.

Reads (project root)
  edit/plan.json    the plan (below)
  edit/words.json   the user's approved words [{"t", "s", "e"}] (seconds)
  edit/footage.json from prep_footage.py: {"duration", "shot_cuts"}

edit/plan.json
  {
    "captions": [{"from": 0, "to": 2}, {"from": 3, "to": 4, "hidden": "intro card"}, {"from": 5, "to": 7, "keys": [2]}],
        word index ranges into edit/words.json, in order, covering the speech; "hidden" when a
        card/kinetic beat already shows those words; "keys" = positions (0-based in the group)
        that get the gold keyword treatment. The text is always the approved words.
        Any group still on screen while a card or kinetic beat is up is hidden automatically
        (captions are gap-only), so keep cards to the phrase they illustrate (~1-2.5 s).
    "cards": [
      {"type": "intro",   "t": 1.6, "out": 2.32, "kicker": "KACHABITI · CACHEMIRE", "title": "قشابية الكشمير"},
      {"type": "chip",    "t": 5.0, "out": 6.38, "text": "دافية", "icon": "sun", "x": 560, "y": 928},   (x omitted = centred)
      {"type": "hero",    "t": 8.7, "out": 9.62, "kicker": "CACHEMIRE", "title": "HAUT DE GAMME"},
      {"type": "keyword", "t": 9.8, "a": "تدوم", "ta": 10.12, "b": "سنين", "tb": 10.62, "out": 10.74, "icon": "hour"},
      {"type": "price",   "t": 19.62, "out": 24.3, "label": "القشابية", "value": 79, "unit": "DT", "count_at": 19.88,
                          "sub": "كشمير haut de gamme", "old": "237 DT", "save": "-38 DT", "side": "right"},
      {"type": "list",    "t": 26.5, "out": 30.3, "title": "ابعثلنا ميساج", "icon": "chat", "side": "right",
                          "items": [{"text": "الطول", "t": 27.52}]},
      {"type": "badge",   "t": 29.34, "out": 30.35, "text": "توصيل لباب الدار", "icon": "truck", "side": "left"},
      {"type": "image",   "t": 6.5, "out": 8.4, "src": "assets/resources/screenshot.png", "y": 700, "w": 640, "caption": "optional"},
      {"type": "end",     "t": 30.58, "name": "KACHABITI", "sub": "CACHEMIRE", "logo": "assets/logo-white.png"}
    ],
    "kinetic": [
      {"t": 12.02, "out": 13.5, "icon": "family",
       "lines": [{"style": "ar", "words": [{"text": "نخرجو", "t": 12.02}, {"text": "بيها", "t": 12.62}]},
                 {"style": "latin", "text": "EN FAMILLE", "t": 12.92}]}
    ],      line styles: "ar" (words rise on onsets), "big" (large gold line), "latin" (letters cascade)
    "zooms": [{"t": 3.0, "to": 1.06, "dur": 1.8, "back": 4.9, "back_dur": 1.4}],
    "music": {"src": "assets/resources/music.mp3", "volume": 0.12}        (optional)
  }
Icons: sun snow hour check family tent tree chat truck gem star heart bolt tag phone pin clock
cart gift shield spark globe user camera.

Usage (project root): python <skill>/scripts/build_glass.py
"""
import html
import json
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ICONS = {
    "sun": '<circle cx="12" cy="12" r="4.5" /><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />',
    "snow": '<path d="M12 2v20M3.3 7l17.4 10M3.3 17l17.4-10M9.5 3.5 12 6l2.5-2.5M9.5 20.5 12 18l2.5 2.5" />',
    "hour": '<path d="M6 2h12M6 22h12M7 2c0 6 10 6 10 10S7 16 7 22M17 2c0 6-10 6-10 10s10 4 10 10" />',
    "check": '<path d="M4 12.5l5 5L20 6.5" />',
    "family": '<circle cx="7" cy="6" r="2.6" /><circle cx="17" cy="6" r="2.6" /><circle cx="12" cy="11.5" r="2" /><path d="M2.5 20v-3.5A4.5 4.5 0 0 1 7 12h0a4.5 4.5 0 0 1 3 1.1M21.5 20v-3.5A4.5 4.5 0 0 0 17 12h0a4.5 4.5 0 0 0-3 1.1M8.8 20v-1.7a3.2 3.2 0 0 1 6.4 0V20" />',
    "tent": '<path d="M12 3 2 21h20L12 3zM12 3l5.5 18M3.5 3.5 7 8M20.5 3.5 17 8" />',
    "tree": '<path d="M12 2 6 10h3l-4 6h14l-4-6h3L12 2zM12 16v6" />',
    "chat": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.8A8 8 0 1 1 21 12z" /><path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />',
    "truck": '<path d="M2 6h11v10H2zM13 9h4.5l3.5 3.5V16h-8" /><circle cx="6" cy="17.5" r="2" /><circle cx="17" cy="17.5" r="2" />',
    "gem": '<path d="M6 3h12l4 6-10 12L2 9l4-6zM2 9h20M9 3l3 18M15 3l-3 18" />',
    "star": '<path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4 6.1 20.5l1.2-6.5L2.5 9.4l6.6-.9z" />',
    "heart": '<path d="M12 20.5s-8-4.9-8-11A4.5 4.5 0 0 1 12 6.9 4.5 4.5 0 0 1 20 9.5c0 6.1-8 11-8 11z" />',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z" />',
    "tag": '<path d="M3 12V4h8l10 10-8 8z" /><circle cx="7.5" cy="8" r="1.4" />',
    "phone": '<path d="M5 3h4l2 5-2.5 1.5a11 11 0 0 0 6 6L16 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2z" />',
    "pin": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" />',
    "clock": '<circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" />',
    "cart": '<path d="M3 4h2.5l2.2 11h10.6l2-8H6.4" /><circle cx="9.5" cy="19.5" r="1.5" /><circle cx="17" cy="19.5" r="1.5" />',
    "gift": '<path d="M3 9h18v4H3zM5 13v8h14v-8M12 9v12M12 9C9 9 7 7.8 7 6.2S9.5 4 12 9c2.5-5 5-4.4 5-2.8S15 9 12 9z" />',
    "shield": '<path d="M12 2.5l8 3v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10v-6z" /><path d="M8.5 12l2.5 2.5 4.5-5" />',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />',
    "globe": '<circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />',
    "user": '<circle cx="12" cy="8" r="4" /><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />',
    "camera": '<path d="M3 7h4l2-2.5h6L17 7h4v12H3z" /><circle cx="12" cy="13" r="4" />',
}

FONT_FACES = """
        @font-face { font-family: "Kachabiti Sans"; src: url("fonts/segoeuib.ttf") format("truetype"); font-weight: 700; font-display: block; }
        @font-face { font-family: "Kachabiti Display"; src: url("fonts/majallab.ttf") format("truetype"); font-weight: 700; font-display: block; }
        @font-face { font-family: "Inter"; src: url("fonts/Inter-700-latin.woff2") format("woff2"); font-weight: 700; font-display: block; }"""

GRAPHICS_CSS = """
        #graphics { position: absolute; inset: 0; pointer-events: none; font-family: "Kachabiti Sans", sans-serif; color: #1b1712;
          --gold: #b08d4f; --gold-lt: #e9cf94; }
        .glass { position: absolute;
          background: linear-gradient(140deg, rgba(255,255,255,.26) 0%, rgba(255,255,255,.07) 45%, rgba(255,255,255,.14) 100%), rgba(24,19,14,.34);
          backdrop-filter: blur(22px) saturate(175%) brightness(.92); -webkit-backdrop-filter: blur(22px) saturate(175%) brightness(.92);
          border: 1.5px solid rgba(255,255,255,.42); border-radius: 26px;
          box-shadow: inset 0 1.5px 0 rgba(255,255,255,.7), inset 0 -1px 0 rgba(255,255,255,.18), inset 0 0 28px rgba(255,255,255,.1), 0 16px 40px rgba(0,0,0,.28);
          color: #fff; text-shadow: 0 1px 8px rgba(0,0,0,.35); }
        .latin { font-family: "Inter", sans-serif; font-weight: 700; direction: ltr; }
        svg.ic { fill: none; stroke: var(--gold); stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; }
        .intro-card { left: 190px; width: 700px; top: 850px; height: 214px; }
        .intro-kick { position: absolute; left: 0; right: 0; top: 868px; text-align: center; font-size: 20px; letter-spacing: .34em; color: var(--gold-lt); }
        .intro-title { position: absolute; left: 0; right: 0; top: 900px; text-align: center; font-family: "Kachabiti Display", serif; font-weight: 700; font-size: 104px; line-height: 1.05; direction: rtl; color: #fff; text-shadow: 0 2px 14px rgba(0,0,0,.35); }
        .intro-rule { position: absolute; left: 400px; width: 280px; top: 1030px; height: 2px; background: var(--gold); transform-origin: 50% 50%; }
        .chip { position: absolute; height: 76px; padding: 0 30px 0 26px; display: flex; align-items: center; gap: 12px; direction: rtl; border-radius: 38px; font-size: 36px; white-space: nowrap; }
        .chip.center { left: 0; right: 0; margin: 0 auto; width: fit-content; }
        .chip svg.ic { width: 32px; height: 32px; }
        .hero { position: absolute; left: 170px; width: 740px; top: 890px; height: 120px; border-radius: 60px; text-align: center; overflow: hidden;
          background: linear-gradient(140deg, rgba(255,255,255,.22) 0%, rgba(255,255,255,.04) 50%, rgba(233,207,148,.16) 100%), rgba(20,15,10,.5);
          backdrop-filter: blur(24px) saturate(170%); -webkit-backdrop-filter: blur(24px) saturate(170%);
          border: 1.5px solid rgba(233,207,148,.75); box-shadow: inset 0 1.5px 0 rgba(255,245,220,.75), inset 0 0 30px rgba(233,207,148,.12), 0 16px 44px rgba(0,0,0,.35); }
        .hero-k { position: absolute; left: 0; right: 0; top: 20px; font-size: 17px; letter-spacing: .42em; color: rgba(233,207,148,.75); }
        .hero-t { position: absolute; left: 0; right: 0; top: 44px; font-size: 50px; letter-spacing: .06em; color: var(--gold-lt); }
        .hero-sheen { position: absolute; top: -20px; left: 0; width: 160px; height: 160px; background: linear-gradient(100deg, rgba(255,255,255,0) 0%, rgba(255,240,200,.45) 50%, rgba(255,255,255,0) 100%); }
        .kw { left: 0; right: 0; margin: 0 auto; width: fit-content; top: 846px; height: 236px; padding: 0 64px; display: flex; align-items: center; gap: 26px; direction: rtl; border-radius: 118px; }
        .kw svg.ic { width: 84px; height: 84px; stroke: var(--gold-lt); stroke-width: 1.8; }
        .kw .kw-t { display: flex; gap: 26px; font-family: "Kachabiti Display", serif; font-weight: 700; font-size: 150px; line-height: 1; padding-top: 18px; overflow: hidden; }
        .kw .kw-w { display: inline-block; }
        .kw .kw-w.gold { color: var(--gold-lt); }
        .kw .kw-w.latin { font-size: .733em; }
        .kw .kw-line { position: absolute; left: 64px; right: 64px; bottom: 30px; height: 3px; border-radius: 2px; background: linear-gradient(90deg, rgba(233,207,148,0), var(--gold-lt), rgba(233,207,148,0)); }
        .price { top: 842px; width: 270px; height: 236px; text-align: center; overflow: hidden; }
        .price .bar { position: absolute; left: 0; right: 0; top: 0; height: 6px; background: var(--gold); }
        .price .pk { position: absolute; left: 0; right: 0; top: 26px; font-size: 30px; direction: rtl; }
        .price .pk.latin { font-size: 20px; letter-spacing: .3em; top: 34px; color: var(--gold-lt); }
        .price .pv { position: absolute; left: 0; right: 0; top: 74px; font-size: 100px; line-height: 1; letter-spacing: -.03em; }
        .price .pv small { font-size: 30px; letter-spacing: .04em; margin-left: 6px; color: var(--gold-lt); }
        .price .ps { position: absolute; left: 0; right: 0; top: 184px; font-size: 22px; color: rgba(255,255,255,.82); }
        .price .old { position: absolute; left: 30px; top: 184px; font-size: 24px; color: rgba(255,255,255,.7); }
        .price .strike { position: absolute; left: 26px; top: 198px; width: 112px; height: 3px; background: #b5452f; transform-origin: 0% 50%; }
        .price .save { position: absolute; right: 22px; top: 178px; height: 40px; padding: 0 14px; border-radius: 20px; background: var(--gold-lt); color: #1b1712; text-shadow: none; font-size: 22px; line-height: 40px; }
        .list { width: 270px; top: 800px; direction: rtl; }
        .list .lh { position: absolute; right: 22px; left: 18px; top: 20px; height: 52px; display: flex; align-items: center; gap: 10px; font-size: 30px; }
        .list .lh svg.ic { width: 36px; height: 36px; }
        .row { position: absolute; right: 26px; left: 20px; height: 52px; display: flex; align-items: center; gap: 12px; font-size: 30px; border-top: 1px solid rgba(176,141,79,.3); }
        .row svg.ic { width: 28px; height: 28px; stroke-width: 3; }
        .badge { width: 290px; height: 170px; top: 880px; text-align: center; direction: rtl; }
        .badge svg.ic { display: block; width: 72px; height: 72px; margin: 16px auto 4px; }
        .badge .tl { font-size: 32px; }
        .shot { padding: 14px; border-radius: 30px; }
        .shot img { display: block; width: 100%; border-radius: 18px; }
        .shot .cap { margin-top: 10px; text-align: center; font-size: 30px; direction: rtl; }
        .end { left: 300px; width: 480px; top: 90px; height: 168px; border-radius: 84px; }
        .end img { position: absolute; left: 46px; top: 26px; height: 116px; }
        .end .en { position: absolute; left: 236px; top: 50px; font-size: 30px; letter-spacing: .28em; }
        .end .es { position: absolute; left: 238px; top: 94px; font-size: 15px; letter-spacing: .3em; color: var(--gold-lt); }
        .end.nologo .en, .end.nologo .es { left: 0; right: 0; text-align: center; }"""

KINETIC_CSS = """
        #kinetic { position: absolute; inset: 0; overflow: hidden; font-family: "Kachabiti Sans", sans-serif; }
        .k-beat { position: absolute; inset: 0; opacity: 0; }
        .k-icon { position: absolute; left: 508px; width: 64px; height: 64px; filter: drop-shadow(0 2px 6px rgba(0,0,0,.55));
          fill: none; stroke: #e9cf94; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
        .k-icon path, .k-icon circle { stroke-dasharray: 1; stroke-dashoffset: 1; }
        .k-line { position: absolute; left: 40px; right: 40px; text-align: center; direction: rtl; overflow: hidden; padding: 6px 0 16px;
          text-shadow: 0 2px 10px rgba(0,0,0,.6), 0 0 28px rgba(0,0,0,.35); }
        .k-ar { font-family: "Kachabiti Display", serif; font-weight: 700; font-size: 86px; line-height: 1.1; color: #f4ede0; }
        .k-big { font-family: "Kachabiti Display", serif; font-weight: 700; font-size: 98px; line-height: 1.05; color: #e9cf94; }
        .k-lat { font-family: "Inter", sans-serif; font-weight: 700; font-size: 54px; letter-spacing: .06em; color: #e9cf94; direction: ltr; }
        .k-w { display: inline-block; margin: 0 9px; }
        .k-ch { display: inline-block; }"""


def esc(text):
    return html.escape(str(text), quote=True)


def is_latin(text):
    return str(text).isascii()


def latin_class(text):
    return " latin" if is_latin(text) else ""


def icon_use(name):
    return f'<svg class="ic"><use href="#i-{name if name in ICONS else "spark"}" /></svg>'


def num(value, default=0.0):
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default


def side_x(card, width, default="right"):
    if "x" in card:
        return int(card["x"])
    return 772 if card.get("side", default) == "right" else 38


def build_graphics(cards, duration):
    markup, script = [], []
    used = set()
    for index, card in enumerate(cards):
        kind = card.get("type")
        cid = f"g{index}"
        t, out = num(card.get("t")), num(card.get("out"), duration - 0.3)
        used.add(card.get("icon", ""))
        if kind == "intro":
            markup.append(f'<div id="{cid}" class="g-layer"><div id="{cid}-card" class="glass intro-card"></div>'
                          f'<div id="{cid}-kick" class="intro-kick latin" data-layout-allow-overlap>{esc(card.get("kicker", ""))}</div>'
                          f'<div id="{cid}-title" class="intro-title">{esc(card.get("title", ""))}</div><div id="{cid}-rule" class="intro-rule"></div></div>')
            script.append(f'popIn("#{cid}-card", {t}, {{ y: 16 }}); out("#{cid}-card", {out});'
                          f'tl.fromTo(q("#{cid}-kick"), {{ opacity: 0, scale: 1.25, filter: "blur(6px)" }}, {{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.5, ease: "power3.out" }}, {t + 0.02});'
                          f'popIn("#{cid}-title", {t + 0.06}, {{ y: 24 }}); tl.fromTo(q("#{cid}-rule"), {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.45, ease: "power3.inOut" }}, {t + 0.2});'
                          f'out("#{cid}-kick", {out - 0.02}); out("#{cid}-title", {out}); tl.to(q("#{cid}-rule"), {{ scaleX: 0, duration: 0.3, ease: "power2.in" }}, {out});')
        elif kind == "chip":
            if "x" in card:
                place, extra = f'style="left: {int(card["x"])}px; top: {int(card.get("y", 928))}px"', ""
            else:
                place, extra = f'style="top: {int(card.get("y", 928))}px"', " center"
            markup.append(f'<div id="{cid}" class="glass chip{extra}" {place}>{icon_use(card.get("icon", "check"))}<span class="{latin_class(card.get("text", "")).strip()}">{esc(card.get("text", ""))}</span></div>')
            script.append(f'popIn("#{cid}", {t}, {{ x: 30 }}); out("#{cid}", {out});')
        elif kind == "hero":
            markup.append(f'<div id="{cid}" class="hero"><div class="hero-k latin">{esc(card.get("kicker", ""))}</div>'
                          f'<div class="hero-t{latin_class(card.get("title", ""))}">{esc(card.get("title", ""))}</div><div id="{cid}-sheen" class="hero-sheen"></div></div>')
            script.append(f'tl.fromTo(q("#{cid}"), {{ opacity: 0, scale: 0.7, filter: "blur(10px)" }}, {{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.6, ease: "power2.out" }}, {t});'
                          f'tl.fromTo(q("#{cid}-sheen"), {{ x: -200 }}, {{ x: 900, duration: 0.9, ease: "power2.inOut" }}, {t + 0.25}); out("#{cid}", {out});')
        elif kind == "keyword":
            a, b = str(card.get("a", "")), str(card.get("b", ""))
            # Shrink long pairs so the pill stays inside the frame (~740 px for the words).
            est = sum(len(w) * (64 if is_latin(w) else 82) for w in (a, b) if w)
            size = int(150 * min(1.0, 740 / est)) if est else 150
            markup.append(f'<div id="{cid}" class="glass kw">{icon_use(card.get("icon", "gem"))}<div class="kw-t" style="font-size: {size}px">'
                          f'<span id="{cid}-a" class="kw-w{latin_class(a)}">{esc(a)}</span><span id="{cid}-b" class="kw-w gold{latin_class(b)}">{esc(b)}</span></div><div id="{cid}-l" class="kw-line"></div></div>')
            script.append(f'kw("#{cid}", {t}, {num(card.get("ta"), t)}, {num(card.get("tb"), t + 0.4)}, {out});')
        elif kind == "price":
            label = str(card.get("label", ""))
            parts = [f'<div class="bar"></div><div class="pk{latin_class(label)}">{esc(label)}</div>',
                     f'<div class="pv latin"><span id="{cid}-n">{esc(card.get("value", ""))}</span><small>{esc(card.get("unit", ""))}</small></div>']
            if card.get("old"):
                parts.append(f'<div id="{cid}-old" class="old latin">{esc(card["old"])}</div><div id="{cid}-strike" class="strike"></div>')
            if card.get("save"):
                parts.append(f'<div id="{cid}-save" class="save latin">{esc(card["save"])}</div>')
            elif card.get("sub"):
                parts.append(f'<div class="ps">{esc(card["sub"])}</div>')
            markup.append(f'<div id="{cid}" class="glass price" style="left: {side_x(card, 270)}px">{"".join(parts)}</div>')
            js = [f'popIn("#{cid}", {t}, {{ y: 24 }});']
            value = card.get("value")
            if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit():
                js.append(f'count("#{cid}-n", {num(value)}, {num(card.get("count_at"), t + 0.26)});')
            if card.get("old"):
                js.append(f'tl.fromTo(q("#{cid}-old"), {{ opacity: 0 }}, {{ opacity: 1, duration: 0.25 }}, {t + 1.2}); tl.fromTo(q("#{cid}-strike"), {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.25, ease: "power2.out" }}, {t + 1.4});')
            if card.get("save"):
                js.append(f'tl.fromTo(q("#{cid}-save"), {{ opacity: 0, scale: 0.85 }}, {{ opacity: 1, scale: 1, duration: 0.4, ease: "power2.out" }}, {t + 1.6});')
            js.append(f'out("#{cid}", {out});')
            script.append("".join(js))
        elif kind == "list":
            items = card.get("items", [])
            rows = "".join(f'<div id="{cid}-r{i}" class="row" style="top: {90 + 58 * i}px">{icon_use("check")}<span>{esc(item.get("text", ""))}</span></div>' for i, item in enumerate(items))
            height = 110 + 58 * len(items)
            markup.append(f'<div id="{cid}" class="glass list" style="left: {side_x(card, 270)}px; height: {height}px"><div id="{cid}-h" class="lh">{icon_use(card.get("icon", "chat"))}<span>{esc(card.get("title", ""))}</span></div>{rows}</div>')
            js = [f'popIn("#{cid}", {t}, {{ x: 40, y: 0 }}); popIn("#{cid}-h", {t + 0.12}, {{ y: 10 }});']
            for i, item in enumerate(items):
                at = num(item.get("t"), t + 0.4 + 0.35 * i)
                js.append(f'tl.fromTo(q("#{cid}-r{i}"), {{ opacity: 0, x: 24 }}, {{ opacity: 1, x: 0, duration: 0.3, ease: "power2.out" }}, {at}); tl.fromTo(q("#{cid}-r{i} svg"), {{ opacity: 0, scale: 0.6 }}, {{ opacity: 1, scale: 1, duration: 0.3, ease: "power2.out" }}, {at + 0.08});')
            js.append(f'out("#{cid}", {out});')
            script.append("".join(js))
        elif kind == "badge":
            markup.append(f'<div id="{cid}" class="glass badge" style="left: {side_x(card, 290, "left")}px">{icon_use(card.get("icon", "truck"))}<div class="tl">{esc(card.get("text", ""))}</div></div>')
            script.append(f'popIn("#{cid}", {t}, {{ x: -40, y: 0 }}); tl.fromTo(q("#{cid} svg"), {{ x: -30 }}, {{ x: 0, duration: 0.6, ease: "power3.out" }}, {t + 0.06}); out("#{cid}", {out});')
        elif kind == "image":
            width = int(card.get("w", 640))
            left = int(card.get("x", (1080 - width) // 2))
            caption = f'<div class="cap">{esc(card["caption"])}</div>' if card.get("caption") else ""
            markup.append(f'<div id="{cid}" class="glass shot" style="left: {left}px; top: {int(card.get("y", 640))}px; width: {width}px"><img src="{esc(card.get("src", ""))}" alt="">{caption}</div>')
            script.append(f'popIn("#{cid}", {t}, {{ y: 30 }}); out("#{cid}", {out});')
        elif kind == "end":
            logo = card.get("logo")
            img = f'<img src="{esc(logo)}" alt="">' if logo else ""
            markup.append(f'<div id="{cid}" class="glass end{"" if logo else " nologo"}">{img}<div id="{cid}-n" class="en latin">{esc(card.get("name", ""))}</div><div id="{cid}-s" class="es latin">{esc(card.get("sub", ""))}</div></div>')
            script.append(f'tl.fromTo(q("#{cid}"), {{ opacity: 0, scale: 0.85, filter: "blur(8px)" }}, {{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.55, ease: "power3.out" }}, {t});'
                          + (f'tl.fromTo(q("#{cid} img"), {{ opacity: 0, y: 12 }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }}, {t + 0.17});' if logo else "")
                          + f'tl.fromTo(q("#{cid}-n"), {{ opacity: 0, x: 24 }}, {{ opacity: 1, x: 0, duration: 0.8, ease: "power3.out" }}, {t + 0.32}); tl.fromTo(q("#{cid}-s"), {{ opacity: 0 }}, {{ opacity: 1, duration: 0.5 }}, {t + 0.62});')
        else:
            print(f"skipped unknown card type {kind!r}", file=sys.stderr)
    symbols = "\n".join(f'<symbol id="i-{name}" viewBox="0 0 24 24">{body}</symbol>' for name, body in ICONS.items())
    return f"""<!DOCTYPE html>
<html>
  <head><meta charset="UTF-8"></head>
  <body>
    <template>
      <style>{FONT_FACES}{GRAPHICS_CSS}
      </style>
      <div id="graphics" data-composition-id="graphics" data-width="1080" data-height="1920">
        <svg width="0" height="0" style="position: absolute"><defs>{symbols}</defs></svg>
        {chr(10).join("        " + item for item in markup)}
      </div>
      <script>
        (function () {{
          const tl = gsap.timeline({{ paused: true }});
          const q = (s) => "#graphics " + s;
          const popIn = (sel, at, from) =>
            tl.fromTo(q(sel), Object.assign({{ opacity: 0, y: -18, scale: 0.92, filter: "blur(6px)" }}, from || {{}}),
              {{ opacity: 1, y: 0, x: 0, scale: 1, filter: "blur(0px)", duration: 0.6, ease: "power2.out" }}, at);
          const out = (sel, at) => tl.to(q(sel), {{ opacity: 0, y: -14, filter: "blur(6px)", duration: 0.3, ease: "power2.in" }}, at);
          const kw = (id, tIn, tA, tB, tOut) => {{
            tl.fromTo(q(id), {{ opacity: 0, scale: 0.86, filter: "blur(12px)" }}, {{ opacity: 1, scale: 1, filter: "blur(0px)", duration: 0.5, ease: "power3.out" }}, tIn);
            tl.fromTo(q(id + " svg"), {{ opacity: 0, scale: 0.6 }}, {{ opacity: 1, scale: 1, duration: 0.5, ease: "power3.out" }}, tIn + 0.08);
            tl.fromTo(q(id + "-a"), {{ yPercent: 110, opacity: 0 }}, {{ yPercent: 0, opacity: 1, duration: 0.45, ease: "power3.out" }}, tA);
            tl.fromTo(q(id + "-b"), {{ yPercent: 110, opacity: 0, scale: 0.9 }}, {{ yPercent: 0, opacity: 1, scale: 1, duration: 0.5, ease: "power3.out" }}, tB);
            tl.fromTo(q(id + "-l"), {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.6, ease: "power2.inOut" }}, tB + 0.05);
            tl.to(q(id + " .kw-t"), {{ scale: 1.04, duration: Math.max(0.3, tOut - tB), ease: "sine.inOut" }}, tB);
            tl.to(q(id), {{ opacity: 0, scale: 1.06, filter: "blur(10px)", duration: 0.28, ease: "power2.in" }}, tOut);
          }};
          const count = (sel, to, at) => {{
            const box = {{ v: 0 }};
            tl.fromTo(box, {{ v: 0 }}, {{ v: to, duration: 0.7, ease: "power2.out", immediateRender: false,
              onUpdate: () => {{ const el = document.querySelector("#graphics " + sel); if (el) el.textContent = Math.round(box.v); }} }}, at);
          }};
          tl.set(q(".glass, .hero, .intro-kick, .intro-title, .row, .lh, .old, .save"), {{ opacity: 0 }}, 0);
          {chr(10).join("          " + line for line in script)}
          tl.to({{}}, {{ duration: {duration} }}, 0);
          window.__timelines["graphics"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
"""


def build_kinetic(beats):
    start = round(max(0.0, min(num(beat.get("t")) for beat in beats) - 0.3), 3)
    end = round(max(num(beat.get("out")) for beat in beats) + 0.5, 3)
    markup, script = [], []
    for index, beat in enumerate(beats):
        bid = f"k{index}"
        t, out = num(beat.get("t")), num(beat.get("out"))
        shift = int(beat.get("shift", 0))
        top = 1190 + shift
        icon = ICONS.get(beat.get("icon", "spark"), ICONS["spark"]).replace("<path ", '<path pathLength="1" ').replace("<circle ", '<circle pathLength="1" ')
        parts = [f'<svg class="k-icon" viewBox="0 0 24 24" style="top: {top - 68}px">{icon}</svg>']
        js = [f'beatIn("#{bid}", {t}); iconIn("#{bid}", {t - 0.02}); draw("#{bid}", {t + 0.03});']
        for li, line in enumerate(beat.get("lines", [])):
            style = line.get("style", "ar")
            if style == "latin":
                parts.append(f'<div id="{bid}-l{li}" class="k-line k-lat" style="top: {top}px"></div>')
                js.append(f'letters("#{bid}-l{li}", {json.dumps(str(line.get("text", "")).upper())}, {num(line.get("t"), t)});')
            else:
                cls = "k-big" if style == "big" else "k-ar"
                spans = []
                for wi, word in enumerate(line.get("words", [])):
                    spans.append(f'<span id="{bid}-l{li}w{wi}" class="k-w">{esc(word.get("text", ""))}</span>')
                    js.append(f'word("#{bid}-l{li}w{wi}", {num(word.get("t"), t)});')
                parts.append(f'<div class="k-line {cls}" style="top: {top}px">{"".join(spans)}</div>')
            top += 102 if style != "big" else 112
        js.append(f'beatOut("#{bid}", {out});')
        markup.append(f'<div id="{bid}" class="k-beat">{"".join(parts)}</div>')
        script.append(" ".join(js))
    doc = f"""<!doctype html>
<html>
  <head><meta charset="UTF-8" /></head>
  <body>
    <template>
      <style>{FONT_FACES}{KINETIC_CSS}
      </style>
      <div id="kinetic" data-composition-id="kinetic" data-width="1080" data-height="1920">
        {chr(10).join("        " + item for item in markup)}
      </div>
      <script>
        (function () {{
          const T0 = {start};
          const at = (t) => t - T0;
          const q = (s) => "#kinetic " + s;
          const tl = gsap.timeline({{ paused: true }});
          const beatIn = (b, t) => tl.fromTo(q(b), {{ opacity: 0 }}, {{ opacity: 1, duration: 0.2, ease: "none" }}, at(t) - 0.12);
          const beatOut = (b, t) => tl.to(q(b), {{ opacity: 0, y: -50, filter: "blur(10px)", duration: 0.4, ease: "power2.in" }}, at(t));
          const word = (w, t) => tl.fromTo(q(w), {{ yPercent: 110, opacity: 0, filter: "blur(8px)" }}, {{ yPercent: 0, opacity: 1, filter: "blur(0px)", duration: 0.55, ease: "power3.out" }}, at(t) - 0.05);
          const draw = (b, t) => tl.fromTo(q(b + " .k-icon path, " + b + " .k-icon circle"), {{ strokeDashoffset: 1 }}, {{ strokeDashoffset: 0, duration: 0.9, ease: "power2.inOut", stagger: 0.08 }}, at(t));
          const iconIn = (b, t) => tl.fromTo(q(b + " .k-icon"), {{ scale: 0.8, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.6, ease: "power2.out" }}, at(t));
          const letters = (id, text, t) => {{
            const el = document.querySelector("#kinetic " + id);
            if (el) el.innerHTML = text.split("").map((c) => '<span class="k-ch">' + (c === " " ? "&nbsp;" : c) + "</span>").join("");
            tl.fromTo(q(id + " .k-ch"), {{ opacity: 0, y: 40, filter: "blur(6px)" }}, {{ opacity: 1, y: 0, filter: "blur(0px)", duration: 0.45, ease: "power3.out", stagger: 0.035 }}, at(t));
          }};
          {chr(10).join("          " + line for line in script)}
          tl.to({{}}, {{ duration: {round(end - start, 3)} }}, 0);
          window.__timelines["kinetic"] = tl;
        }})();
      </script>
    </template>
  </body>
</html>
"""
    return doc, start, round(end - start, 3)


def build_index(duration, zooms, kinetic_window, music):
    pushes = []
    for zi, zoom in enumerate(zooms):
        peak, t = num(zoom.get("to"), 1.06), num(zoom.get("t"))
        dur = num(zoom.get("dur"), 1.8)
        back = num(zoom.get("back"), t + dur + 0.2)
        pushes.append(f"push(1, {peak}, {t}, {dur}, {str(zi == 0).lower()}); push({peak}, 1, {back}, {num(zoom.get('back_dur'), 1.4)});")
    kinetic = ""
    if kinetic_window:
        start, length = kinetic_window
        kinetic = f'\n      <div id="kinetic-host" class="layer clip" data-composition-id="kinetic" data-composition-src="compositions/kinetic.html" data-start="{start}" data-duration="{length}" data-track-index="4" data-width="1080" data-height="1920"></div>'
    music_tag = f'\n      <audio id="music" src="assets/music.wav" data-start="0" data-duration="{duration}" data-track-index="5" data-volume="{num(music.get("volume"), 0.12)}"></audio>' if music else ""
    return f"""<!DOCTYPE html>
<html lang="ar">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=1080, height=1920">
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #000; }}
      /* the footage plays untouched; only this wrapper scales for the punch-ins */
      #video-wrap {{ position: absolute; inset: 0; overflow: hidden; transform-origin: 50% 42%; will-change: transform; backface-visibility: hidden; }}
      #bg-video {{ width: 100%; height: 100%; object-fit: cover; }}
      .layer {{ position: absolute; inset: 0; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="1080" data-height="1920">
      <div id="video-wrap">
        <video id="bg-video" src="assets/source.mp4" playsinline data-has-audio="true" data-start="0" data-duration="{duration}" data-track-index="0"></video>
      </div>
      <div id="graphics-host" class="layer clip" data-composition-id="graphics" data-composition-src="compositions/graphics.html" data-start="0" data-duration="{duration}" data-track-index="1" data-width="1080" data-height="1920"></div>{kinetic}
      <div id="captions-host" data-track-kind="captions" class="layer clip" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{duration}" data-track-index="2" data-width="1080" data-height="1920"></div>
      <audio id="sfx" src="assets/sfx.wav" data-start="0" data-duration="{duration}" data-track-index="3" data-volume="0.55"></audio>{music_tag}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      const V = "#video-wrap";
      // slow, smooth pushes, GPU-composited so the frame scales sub-pixel without jitter
      const push = (from, to, at, dur, first) =>
        tl.fromTo(V, {{ scale: from }}, {{ scale: to, duration: dur, ease: "sine.inOut", force3D: true, immediateRender: !!first }}, at);
      {chr(10).join("      " + line for line in pushes)}
      tl.to({{}}, {{ duration: {duration} }}, 0);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def copy_fonts():
    """Arabic display/sans + Inter under the file names the templates load."""

    os.makedirs("fonts", exist_ok=True)
    recut = os.path.normpath(os.path.join(SKILL, "..", "talking-head-recut", "assets", "fonts", "Inter-700-latin.woff2"))
    wanted = {
        "segoeuib.ttf": ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf", "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.ttf"],
        "majallab.ttf": ["C:/Windows/Fonts/majallab.ttf", "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"],
        "Inter-700-latin.woff2": [recut],
    }
    for name, candidates in wanted.items():
        target = os.path.join("fonts", name)
        if os.path.exists(target):
            continue
        source = next((path for path in candidates if os.path.isfile(path)), None)
        if source:
            shutil.copyfile(source, target)
        else:
            print(f"warning: no font found for {name}", file=sys.stderr)


def main():
    plan = json.load(open("edit/plan.json", encoding="utf-8"))
    words = json.load(open("edit/words.json", encoding="utf-8"))
    footage = json.load(open("edit/footage.json", encoding="utf-8")) if os.path.exists("edit/footage.json") else {}
    duration = num(footage.get("duration"), (words[-1]["e"] + 0.5) if words else 1.0)

    # transcript.json is what build_captions.py snaps to the voice onsets.
    json.dump([{"text": w["t"], "start": w["s"], "end": w["e"]} for w in words], open("transcript.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    # Gap-only captions (design-system §9): cards and kinetic beats share the middle
    # band with the captions, so a caption on screen while one is up is hidden here
    # rather than trusted to the plan. The end card sits at the top and doesn't count.
    busy = [(num(c.get("t")) - 0.1, num(c.get("out"), duration)) for c in plan.get("cards", []) if c.get("type") != "end"]
    busy += [(num(b.get("t")) - 0.15, num(b.get("out")) + 0.4) for b in plan.get("kinetic", [])]
    spans = [(int(g["from"]), int(g["to"])) for g in plan.get("captions", [])]

    groups = []
    for gi, group in enumerate(plan.get("captions", [])):
        first, last = spans[gi]
        if not 0 <= first <= last < len(words):
            sys.exit(f"caption group {group} is outside the {len(words)} words")
        entry = {"words": [[words[i]["t"], [i]] for i in range(first, last + 1)]}
        # build_captions.py holds a phrase up to 0.9 s, never past the next one.
        shown_from = words[first]["s"]
        shown_to = min(words[last]["e"] + 0.9, words[spans[gi + 1][0]]["s"] if gi + 1 < len(spans) else duration)
        if not group.get("hidden") and any(start < shown_to and shown_from < end for start, end in busy):
            group = {**group, "hidden": "a card or kinetic beat is up"}
        if group.get("hidden"):
            entry["hidden"] = str(group["hidden"])
        if group.get("keys"):
            entry["keys"] = [int(k) for k in group["keys"]]
        groups.append(entry)
    json.dump({"duration": duration, "shot_cuts": footage.get("shot_cuts", []), "groups": groups}, open("edit/captions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    os.makedirs("compositions", exist_ok=True)
    open("compositions/graphics.html", "w", encoding="utf-8").write(build_graphics(plan.get("cards", []), duration))
    window = None
    if plan.get("kinetic"):
        doc, start, length = build_kinetic(plan["kinetic"])
        open("compositions/kinetic.html", "w", encoding="utf-8").write(doc)
        window = (start, length)
    elif os.path.exists("compositions/kinetic.html"):
        os.remove("compositions/kinetic.html")

    music = plan.get("music") or None
    if music:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", music["src"], "-t", str(duration), "-ac", "2", "-ar", "48000", "assets/music.wav"], check=True)
    open("index.html", "w", encoding="utf-8").write(build_index(duration, plan.get("zooms", []), window, music))
    copy_fonts()
    print(f"built: {len(plan.get('cards', []))} cards, {len(plan.get('kinetic', []))} kinetic beats, {len(plan.get('zooms', []))} zooms, {len(groups)} caption groups")


if __name__ == "__main__":
    main()
