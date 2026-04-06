from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any


def _duration_seconds(path: Path) -> float:
    with wave.open(path.as_posix(), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return 0.0 if rate == 0 else frames / float(rate)


def _windows_tts(text: str, path: Path, rate: int = 0) -> bool:
    tts_shell = shutil.which("powershell")
    if not tts_shell:
        return False
    escaped_text = text.replace("'", "''")
    escaped_path = path.as_posix().replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$synth.Rate = {rate}; "
        f"$synth.SetOutputToWaveFile('{escaped_path}'); "
        f"$synth.Speak('{escaped_text}'); "
        "$synth.Dispose();"
    )
    result = subprocess.run(
        [tts_shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and path.exists() and path.stat().st_size > 0


def synthesize_voice_for_dialogue(
    request_id: str,
    scene_id: str,
    speaker: str,
    dialogue: str,
    emotion: str,
    output_dir: str,
) -> dict[str, Any]:
    base = Path(output_dir) / "phase2" / request_id / "audio"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{scene_id}_{speaker.replace(' ', '_').replace('.', '').replace('-', '_')}.wav"
    spoken_text = f"{speaker}. {dialogue}"
    emotion_rate = {"calm": -1, "neutral": 0, "tense": 1, "angry": 2, "sad": -2}
    rate = emotion_rate.get(emotion.lower(), 0)
    if not _windows_tts(spoken_text, path, rate=rate):
        raise RuntimeError("VOICE_SYNTH_FAILED: No local TTS engine could synthesize speech.")

    duration_seconds = round(_duration_seconds(path), 2)

    return {
        "artifact_id": f"wav_{scene_id}_{speaker.replace(' ', '_')}",
        "path": path.as_posix(),
        "scene_id": scene_id,
        "speaker": speaker,
        "type": "wav",
        "duration_seconds": round(duration_seconds, 2),
        "emotion": emotion,
    }
