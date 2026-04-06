from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_character_db(request_id: str, characters: list[dict[str, Any]], output_root: str) -> str:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "character_db.json"

    payload = {
        "schema_version": "1.0.0",
        "request_id": request_id,
        "characters": characters,
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path.as_posix()


def write_scene_manifest(request_id: str, input_mode: str, script: dict[str, Any], output_root: str) -> str:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "scene_manifest.json"

    payload = {
        "schema_version": "1.0.0",
        "request_id": request_id,
        "input_mode": input_mode,
        "title": script.get("title", ""),
        "logline": script.get("logline", ""),
        "theme": script.get("theme", ""),
        "scenes": script.get("scenes", []),
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path.as_posix()
