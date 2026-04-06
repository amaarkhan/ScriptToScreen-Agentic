from __future__ import annotations

from typing import Any

from phase1.mcp.external_providers import comfyui_generate_image


def try_generate_via_comfyui(
    prompt: str,
    output_path: str,
    style: str,
    metadata: dict[str, Any],
    endpoint_url: str | None,
    timeout_seconds: int = 900,
) -> bool:
    endpoint = (endpoint_url or "").strip()
    if not endpoint:
        return False

    return comfyui_generate_image(
        prompt=prompt,
        output_path=output_path,
        style=style,
        metadata=metadata,
        endpoint_url=endpoint,
        timeout_seconds=timeout_seconds,
    )
