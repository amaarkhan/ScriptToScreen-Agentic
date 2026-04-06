from __future__ import annotations

from pathlib import Path
from typing import Any


def _speaker_name(scene: dict[str, Any], default_index: int) -> str:
    dialogue = scene.get("dialogue", [])
    if dialogue:
        return str(dialogue[0].get("speaker", f"Speaker_{default_index}"))
    return f"Speaker_{default_index}"


def build_scene_task_graph(scene_manifest: dict[str, Any]) -> dict[str, Any]:
    scenes = scene_manifest.get("scenes", [])
    scene_tasks: list[dict[str, Any]] = []
    flattened_tasks: list[dict[str, Any]] = []

    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id", f"S{index}"))
        order = int(scene.get("order", index))
        speaker = _speaker_name(scene, index)

        audio_task = {
            "task_id": f"{scene_id}_A1",
            "type": "voice_synthesis",
            "status": "queued",
            "tool": "voice_cloning_synthesizer",
            "depends_on": [],
            "scene_id": scene_id,
            "speaker": speaker,
        }
        video_task = {
            "task_id": f"{scene_id}_V1",
            "type": "video_generation",
            "status": "queued",
            "tool": "query_stock_footage",
            "depends_on": [],
            "scene_id": scene_id,
        }
        face_swap_task = {
            "task_id": f"{scene_id}_F1",
            "type": "face_swap",
            "status": "queued",
            "tool": "face_swapper",
            "depends_on": [video_task["task_id"]],
            "scene_id": scene_id,
        }
        sync_task = {
            "task_id": f"{scene_id}_L1",
            "type": "lip_sync",
            "status": "queued",
            "tool": "lip_sync_aligner",
            "depends_on": [audio_task["task_id"], face_swap_task["task_id"]],
            "scene_id": scene_id,
        }

        scene_task = {
            "scene_id": scene_id,
            "order": order,
            "audio_tasks": [audio_task],
            "video_tasks": [video_task, face_swap_task],
            "sync_tasks": [sync_task],
        }
        scene_tasks.append(scene_task)
        flattened_tasks.extend([audio_task, video_task, face_swap_task, sync_task])

    task_graph = {
        "schema_version": "1.0.0",
        "request_id": scene_manifest.get("request_id", ""),
        "scene_tasks": scene_tasks,
    }
    return {"task_graph": task_graph, "tasks": flattened_tasks}


def write_task_graph_log(task_graph: dict[str, Any], output_dir: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_path = path / "task_graph.json"
    log_path.write_text(__import__("json").dumps(task_graph, indent=2), encoding="utf-8")
    return log_path
