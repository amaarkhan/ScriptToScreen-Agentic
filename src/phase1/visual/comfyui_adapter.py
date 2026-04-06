from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests


def try_generate_via_comfyui(prompt: str, output_path: str, style: str, metadata: dict[str, Any]) -> bool:
    base_url = os.environ.get("COMFYUI_URL")
    if not base_url:
        return False

    workflow = {
        "prompt": prompt,
        "style": style,
        "metadata": metadata,
        "output_path": output_path,
    }

    try:
        # CPU generation can take several minutes per image.
        response = requests.post(f"{base_url.rstrip('/')}/generate", json=workflow, timeout=900)
        response.raise_for_status()
        data = response.json()
        image_b64 = data.get("image_base64")
        if not image_b64:
            return False
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(base64.b64decode(image_b64))
        return True
    except Exception:
        return False
