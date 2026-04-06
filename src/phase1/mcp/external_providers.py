from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import requests


def groq_chat_completion(prompt: str, num_scenes: int, api_base: str, api_key: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a screenplay generation engine. Return ONLY valid JSON with keys: "
                    "title, logline, theme, scenes. Each scene must include location, time_of_day, actions, dialogue, visual_cues."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt": prompt,
                        "num_scenes": max(2, int(num_scenes)),
                        "constraints": {
                            "dialogue_items_per_scene": 2,
                            "include_visual_cues": True,
                            "json_only": True,
                        },
                    }
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(api_base.rstrip("/") + "/chat/completions", headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def comfyui_generate_image(
    prompt: str,
    output_path: str,
    style: str,
    metadata: dict[str, Any],
    endpoint_url: str,
    timeout_seconds: int = 900,
) -> bool:
    workflow = {
        "prompt": prompt,
        "style": style,
        "metadata": metadata,
        "output_path": output_path,
    }

    response = requests.post(endpoint_url, json=workflow, timeout=max(30, int(timeout_seconds)))
    response.raise_for_status()
    data = response.json()
    image_b64 = data.get("image_base64")
    if not image_b64:
        return False
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(base64.b64decode(image_b64))
    return True