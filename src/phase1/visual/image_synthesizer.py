from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from phase1.mcp.external_providers import comfyui_generate_image


def _palette_for_name(name: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    h = hashlib.sha256(name.encode("utf-8")).hexdigest()
    a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    b = int(h[6:8], 16), int(h[8:10], 16), int(h[10:12], 16)
    return a, b


def _render_reference_image(path: Path, name: str, style: str) -> None:
    c1, c2 = _palette_for_name(name + style)
    img = Image.new("RGB", (768, 768), c1)
    draw = ImageDraw.Draw(img)

    for i in range(0, 768, 6):
        blend = i / 768
        color = (
            int(c1[0] * (1 - blend) + c2[0] * blend),
            int(c1[1] * (1 - blend) + c2[1] * blend),
            int(c1[2] * (1 - blend) + c2[2] * blend),
        )
        draw.rectangle((0, i, 768, i + 6), fill=color)

    draw.ellipse((160, 110, 610, 560), outline=(245, 245, 245), width=6)
    draw.rectangle((250, 560, 520, 720), outline=(245, 245, 245), width=6)
    draw.text((32, 32), f"Character: {name}", fill=(250, 250, 250))
    draw.text((32, 70), f"Style: {style}", fill=(240, 240, 240))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def generate_character_images(
    characters: list[dict[str, Any]],
    output_dir: str,
    endpoint_url: str | None = None,
    timeout_seconds: int = 900,
    require_comfyui: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not characters:
        return [], [{"code": "IMG_NO_CHARACTERS", "message": "No characters available for image synthesis."}]

    legacy_base = os.environ.get("COMFYUI_URL", "").strip().rstrip("/")
    legacy_endpoint = f"{legacy_base}/generate" if legacy_base else ""
    resolved_endpoint = (endpoint_url or os.environ.get("COMFYUI_GENERATE_URL", "") or legacy_endpoint).strip()
    if not resolved_endpoint:
        if not require_comfyui:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            images: list[dict[str, Any]] = []
            for profile in characters:
                character_id = str(profile["character_id"])
                name = str(profile["name"])
                style = str(profile.get("reference_style", "cinematic realistic"))
                prompt_material = f"{name}|{style}|{profile.get('appearance', {})}"
                prompt_hash = hashlib.sha256(prompt_material.encode("utf-8")).hexdigest()
                asset_id = f"ASSET_{prompt_hash[:10]}"
                path = out / f"{character_id.lower()}_ref.png"
                _render_reference_image(path, name, style)
                ref = {
                    "asset_id": asset_id,
                    "character_id": character_id,
                    "path": path.as_posix(),
                    "prompt_hash": prompt_hash,
                }
                images.append(ref)
                profile["image_refs"].append(ref)
            return images, []

        return [], [
            {
                "code": "IMG_COMFYUI_ENDPOINT_REQUIRED",
                "message": "COMFYUI_GENERATE_URL (or COMFYUI_URL) is not set. Phase 1 image generation requires an MCP-configured ComfyUI generate endpoint.",
            }
        ]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for profile in characters:
        character_id = str(profile["character_id"])
        name = str(profile["name"])
        style = str(profile.get("reference_style", "cinematic realistic"))
        prompt_material = f"{name}|{style}|{profile.get('appearance', {})}"
        prompt_hash = hashlib.sha256(prompt_material.encode("utf-8")).hexdigest()
        asset_id = f"ASSET_{prompt_hash[:10]}"
        path = out / f"{character_id.lower()}_ref.png"

        generated = comfyui_generate_image(
            prompt=f"Character reference for {name}",
            output_path=path.as_posix(),
            style=style,
            metadata={"appearance": profile.get("appearance", {}), "prompt_hash": prompt_hash},
            endpoint_url=resolved_endpoint,
            timeout_seconds=timeout_seconds,
        )
        if not generated:
            if not require_comfyui:
                _render_reference_image(path, name, style)
                ref = {
                    "asset_id": asset_id,
                    "character_id": character_id,
                    "path": path.as_posix(),
                    "prompt_hash": prompt_hash,
                }
                images.append(ref)
                profile["image_refs"].append(ref)
                continue

            errors.append(
                {
                    "code": "IMG_COMFYUI_GENERATION_FAILED",
                    "message": f"ComfyUI failed to generate image for character '{name}'.",
                    "details": {"character_id": character_id, "output_path": path.as_posix()},
                }
            )
            continue

        ref = {
            "asset_id": asset_id,
            "character_id": character_id,
            "path": path.as_posix(),
            "prompt_hash": prompt_hash,
        }
        images.append(ref)
        profile["image_refs"].append(
            {
                "asset_id": asset_id,
                "path": path.as_posix(),
                "prompt_hash": prompt_hash,
            }
        )

    if errors:
        return images, errors
    return images, []
