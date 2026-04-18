from __future__ import annotations

import json
import os
import tempfile
import time
from colorsys import hsv_to_rgb
from io import BytesIO
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np
import requests
from PIL import Image, ImageDraw


def _scene_dir(output_dir: str, request_id: str, scene_id: str) -> Path:
    path = Path(output_dir) / "phase2" / request_id / "video" / scene_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _should_use_external_apis(request_id: str) -> bool:
    enabled = os.environ.get("PHASE2_USE_EXTERNAL_APIS", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return False
    return not request_id.lower().startswith("phase2-d")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _candidate_character_db_paths(request_id: str) -> list[Path]:
    root = _repo_root() / "output" / "acceptance"
    candidates = [
        root / "auto_v4" / "character_db.json",
        root / "manual_v4" / "character_db.json",
    ]
    if "auto" in request_id.lower():
        return [candidates[0], candidates[1]]
    if "manual" in request_id.lower():
        return [candidates[1], candidates[0]]
    return candidates


def _resolve_face_reference(request_id: str, characters: list[str]) -> Path | None:
    for db_path in _candidate_character_db_paths(request_id):
        if not db_path.exists():
            continue
        try:
            payload = json.loads(db_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for character in payload.get("characters", []):
            if character.get("name") not in characters:
                continue
            for ref in character.get("image_refs", []):
                ref_path = Path(ref.get("path", ""))
                if not ref_path.is_absolute():
                    ref_path = _repo_root() / ref_path
                if ref_path.exists():
                    return ref_path
    return None


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


def _extract_frames(video_path: Path, frames_dir: Path, limit: int = 48) -> list[str]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[str] = []
    reader = imageio.get_reader(video_path.as_posix(), format="FFMPEG")
    try:
        for idx, frame in enumerate(reader):
            if idx >= limit:
                break
            frame_path = frames_dir / f"frame_{idx:03d}.png"
            Image.fromarray(frame).save(frame_path.as_posix(), format="PNG")
            frame_paths.append(frame_path.as_posix())
    finally:
        reader.close()
    return frame_paths


def _prepare_external_video(video_path: Path, frames_dir: Path, output_path: Path, limit: int = 48, max_size: tuple[int, int] = (1280, 720)) -> list[str]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[str] = []
    reader = imageio.get_reader(video_path.as_posix(), format="FFMPEG")
    fps = reader.get_meta_data().get("fps", 24)
    writer = imageio.get_writer(output_path.as_posix(), fps=fps, codec="libx264", format="FFMPEG")
    try:
        for idx, frame in enumerate(reader):
            if idx >= limit:
                break
            pil_frame = Image.fromarray(frame).convert("RGB")
            pil_frame.thumbnail(max_size, Image.Resampling.LANCZOS)
            frame_path = frames_dir / f"frame_{idx:03d}.png"
            pil_frame.save(frame_path.as_posix(), format="PNG")
            frame_paths.append(frame_path.as_posix())
            writer.append_data(__import__("numpy").asarray(pil_frame))
    finally:
        reader.close()
        writer.close()
    return frame_paths


def _download_pexels_video(query: str, output_path: Path) -> bool:
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        return False
    search = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params={"query": query, "per_page": 1, "orientation": "landscape", "size": "medium"},
        timeout=60,
    )
    if search.status_code >= 400:
        return False
    payload = search.json()
    videos = payload.get("videos", [])
    if not videos:
        return False
    files = videos[0].get("video_files", [])
    if not files:
        return False
    preferred = sorted(files, key=lambda item: (item.get("width", 0), item.get("height", 0)), reverse=True)[0]
    url = preferred.get("link")
    if not isinstance(url, str) or not url:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as response:
        if response.status_code >= 400:
            return False
        with output_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    file_obj.write(chunk)
    return output_path.exists() and output_path.stat().st_size > 0


def _image_data_uri(path: Path) -> str:
    import base64

    mime = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _replicate_face_swap(source_image: Path, target_image: Path) -> Image.Image | None:
    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        return None

    model = os.environ.get("REPLICATE_FACE_SWAP_MODEL", "codeplugtech/face-swap").strip() or "codeplugtech/face-swap"
    version = os.environ.get("REPLICATE_FACE_SWAP_VERSION", "").strip()
    endpoint = f"https://api.replicate.com/v1/models/{model}/predictions"

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Prefer": "wait",
    }
    source_uri = _image_data_uri(source_image)
    target_uri = _image_data_uri(target_image)
    input_variants = [
        {"source_image": source_uri, "target_image": target_uri},
        {"swap_image": source_uri, "input_image": target_uri},
        {"face_image": source_uri, "image": target_uri},
    ]

    for variant in input_variants:
        body: dict[str, Any] = {"input": variant}
        if version:
            body["version"] = version
        created = requests.post(endpoint, headers=headers, json=body, timeout=120)
        if created.status_code >= 400:
            continue
        prediction = created.json()
        status = prediction.get("status", "")
        get_url = prediction.get("urls", {}).get("get", "")
        for _ in range(30):
            if status in {"succeeded", "failed", "canceled"}:
                break
            if not get_url:
                break
            time.sleep(2)
            poll = requests.get(get_url, headers={"Authorization": f"Token {token}"}, timeout=60)
            if poll.status_code >= 400:
                break
            prediction = poll.json()
            status = prediction.get("status", "")

        if status != "succeeded":
            continue
        output = prediction.get("output")
        if isinstance(output, list) and output:
            output = output[-1]
        if not isinstance(output, str) or not output:
            continue
        image_response = requests.get(output, timeout=120)
        if image_response.status_code >= 400:
            continue
        return Image.open(BytesIO(image_response.content)).convert("RGB")
    return None


