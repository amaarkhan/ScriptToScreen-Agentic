from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase2.memory import commit_memory
from phase2.mcp import Phase2MCPRuntime
from phase2.state import Phase2State


def _runtime(state: Phase2State) -> Phase2MCPRuntime:
    config_path = state.get("test_flags", {}).get("mcp_config_path", "config/phase2_mcp_tools.json")
    return Phase2MCPRuntime(config_path)


def lip_sync_node(state: Phase2State) -> Phase2State:
    runtime = _runtime(state)
    branches = state.get("branch_history", [])
    scene_task = state.get("scene_task", {})
    scene_id = scene_task.get("scene_id", "")
    if state.get("scene_status", "queued") == "resumed":
        return {
            "node_history": ["lip_sync_node"],
            "branch_history": branches,
            "tool_calls": [],
            "sync_jobs": [],
            "sync_artifacts": [],
        }

    audio_by_scene: dict[str, str] = {}
    for item in state.get("audio_artifacts", []):
        sid = item.get("scene_id", "")
        if sid and sid not in audio_by_scene:
            audio_by_scene[sid] = item.get("path", "")

    raw_by_scene: dict[str, str] = {}
    for item in state.get("raw_scene_artifacts", []):
        sid = item.get("scene_id", "")
        if sid:
            raw_by_scene[sid] = item.get("path", "")

    sync_jobs: list[dict[str, Any]] = []
    sync_artifacts: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []

    order_map = {item.get("scene_id"): item.get("order") for item in state.get("scene_results", [])}
    existing_sync_ids = {item.get("scene_id") for item in state.get("sync_artifacts", [])}
    candidate_ids = [scene_id] if scene_id else [item.get("scene_id", "") for item in state.get("scene_results", [])]

    for candidate_scene_id in candidate_ids:
        if not candidate_scene_id or candidate_scene_id in existing_sync_ids:
            continue

        audio_path = audio_by_scene.get(candidate_scene_id, "")
        raw_path = raw_by_scene.get(candidate_scene_id, "")
        if not audio_path or not raw_path:
            continue

        payload = {
            "request_id": state["request_id"],
            "scene_id": candidate_scene_id,
            "audio_path": audio_path,
            "video_path": raw_path,
            "output_dir": state.get("test_flags", {}).get("output_dir", "output/phase2"),
            "scene_order": int(order_map.get(candidate_scene_id, 0)) if order_map.get(candidate_scene_id) is not None else None,
        }
        result = runtime.invoke_capability("lip_sync", payload)
        tool_calls.append(
            {
                "tool": result.get("tool", "lip_sync_aligner"),
                "status": "success" if result.get("ok") else "failure",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if not result.get("ok"):
            err = result.get("error", {})
            return {
                "node_history": ["lip_sync_node"],
                "branch_history": branches,
                "tool_calls": tool_calls,
                "errors": [
                    {
                        "code": err.get("code", "LIP_SYNC_FAILED"),
                        "message": err.get("message", "Lip sync failed."),
                    }
                ],
            }

        artifact = result["result"]["synced_scene"]
        sync_artifacts.append(artifact)
        sync_jobs.append(
            {
                "task_id": f"{candidate_scene_id}_L1",
                "scene_id": candidate_scene_id,
                "status": "completed",
                "artifact_id": artifact["artifact_id"],
            }
        )

    existing_artifacts = state.get("artifacts", {})
    memory_refs = state.get("memory_refs", {})
    commit_memory(
        request_id=state["request_id"],
        output_dir=state.get("test_flags", {}).get("output_dir", "output/phase2"),
        state_snapshot={
            "request_id": state["request_id"],
            "task_graph": state.get("task_graph", {}),
            "tasks": state.get("tasks", []),
            "artifacts": {
                "audio_tracks": existing_artifacts.get("audio_tracks", []),
                "frame_sequences": existing_artifacts.get("frame_sequences", []),
                "video_scenes": existing_artifacts.get("video_scenes", []),
                "raw_scenes": existing_artifacts.get("raw_scenes", []) + sync_artifacts,
                "task_graph_logs": existing_artifacts.get("task_graph_logs", []),
            },
            "memory_refs": {
                "task_graph_ids": memory_refs.get("task_graph_ids", []),
                "audio_memory_ids": memory_refs.get("audio_memory_ids", []),
                "video_memory_ids": memory_refs.get("video_memory_ids", []),
                "sync_memory_ids": memory_refs.get("sync_memory_ids", []) + [artifact["artifact_id"] for artifact in sync_artifacts],
            },
            "completed_scene_ids": [item.get("scene_id") for item in state.get("scene_results", []) if item.get("scene_id")],
        },
    )

    updated_sync_refs = {
        "task_graph_ids": memory_refs.get("task_graph_ids", []),
        "audio_memory_ids": memory_refs.get("audio_memory_ids", []),
        "video_memory_ids": memory_refs.get("video_memory_ids", []),
        "sync_memory_ids": memory_refs.get("sync_memory_ids", []) + [artifact["artifact_id"] for artifact in sync_artifacts],
    }

    return {
        "node_history": ["lip_sync_node"],
        "branch_history": branches,
        "tool_calls": tool_calls,
        "sync_jobs": sync_jobs,
        "sync_artifacts": sync_artifacts,
    }
