#!/usr/bin/env python3
"""Build step of the generic fast engine (run from the composition folder).

Puts the fonts ENGINE.md promises into fonts/ (the renderer only knows fonts declared with
@font-face), then lints; lint errors exit 1 so the plan goes back for a repair.
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
FONTS = {
    "arabic.ttf": ["/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf", "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf"],
    "arabic-display.ttf": ["/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf", "C:/Windows/Fonts/majallab.ttf", "C:/Windows/Fonts/segoeuib.ttf"],
    "inter.woff2": [os.path.join(REPO, "skills", "library", "talking-head-recut", "assets", "fonts", "Inter-700-latin.woff2")],
}


def copy_fonts():
    os.makedirs("fonts", exist_ok=True)
    for name, candidates in FONTS.items():
        target = os.path.join("fonts", name)
        source = next((path for path in candidates if os.path.isfile(path)), None)
        if source and not os.path.exists(target):
            shutil.copyfile(source, target)


def main():
    copy_fonts()
    npx = shutil.which("npx") or "npx"
    done = subprocess.run([npx, "hyperframes", "lint", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    start = done.stdout.find("{")
    try:
        report = json.loads(done.stdout[start:]) if start != -1 else {}
    except json.JSONDecodeError:
        report = {}
    if not report:
        print(done.stdout[-2000:] + done.stderr[-2000:])
        sys.exit(done.returncode or 1)
    errors = [item for item in report.get("findings", []) if item.get("severity", "error") == "error"]
    if report.get("errorCount", len(errors)):
        for item in errors[:20]:
            print(f"- {item.get('code', '')}: {item.get('message', item)}")
        sys.exit(1)
    print(f"lint ok ({report.get('warningCount', 0)} warnings)")


if __name__ == "__main__":
    main()
