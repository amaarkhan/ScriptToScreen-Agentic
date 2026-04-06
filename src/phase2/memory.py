from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _checkpoint_path(output_dir: str, request_id: str) -> Path:
    run_dir = Path(output_dir) / "phase2" / request_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "checkpoint.json"


def load_checkpoint(output_dir: str, request_id: str) -> dict[str, Any]:
    path = _checkpoint_path(output_dir, request_id)
    if not path.exists():
        return {"completed_scene_ids": [], "task_graph_ids": [], "artifacts": []}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {"completed_scene_ids": [], "task_graph_ids": [], "artifacts": []}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"completed_scene_ids": [], "task_graph_ids": [], "artifacts": []}


def commit_memory(
    request_id: str,
    output_dir: str,
    state_snapshot: dict[str, Any],
) -> dict[str, Any]:
    checkpoint = load_checkpoint(output_dir, request_id)
    completed_scene_ids = state_snapshot.get("completed_scene_ids") or checkpoint.get("completed_scene_ids", [])
    task_graph_ids = state_snapshot.get("memory_refs", {}).get("task_graph_ids", [])

    payload = {
        "request_id": request_id,
        "completed_scene_ids": completed_scene_ids,
        "task_graph_ids": task_graph_ids,
        "state_snapshot": state_snapshot,
    }
    path = _checkpoint_path(output_dir, request_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "checkpoint_path": path.as_posix(),
        "memory_refs": {
            "task_graph_ids": task_graph_ids,
            "audio_memory_ids": state_snapshot.get("memory_refs", {}).get("audio_memory_ids", []),
            "video_memory_ids": state_snapshot.get("memory_refs", {}).get("video_memory_ids", []),
            "sync_memory_ids": state_snapshot.get("memory_refs", {}).get("sync_memory_ids", []),
        },
        "completed_scene_ids": completed_scene_ids,
    }
