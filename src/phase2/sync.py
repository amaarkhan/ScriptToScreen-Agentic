from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
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

    temp_video = base / f"{scene_id}_lips_temp.mp4"
    _render_lipsynced_video(video_path, audio_path, temp_video)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        temp_video.as_posix(),
        "-i",
        audio_path,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        final_path.as_posix(),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        fallback = [
            ffmpeg_exe,
            "-y",
            "-i",
            temp_video.as_posix(),
            "-i",
            audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            final_path.as_posix(),
        ]
        retry = subprocess.run(fallback, check=False, capture_output=True, text=True)
        if retry.returncode != 0:
            raise RuntimeError(f"LIP_SYNC_FAILED: {retry.stderr.strip()[:400]}")
    if temp_video.exists():
        temp_video.unlink()

    return {
        "artifact_id": f"sync_{scene_id}",
        "scene_id": scene_id,
        "type": "mp4",
        "path": final_path.as_posix(),
    }
