from __future__ import annotations

import hashlib
from typing import Any

from phase1.intake import normalize_manual_script
from phase1.memory import commit_memory_bundle
from .providers import comfyui_generate_images, groq_generate_script


def tool_generate_script_segment(payload: dict[str, Any]) -> dict[str, Any]:
    normalized, errors = groq_generate_script(
        prompt=payload["prompt"],
        num_scenes=int(payload["num_scenes"]),
        llm_mode=str(payload.get("llm_mode", "required")),
        llm_api_base=str(payload.get("llm_api_base", "")),
        llm_api_key=str(payload.get("llm_api_key", "")),
        llm_model=str(payload.get("llm_model", "")),
    )
    return {"script": normalized, "errors": errors}


def tool_validate_script(payload: dict[str, Any]) -> dict[str, Any]:
    normalized, errors = normalize_manual_script(payload["script_text"])
    return {"script": normalized, "errors": errors}


def tool_generate_character_image(payload: dict[str, Any]) -> dict[str, Any]:
    images, errors = comfyui_generate_images(
        characters=payload["characters"],
        output_dir=payload["output_dir"],
        endpoint_url=payload.get("endpoint_url"),
        timeout_seconds=int(payload.get("timeout_seconds", 900)),
        require_comfyui=bool(int(payload.get("require_comfyui", 0))),
    )
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
