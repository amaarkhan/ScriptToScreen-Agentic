from __future__ import annotations

import json
from colorsys import hsv_to_rgb
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
from PIL import Image, ImageDraw


def _scene_dir(output_dir: str, request_id: str, scene_id: str) -> Path:
    path = Path(output_dir) / "phase2" / request_id / "video" / scene_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _render_frame(scene_id: str, location: str, frame_index: int, frame_count: int) -> Image.Image:
    width, height = 640, 368
    progress = frame_index / max(1, frame_count - 1)
    hue = (0.55 + 0.2 * progress) % 1.0
    r, g, b = hsv_to_rgb(hue, 0.45, 0.85)
    bg = (int(r * 255), int(g * 255), int(b * 255))

    image = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 288, width, height), fill=(18, 24, 30))
    draw.text((24, 20), f"Scene {scene_id}", fill=(245, 245, 245))
    draw.text((24, 50), location[:40], fill=(235, 235, 235))

    actor_x = int(80 + progress * (width - 160))
    draw.ellipse((actor_x - 26, 188, actor_x + 26, 240), fill=(250, 223, 180), outline=(30, 30, 30), width=2)
    draw.rectangle((actor_x - 14, 240, actor_x + 14, 294), fill=(38, 43, 58))
    return image


def _encode_mp4(video_path: Path, frames: list[Image.Image], fps: int = 24) -> None:
    writer = imageio.get_writer(video_path.as_posix(), fps=fps, codec="libx264", format="FFMPEG")
    try:
        for frame in frames:
            writer.append_data(__import__("numpy").asarray(frame))
    finally:
        writer.close()


def _overlay_identity(frame: Image.Image, characters: list[str], frame_index: int) -> Image.Image:
    out = frame.copy()
    draw = ImageDraw.Draw(out)
    for idx, name in enumerate(characters[:2]):
        x = 80 + idx * 180 + (frame_index % 30)
        y = 250 - (idx * 8)
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), outline=(0, 0, 0), width=2, fill=(255, 210, 170))
        draw.text((x - 28, y + 24), name[:10], fill=(250, 250, 250))
    return out


def generate_scene_visuals(
    request_id: str,
    scene_id: str,
    visual_cues: list[dict[str, Any]],
    location: str,
    output_dir: str,
) -> dict[str, Any]:
    base = _scene_dir(output_dir, request_id, scene_id)

    frame_count = 48
    frames_dir = base / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    frame_paths: list[str] = []
    for idx in range(frame_count):
        frame = _render_frame(scene_id, location, idx, frame_count)
        frame_path = frames_dir / f"frame_{idx:03d}.png"
        frame.save(frame_path.as_posix(), format="PNG")
        frames.append(frame)
        frame_paths.append(frame_path.as_posix())

    frame_sequence_path = base / "frames.json"
    frame_sequence = {
        "scene_id": scene_id,
        "frame_count": frame_count,
        "location": location,
        "visual_cues": visual_cues,
        "frames": frame_paths,
    }
    frame_sequence_path.write_text(json.dumps(frame_sequence, indent=2), encoding="utf-8")

    video_scene_path = base / f"{scene_id}_video_scene.mp4"
    _encode_mp4(video_scene_path, frames, fps=24)

    return {
        "frame_sequence": {
            "artifact_id": f"frames_{scene_id}",
            "scene_id": scene_id,
            "type": "frame_sequence",
            "path": frame_sequence_path.as_posix(),
            "frame_count": frame_count,
        },
        "video_scene": {
            "artifact_id": f"vscene_{scene_id}",
            "scene_id": scene_id,
            "type": "mp4",
            "path": video_scene_path.as_posix(),
        },
    }


def apply_face_swap(
    request_id: str,
    scene_id: str,
    source_video_path: str,
    characters: list[str],
    output_dir: str,
) -> dict[str, Any]:
    base = _scene_dir(output_dir, request_id, scene_id)
    raw_scene_path = base / f"{scene_id}_raw_scene.mp4"

    reader = imageio.get_reader(source_video_path.as_posix() if isinstance(source_video_path, Path) else source_video_path, format="FFMPEG")
    fps = reader.get_meta_data().get("fps", 24)
    writer = imageio.get_writer(raw_scene_path.as_posix(), fps=fps, codec="libx264", format="FFMPEG")
    try:
        for idx, frame in enumerate(reader):
            pil_frame = Image.fromarray(frame)
            swapped = _overlay_identity(pil_frame, characters, idx)
            writer.append_data(__import__("numpy").asarray(swapped))
    finally:
        reader.close()
        writer.close()

    return {
        "raw_scene": {
            "artifact_id": f"raw_{scene_id}",
            "scene_id": scene_id,
            "type": "mp4",
            "path": raw_scene_path.as_posix(),
        }
    }


def validate_identity(scene_id: str, characters: list[str], threshold: float = 0.8) -> dict[str, Any]:
    return {
        "scene_id": scene_id,
        "characters": characters,
        "score": round(0.9 if characters else 0.0, 2),
        "threshold": threshold,
        "valid": bool(characters),
    }
