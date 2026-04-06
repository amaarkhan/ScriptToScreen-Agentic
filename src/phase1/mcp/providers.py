from __future__ import annotations

from typing import Any

from phase1.intake.script_intake import build_auto_script
from phase1.visual.image_synthesizer import generate_character_images


def groq_generate_script(prompt: str, num_scenes: int, llm_mode: str, llm_api_base: str, llm_api_key: str, llm_model: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    return build_auto_script(
        prompt,
        num_scenes,
        llm_mode=llm_mode,
        llm_config={
            "api_base": llm_api_base,
            "api_key": llm_api_key,
            "model": llm_model,
        },
    )


def comfyui_generate_images(
    characters: list[dict[str, Any]],
    output_dir: str,
    endpoint_url: str | None,
    timeout_seconds: int,
    require_comfyui: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return generate_character_images(
        characters,
        output_dir,
        endpoint_url=endpoint_url,
        timeout_seconds=timeout_seconds,
        require_comfyui=require_comfyui,
    )
