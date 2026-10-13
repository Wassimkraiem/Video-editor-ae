#!/usr/bin/env python3
"""Export FastAPI's OpenAPI document for the generated client pipeline."""

import json
from pathlib import Path

from services.api.main import app


def main() -> None:
    target = Path("packages/api-client/openapi.json")
    target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
