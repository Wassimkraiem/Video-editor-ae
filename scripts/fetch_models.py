"""One-time setup: install the faster-whisper models the style skills use.

The studio never downloads models during an edit (agent runs set
WHISPER_OFFLINE=1). Run this once per machine, or point
WHISPER_MODELS_HOST_DIR at a folder that already has `fw-large-v3`.

    python scripts/fetch_models.py [--dir ~/.cache] [--model large-v3 ...]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=os.environ.get("WHISPER_MODELS_DIR") or os.path.expanduser("~/.cache"))
    parser.add_argument("--model", action="append", help="faster-whisper size; default large-v3 (what wassim-style, devin-style and talking-head-glass-edit use)")
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    for name in args.model or ["large-v3"]:
        target = Path(args.dir).expanduser() / f"fw-{name}"
        if (target / "model.bin").is_file():
            print(f"{name}: already installed at {target}")
            continue
        print(f"{name}: downloading to {target} ...")
        # local_dir avoids Hugging Face's symlinked cache, which fails on Windows without admin rights.
        snapshot_download(f"Systran/faster-whisper-{name}", local_dir=str(target))
        print(f"{name}: done")


if __name__ == "__main__":
    main()
