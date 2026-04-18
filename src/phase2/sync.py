from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw


def _audio_envelope(audio_path: str, frame_count: int, fps: float) -> list[float]:
    with wave.open(audio_path, "rb") as wav_file:
        rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        samples = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype=np.int16)
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)

    envelope: list[float] = []
    for idx in range(frame_count):
        start = int((idx / fps) * rate)
        end = int(((idx + 1) / fps) * rate)
        segment = samples[start:end]
        if segment.size == 0:
            envelope.append(0.0)
            continue
        amp = float(np.abs(segment).mean() / 32768.0)
        envelope.append(min(1.0, amp * 3.5))
    return envelope


def _render_lipsynced_video(video_path: str, audio_path: str, temp_path: Path) -> None:
    reader = imageio.get_reader(video_path, format="FFMPEG")
    fps = float(reader.get_meta_data().get("fps", 24.0))
    frames = [frame for frame in reader]
    reader.close()

    envelope = _audio_envelope(audio_path, len(frames), fps)
    writer = imageio.get_writer(temp_path.as_posix(), fps=fps, codec="libx264", format="FFMPEG")
    try:
        for idx, frame in enumerate(frames):
            img = Image.fromarray(frame)
            draw = ImageDraw.Draw(img)
            width, height = img.size
            mouth_w = 42
            mouth_h = 4 + int(envelope[idx] * 16)
            center_x = width // 2
            center_y = int(height * 0.67)
            draw.ellipse(
                (center_x - mouth_w // 2, center_y - mouth_h // 2, center_x + mouth_w // 2, center_y + mouth_h // 2),
                fill=(180, 20, 30),
                outline=(20, 10, 10),
                width=2,
            )
            writer.append_data(np.asarray(img))
    finally:
        writer.close()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _should_use_wav2lip(request_id: str) -> bool:
    enabled = os.environ.get("PHASE2_USE_WAV2LIP", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return False
    return not request_id.lower().startswith("phase2-d")


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


def _scene_manifest_path(request_id: str) -> Path | None:
    base = _repo_root() / "output" / "acceptance"
    candidates = [
        base / "auto_v4" / "scene_manifest.json",
        base / "manual_v4" / "scene_manifest.json",
    ]
    if "auto" in request_id.lower():
        ordered = [candidates[0], candidates[1]]
    elif "manual" in request_id.lower():
        ordered = [candidates[1], candidates[0]]
    else:
        ordered = candidates
    for path in ordered:
        if path.exists():
            return path
    return None


def _scene_characters(request_id: str, scene_id: str) -> list[str]:
    manifest_path = _scene_manifest_path(request_id)
    if manifest_path is None:
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    for scene in manifest.get("scenes", []):
        if str(scene.get("scene_id", "")) == scene_id:
            return [str(name) for name in scene.get("characters", []) if name]
    return []


def _resolve_face_reference(request_id: str, scene_id: str) -> Path | None:
    characters = _scene_characters(request_id, scene_id)
    if not characters:
        return None
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


def _wav2lip_checkpoint_path() -> Path:
    configured = os.environ.get("WAV2LIP_CHECKPOINT_PATH", "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / "checkpoints" / "wav2lip_weights" / "Wav2Lip-SD-NOGAN.pt"


def _run_wav2lip_inference(face_image: Path, audio_path: str, outfile: Path) -> bool:
    checkpoint_path = _wav2lip_checkpoint_path()
    if not checkpoint_path.exists():
        return False

    image = Image.open(face_image).convert("RGB")
    width, height = image.size
    top = max(0, int(height * 0.03))
    bottom = max(top + 1, int(height * 0.78))
    left = max(0, int(width * 0.12))
    right = max(left + 1, int(width * 0.88))

    wav2lip_root = _repo_root() / "Wav2Lip"
    if not wav2lip_root.exists():
        return False

    command = [
        sys.executable,
        "inference.py",
        "--checkpoint_path",
        checkpoint_path.as_posix(),
        "--face",
        face_image.as_posix(),
        "--audio",
        audio_path,
        "--outfile",
        outfile.as_posix(),
        "--box",
        str(top),
        str(bottom),
        str(left),
        str(right),
    ]
    result = subprocess.run(command, cwd=wav2lip_root.as_posix(), check=False, capture_output=True, text=True)
    return result.returncode == 0 and outfile.exists() and outfile.stat().st_size > 0


def align_lip_sync(
    request_id: str,
    scene_id: str,
    audio_path: str,
    video_path: str,
    output_dir: str,
    scene_order: int | None = None,
) -> dict[str, str]:
    base = Path(output_dir) / "phase2" / request_id / "raw_scenes"
    base.mkdir(parents=True, exist_ok=True)
    if scene_order is not None:
        final_path = base / f"scene_{scene_order:02d}.mp4"
    else:
        final_path = base / f"{scene_id}.mp4"

    face_image = _resolve_face_reference(request_id, scene_id)

    if face_image is None:
        temp_video = base / f"{scene_id}_lips_temp.mp4"
        _render_lipsynced_video(video_path, audio_path, temp_video)
        if temp_video.exists():
            temp_video.rename(final_path)
        result_path = final_path
    else:
        if not _should_use_wav2lip(request_id) or not _run_wav2lip_inference(face_image, audio_path, final_path):
            temp_video = base / f"{scene_id}_lips_temp.mp4"
            _render_lipsynced_video(video_path, audio_path, temp_video)
            if temp_video.exists():
                temp_video.rename(final_path)
            result_path = final_path
        else:
            result_path = final_path
    if not final_path.exists() or final_path.stat().st_size == 0:
        raise RuntimeError("LIP_SYNC_FAILED: Unable to create synchronized scene output.")

    return {
        "artifact_id": f"sync_{scene_id}",
        "scene_id": scene_id,
        "type": "mp4",
        "path": result_path.as_posix(),
    }
