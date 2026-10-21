"""What kind of video this is and how much editing it gets, in words any style understands."""

from __future__ import annotations

KINDS = {
    "people": "A person talking or selling to camera (talking head, ad, UGC). The speaker and what they say are the hero; graphics support them, never compete with them.",
    "motion": "A fully motion-graphics video: there is no footage. Every scene is designed (type, shapes, icons, UI, objects) and paced like a reel.",
    "product": "A product launch / promo video: there is no footage. Introduce the product, show what it does and why it matters, end on the call to action.",
}

INTENSITY = {
    "minimal": "Edit intensity: MINIMAL. Clean, readable captions; a gentle punch-in only on the key lines; at most one graphic every 8-10 seconds and only for what matters (product or brand name, price or offer, a key number, the call to action). No stacked effects, no busy backgrounds, soft sound.",
    "balanced": "Edit intensity: BALANCED. The style's normal density.",
    "bold": "Edit intensity: BOLD. Use the style's full range: frequent graphics, scene changes and sound, while keeping everything readable and synced.",
}


def brand_text(brand: dict | None) -> str:
    """The user's brand kit as instructions every style (and auto-style) follows."""

    if not brand:
        return ""
    lines = []
    colors = [str(color) for color in brand.get("colors") or [] if str(color).strip()]
    if colors:
        lines.append(f"- Colours: {', '.join(colors)}. Build the palette from these (first = main/accent, then the rest in order); you may add neutrals (near-black, off-white) and tints of them, nothing else.")
    fonts = [str(font) for font in brand.get("fonts") or [] if str(font).strip()]
    if fonts:
        lines.append(f"- Fonts: {', '.join(fonts)} (first for headlines/keywords, second for body). Load them from Google Fonts; if one is not available there, use the closest free match and say so.")
    if str(brand.get("notes") or "").strip():
        lines.append(f"- Brand notes: {str(brand['notes']).strip()}")
    return "Brand kit (these override the style's own colours and fonts):\n" + "\n".join(lines) if lines else ""


def compose_request(brief: str, *, kind: str | None = None, intensity: str | None = None, script: str | None = None, brand: dict | None = None) -> str:
    """The first turn's request: the user's ideas plus the type, intensity, brand kit and script."""

    parts = [f"The user's ideas for this edit:\n{brief.strip()}" if brief.strip() else ""]
    if kind in KINDS:
        parts.append(f"Video type: {KINDS[kind]}")
    if intensity in INTENSITY:
        parts.append(INTENSITY[intensity])
    if kit := brand_text(brand):
        parts.append(kit)
    if script and script.strip():
        label = "Script / voice-over text (use these exact words on screen, in this order)" if kind in {"motion", "product"} else "Script"
        parts.append(f"{label}:\n{script.strip()}")
    return "\n\n".join(part for part in parts if part)
