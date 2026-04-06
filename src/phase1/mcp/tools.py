from __future__ import annotations

import hashlib
from typing import Any

from phase1.intake import build_auto_script, normalize_manual_script
from phase1.memory import commit_memory_bundle
from phase1.visual import generate_character_images


def tool_generate_script_segment(payload: dict[str, Any]) -> dict[str, Any]:
    normalized, errors = build_auto_script(payload["prompt"], int(payload["num_scenes"]))
    return {"script": normalized, "errors": errors}


def tool_validate_script(payload: dict[str, Any]) -> dict[str, Any]:
    normalized, errors = normalize_manual_script(payload["script_text"])
    return {"script": normalized, "errors": errors}


def tool_generate_character_image(payload: dict[str, Any]) -> dict[str, Any]:
    images, errors = generate_character_images(payload["characters"], payload["output_dir"])
    return {"images": images, "errors": errors}


def tool_query_stock_footage(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload["prompt"]
    references = []
    for index, character in enumerate(payload["characters"], start=1):
        name = str(character.get("name", f"Character {index}"))
        seed = hashlib.sha256(f"{name}|{prompt}".encode("utf-8")).hexdigest()[:12]
        references.append(
            {
                "character_name": name,
                "reference_id": f"stock_{seed}",
                "source": "local_stock_catalog",
                "style_hint": character.get("reference_style", "cinematic realistic"),
            }
        )
    return {"references": references, "errors": []}


def tool_commit_memory(payload: dict[str, Any]) -> dict[str, Any]:
    memory_refs = commit_memory_bundle(
        request_id=payload["request_id"],
        script=payload["script"],
        characters=payload["characters"],
        images=payload["images"],
        memory_dir=payload["memory_dir"],
    )
    return {"memory_refs": memory_refs, "errors": []}


TOOL_HANDLERS = {
    "generate_script_segment": tool_generate_script_segment,
    "validate_script": tool_validate_script,
    "generate_character_image": tool_generate_character_image,
    "query_stock_footage": tool_query_stock_footage,
    "commit_memory": tool_commit_memory,
}