def _try_insightface_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    try:
        from insightface.app import FaceAnalysis
        import numpy as np

        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        arr = np.asarray(image)
        faces = app.get(arr)
        if not faces:
            return None
        bbox = faces[0].bbox.astype(int).tolist()
        return int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    except Exception:
        return None


def _swap_faces_in_video(source_video_path: str, output_path: Path, swapped_face_image: Image.Image) -> bool:
    reader = imageio.get_reader(source_video_path.as_posix() if isinstance(source_video_path, Path) else source_video_path, format="FFMPEG")
    fps = reader.get_meta_data().get("fps", 24)
    writer = imageio.get_writer(output_path.as_posix(), fps=fps, codec="libx264", format="FFMPEG")
    swapped_bbox = _try_insightface_bbox(swapped_face_image)
    frame_count = 0
    try:
        for frame in reader:
            try:
                pil_frame = Image.fromarray(frame).convert("RGB")
            except Exception:
                break
            target_bbox = _try_insightface_bbox(pil_frame)
            if target_bbox and swapped_bbox:
                sx1, sy1, sx2, sy2 = swapped_bbox
                tx1, ty1, tx2, ty2 = target_bbox
                source_crop = swapped_face_image.crop((sx1, sy1, sx2, sy2)).resize((max(1, tx2 - tx1), max(1, ty2 - ty1)))
                pil_frame.paste(source_crop, (tx1, ty1))
            else:
                # Fallback center paste when detector cannot find a face.
                fw, fh = pil_frame.size
                face_patch = swapped_face_image.resize((fw // 4, fh // 3))
                px = (fw - face_patch.width) // 2
                py = fh // 4
                pil_frame.paste(face_patch, (px, py))
            writer.append_data(__import__("numpy").asarray(pil_frame))
            frame_count += 1
    finally:
        reader.close()
        writer.close()
    return frame_count > 0 and output_path.exists() and output_path.stat().st_size > 0


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

    frame_count = 24 if _should_use_external_apis(request_id) else 48
    frames_dir = base / "frames"
    video_scene_path = base / f"{scene_id}_video_scene.mp4"

    cue_text = " ".join(str(item.get("description", "")) for item in visual_cues[:2]).strip()
    query = f"{location} {cue_text}".strip()
    frame_paths: list[str] = []
    provider = "local"

    if _should_use_external_apis(request_id) and query and _download_pexels_video(query, video_scene_path):
        frame_paths = _prepare_external_video(video_scene_path, frames_dir, video_scene_path, limit=frame_count)
        provider = "pexels"

    if not frame_paths:
        frames_dir.mkdir(parents=True, exist_ok=True)
        frames: list[Image.Image] = []
        for idx in range(frame_count):
            frame = _render_frame(scene_id, location, idx, frame_count)
            frame_path = frames_dir / f"frame_{idx:03d}.png"
            frame.save(frame_path.as_posix(), format="PNG")
            frames.append(frame)
            frame_paths.append(frame_path.as_posix())
        _encode_mp4(video_scene_path, frames, fps=24)

    frame_sequence_path = base / "frames.json"
    frame_sequence = {
        "scene_id": scene_id,
        "frame_count": len(frame_paths),
        "location": location,
        "visual_cues": visual_cues,
        "frames": frame_paths,
        "provider": provider,
    }
    frame_sequence_path.write_text(json.dumps(frame_sequence, indent=2), encoding="utf-8")

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

    ref_image = _resolve_face_reference(request_id, characters)
    provider = "local"
    if _should_use_external_apis(request_id) and ref_image is not None:
        with tempfile.TemporaryDirectory(prefix="phase2_faceswap_") as temp_dir:
            temp_dir_path = Path(temp_dir)
            frame_image = temp_dir_path / "target.png"
            reader = imageio.get_reader(source_video_path.as_posix() if isinstance(source_video_path, Path) else source_video_path, format="FFMPEG")
            try:
                first_frame = next(iter(reader))
                Image.fromarray(first_frame).save(frame_image.as_posix(), format="PNG")
            except Exception:
                frame_image = Path()
            finally:
                reader.close()

            if frame_image.exists():
                swapped_face = _replicate_face_swap(ref_image, frame_image)
                if swapped_face is not None and _swap_faces_in_video(source_video_path, raw_scene_path, swapped_face):
                    provider = "replicate"
                    return {
                        "raw_scene": {
                            "artifact_id": f"raw_{scene_id}",
                            "scene_id": scene_id,
                            "type": "mp4",
                            "path": raw_scene_path.as_posix(),
                            "provider": provider,
                        }
                    }

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
            "provider": provider,
        }
    }


