"""OpenAI image generation adapter with prompt-hash caching."""

from __future__ import annotations

import hashlib
import json
import base64
from pathlib import Path
from typing import Any


class ImageGenerator:
    def __init__(self, client, model: str = "gpt-image-1", cache_dir: str | Path = "/tmp/video-editor-images"):
        self.client = client
        self.model = model
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt: str, size: str, transparent_background: bool = False) -> dict[str, Any]:
        cache_key = hashlib.sha256(json.dumps({"prompt": prompt, "model": self.model, "size": size, "transparent_background": transparent_background}, sort_keys=True).encode()).hexdigest()
        target = self.cache_dir / f"{cache_key}.json"
        if target.exists():
            return json.loads(target.read_text(encoding="utf-8"))
        result = self.client.images.generate(model=self.model, prompt=prompt, size=size, background="transparent" if transparent_background else "opaque")
        item = result.data[0]
        record = {"cache_key": cache_key, "model": self.model, "size": size, "prompt": prompt, "url": getattr(item, "url", None), "cost_estimate": 0.0}
        encoded = getattr(item, "b64_json", None)
        if encoded:
            extension = "png" if transparent_background else "webp"
            asset_path = self.cache_dir / f"{cache_key}.{extension}"
            asset_path.write_bytes(base64.b64decode(encoded))
            record["asset_path"] = str(asset_path)
        target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record
