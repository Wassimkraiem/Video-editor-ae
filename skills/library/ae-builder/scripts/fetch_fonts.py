#!/usr/bin/env python3
"""
fetch_fonts.py - put the exact font files a rebuild needs into <project>/fonts, with their licences.

  python3 fetch_fonts.py OUT_DIR "Unbounded:Black" "Space Grotesk:Medium,SemiBold,Bold"

Why: the build script sets text by PostScript name (e.g. "Unbounded-Black"). If the user doesn't have the font,
AE silently substitutes. So the font files ship INSIDE the delivery zip and the script opens that folder if
anything is missing. Run this at the START of a project, while the network works, and copy the result into the
persistent outputs folder straight away (sandboxes reset and lose /home files).

Only open-licence fonts (OFL / Apache / UFL, e.g. everything on Google Fonts) may be bundled. For commercial fonts,
do not bundle: tell the user up front and give the purchase/download link.

Checks every download is a real font file (a blocked network returns small text pages that look like files).
"""
import os, sys, re, urllib.request

WEIGHTS = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800, "Black": 900}

def real_font(b):
    return len(b) > 10000 and b[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            return r.read()
    except Exception as e:
        return None

def fetch(family, styles, out):
    slug, nospace = family.lower().replace(" ", ""), family.replace(" ", "")
    got, lic = [], None
    for lic_dir in ("ofl", "apache", "ufl"):
        base = f"https://raw.githubusercontent.com/google/fonts/main/{lic_dir}/{slug}"
        for style in styles:
            name = f"{nospace}-{style}.ttf"
            for url in (f"{base}/static/{name}", f"{base}/{name}"):
                b = get(url)
                if b and real_font(b):
                    open(os.path.join(out, name), "wb").write(b); got.append(name); break
        if got:
            for lf in ("OFL.txt", "LICENSE.txt"):
                b = get(f"{base}/{lf}")
                if b and len(b) > 500 and b"<html" not in b[:200].lower():
                    lic = f"{nospace}_{lf}"; open(os.path.join(out, lic), "wb").write(b); break
            missing = [s for s in styles if f"{nospace}-{s}.ttf" not in got]
            if missing:   # family ships only as a variable font: bundle that (named instances still install)
                for url in (f"{base}/{nospace}[wght].ttf", f"{base}/{nospace}%5Bwght%5D.ttf"):
                    b = get(url)
                    if b and real_font(b):
                        open(os.path.join(out, f"{nospace}-Variable.ttf"), "wb").write(b); got.append(f"{nospace}-Variable.ttf (covers {', '.join(missing)})"); break
            break
    if not got:   # fallback: Fontsource CDN (also open-licence Google fonts)
        for style in styles:
            w = WEIGHTS.get(style, 400)
            b = get(f"https://cdn.jsdelivr.net/fontsource/fonts/{slug.replace(' ','-')}@latest/latin-{w}-normal.ttf")
            if b and real_font(b):
                n = f"{nospace}-{style}.ttf"; open(os.path.join(out, n), "wb").write(b); got.append(n)
    return got, lic

if __name__ == "__main__":
    out = sys.argv[1]; os.makedirs(out, exist_ok=True); ok = True
    for spec in sys.argv[2:]:
        fam, _, st = spec.partition(":"); styles = [s.strip() for s in (st or "Regular").split(",")]
        got, lic = fetch(fam.strip(), styles, out)
        print(f"{fam}: {', '.join(got) if got else 'NOT FOUND'}" + (f"  (licence: {lic})" if lic else ""))
        ok = ok and bool(got)
    try:
        from fontTools.ttLib import TTFont
        for f in sorted(os.listdir(out)):
            if f.endswith(".ttf"):
                print("  PostScript name:", TTFont(os.path.join(out, f))["name"].getDebugName(6), "<-", f)
    except Exception:
        print("  (install fontTools to print PostScript names: pip install fonttools)")
    if not ok:
        print("\nSome fonts could not be downloaded (no network?). Tell the user NOW, with the download links, "
              "rather than at hand-off; or ask them to enable network access so they can be bundled.")
        sys.exit(1)