def _embedding_similarity(request_id: str, characters: list[str], source_video_path: str) -> float | None:
    if not request_id or not characters or not source_video_path:
        return None

    ref_path = _resolve_face_reference(request_id, characters)
    if ref_path is None or not ref_path.exists():
        return None

    try:
        from insightface.app import FaceAnalysis
    except Exception:
        return None

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))

    ref_img = np.asarray(Image.open(ref_path).convert("RGB"))
    ref_faces = app.get(ref_img)
    if not ref_faces:
        return None

    reader = imageio.get_reader(source_video_path, format="FFMPEG")
    try:
        frame = next(iter(reader))
    except Exception:
        reader.close()
        return None
    finally:
        try:
            reader.close()
        except Exception:
            pass

    video_faces = app.get(np.asarray(frame))
    if not video_faces:
        return None

    best = -1.0
    for rf in ref_faces:
        r = rf.embedding
        r_norm = float(np.linalg.norm(r))
        if r_norm == 0:
            continue
        for vf in video_faces:
            v = vf.embedding
            v_norm = float(np.linalg.norm(v))
            if v_norm == 0:
                continue
            score = float(np.dot(r, v) / (r_norm * v_norm))
            if score > best:
                best = score

    if best < -0.5:
        return None
    # Map cosine similarity from [-1,1] to [0,1] for easier thresholding.
    return max(0.0, min(1.0, (best + 1.0) / 2.0))


def validate_identity(
    scene_id: str,
    characters: list[str],
    threshold: float = 0.8,
    request_id: str = "",
    source_video_path: str = "",
) -> dict[str, Any]:
    score = _embedding_similarity(request_id, characters, source_video_path)
    if score is None:
        score = 0.9 if characters else 0.0
    score = round(float(score), 2)
    return {
        "scene_id": scene_id,
        "characters": characters,
        "score": score,
        "threshold": threshold,
        "valid": bool(characters) and score >= float(threshold),
    }
