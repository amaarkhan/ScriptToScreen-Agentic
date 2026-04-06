from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase2.memory import commit_memory
from phase2.mcp import Phase2MCPRuntime
from phase2.state import Phase2State


def _runtime(state: Phase2State) -> Phase2MCPRuntime:
    config_path = state.get("test_flags", {}).get("mcp_config_path", "config/phase2_mcp_tools.json")
    return Phase2MCPRuntime(config_path)


def video_gen_node(state: Phase2State) -> Phase2State:
    runtime = _runtime(state)
    output_dir = state.get("test_flags", {}).get("output_dir", "output/phase2")
    frame_sequences: list[dict[str, Any]] = []
    video_scenes: list[dict[str, Any]] = []
    video_jobs: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    branches = state.get("branch_history", [])
    scene_task = state.get("scene_task", {})
    scene_id = scene_task.get("scene_id", "unknown")
    if state.get("scene_status", "queued") == "resumed":
        return {
            "node_history": ["video_gen_node"],
            "branch_history": branches,
            "tool_calls": [],
            "video_jobs": [],
            "frame_artifacts": [],
            "video_scene_artifacts": [],
        }

    scene = state.get("source_scene", {})
    payload = {
        "request_id": state["request_id"],
        "scene_id": scene_id,
        "location": scene.get("location", "Unknown"),
        "visual_cues": scene.get("visual_cues", []),
        "output_dir": output_dir,
    }
    result = runtime.invoke_capability("video_generation", payload)
    tool_calls.append(
        {
            "tool": result.get("tool", "query_stock_footage"),
            "status": "success" if result.get("ok") else "failure",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    if not result.get("ok"):
        err = result.get("error", {})
        return {
            "node_history": ["video_gen_node"],
            "branch_history": branches,
            "tool_calls": tool_calls,
            "errors": [
                {
                    "code": err.get("code", "VIDEO_GEN_FAILED"),
                    "message": err.get("message", "Video generation failed."),
                }
            ],
        }

    frame_sequence = result["result"]["frame_sequence"]
    video_scene = result["result"]["video_scene"]
    frame_sequences.append(frame_sequence)
    video_scenes.append(video_scene)
    video_jobs.append(
        {
            "task_id": f"{scene_id}_V1",
            "scene_id": scene_id,
            "status": "completed",
            "frame_artifact_id": frame_sequence["artifact_id"],
            "video_artifact_id": video_scene["artifact_id"],
        }
    )

    existing_artifacts = state.get("artifacts", {})
    memory_refs = state.get("memory_refs", {})
    commit_memory(
        request_id=state["request_id"],
        output_dir=output_dir,
        state_snapshot={
            "request_id": state["request_id"],
            "task_graph": state.get("task_graph", {}),
            "tasks": state.get("tasks", []),
            "artifacts": {
                "audio_tracks": existing_artifacts.get("audio_tracks", []),
                "frame_sequences": existing_artifacts.get("frame_sequences", []) + frame_sequences,
                "video_scenes": existing_artifacts.get("video_scenes", []) + video_scenes,
                "raw_scenes": existing_artifacts.get("raw_scenes", []),
                "task_graph_logs": existing_artifacts.get("task_graph_logs", []),
            },
            "memory_refs": {
                "task_graph_ids": memory_refs.get("task_graph_ids", []),
                "audio_memory_ids": memory_refs.get("audio_memory_ids", []),
                "video_memory_ids": memory_refs.get("video_memory_ids", []),
                "sync_memory_ids": memory_refs.get("sync_memory_ids", []),
            },
            "completed_scene_ids": [item.get("scene_id") for item in state.get("scene_results", []) if item.get("scene_id")],
        },
    )

    updated_video_refs = {
        "task_graph_ids": memory_refs.get("task_graph_ids", []),
        "audio_memory_ids": memory_refs.get("audio_memory_ids", []),
        "video_memory_ids": memory_refs.get("video_memory_ids", []),
        "sync_memory_ids": memory_refs.get("sync_memory_ids", []),
    }

    return {
        "node_history": ["video_gen_node"],
        "branch_history": branches,
        "tool_calls": tool_calls,
        "video_jobs": video_jobs,
        "frame_artifacts": frame_sequences,
        "video_scene_artifacts": video_scenes,
    }


def face_swap_node(state: Phase2State) -> Phase2State:
    runtime = _runtime(state)
    output_dir = state.get("test_flags", {}).get("output_dir", "output/phase2")
    branches = state.get("branch_history", [])

    raw_scenes: list[dict[str, Any]] = []
    face_swap_jobs: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []

    scene_task = state.get("scene_task", {})
    scene_id = scene_task.get("scene_id", "")
    if state.get("scene_status", "queued") == "resumed":
        return {
            "node_history": ["face_swap_node"],
            "branch_history": branches,
            "tool_calls": [],
            "face_swap_jobs": [],
            "raw_scene_artifacts": [],
        }

    scene_map = {scene.get("scene_id", ""): scene for scene in state.get("scenes", [])}
    processed_raw_ids = {item.get("scene_id") for item in state.get("raw_scene_artifacts", [])}
    target_scene_ids = [scene_id] if scene_id else [item.get("scene_id", "") for item in state.get("video_scene_artifacts", [])]

    for target_scene_id in target_scene_ids:
        if not target_scene_id or target_scene_id in processed_raw_ids:
            continue
        video_scene = None
        for item in state.get("video_scene_artifacts", []):
            if item.get("scene_id") == target_scene_id:
                video_scene = item
                break
        if video_scene is None:
            continue

        scene = scene_map.get(target_scene_id, {})
        swap_result = runtime.invoke_capability(
            "face_swap",
            {
                "request_id": state["request_id"],
                "scene_id": target_scene_id,
                "source_video_path": video_scene.get("path", ""),
                "characters": scene.get("characters", []),
                "output_dir": output_dir,
            },
        )
        tool_calls.append(
            {
                "tool": swap_result.get("tool", "face_swapper"),
                "status": "success" if swap_result.get("ok") else "failure",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if not swap_result.get("ok"):
            err = swap_result.get("error", {})
            return {
                "node_history": ["face_swap_node"],
                "branch_history": branches,
                "tool_calls": tool_calls,
                "errors": [
                    {
                        "code": err.get("code", "FACE_SWAP_FAILED"),
                        "message": err.get("message", "Face swap failed."),
                    }
                ],
            }

        identity_result = runtime.invoke_capability(
            "identity_validation",
            {
                "scene_id": target_scene_id,
                "characters": scene.get("characters", []),
                "threshold": 0.8,
            },
        )
        tool_calls.append(
            {
                "tool": identity_result.get("tool", "identity_validator"),
                "status": "success" if identity_result.get("ok") else "failure",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if not identity_result.get("ok"):
            err = identity_result.get("error", {})
            return {
                "node_history": ["face_swap_node"],
                "branch_history": branches,
                "tool_calls": tool_calls,
                "errors": [
                    {
                        "code": err.get("code", "IDENTITY_VALIDATION_FAILED"),
                        "message": err.get("message", "Identity validation failed."),
                    }
                ],
            }

        identity = identity_result["result"]["identity_validation"]
        if not identity.get("valid", False):
            return {
                "node_history": ["face_swap_node"],
                "branch_history": branches,
                "tool_calls": tool_calls,
                "errors": [
                    {
                        "code": "IDENTITY_VALIDATION_FAILED",
                        "message": f"Identity validation failed for scene {target_scene_id}.",
                    }
                ],
            }

        raw_scene = swap_result["result"]["raw_scene"]
        raw_scenes.append(raw_scene)
        face_swap_jobs.append(
            {
                "task_id": f"{target_scene_id}_F1",
                "scene_id": target_scene_id,
                "status": "completed",
                "artifact_id": raw_scene["artifact_id"],
                "identity_score": identity.get("score", 0.0),
            }
        )

    existing_artifacts = state.get("artifacts", {})
    memory_refs = state.get("memory_refs", {})
    commit_memory(
        request_id=state["request_id"],
        output_dir=output_dir,
        state_snapshot={
            "request_id": state["request_id"],
            "task_graph": state.get("task_graph", {}),
            "tasks": state.get("tasks", []),
            "artifacts": {
                "audio_tracks": existing_artifacts.get("audio_tracks", []),
                "frame_sequences": existing_artifacts.get("frame_sequences", []),
                "video_scenes": existing_artifacts.get("video_scenes", []),
                "raw_scenes": existing_artifacts.get("raw_scenes", []) + raw_scenes,
                "task_graph_logs": existing_artifacts.get("task_graph_logs", []),
            },
            "memory_refs": {
                "task_graph_ids": memory_refs.get("task_graph_ids", []),
                "audio_memory_ids": memory_refs.get("audio_memory_ids", []),
                "video_memory_ids": memory_refs.get("video_memory_ids", []) + [item["artifact_id"] for item in raw_scenes],
                "sync_memory_ids": memory_refs.get("sync_memory_ids", []),
            },
            "completed_scene_ids": [item.get("scene_id") for item in state.get("scene_results", []) if item.get("scene_id")],
        },
    )

    updated_face_refs = {
        "task_graph_ids": memory_refs.get("task_graph_ids", []),
        "audio_memory_ids": memory_refs.get("audio_memory_ids", []),
        "video_memory_ids": memory_refs.get("video_memory_ids", []) + [item["artifact_id"] for item in raw_scenes],
        "sync_memory_ids": memory_refs.get("sync_memory_ids", []),
    }

    return {
        "node_history": ["face_swap_node"],
        "branch_history": branches,
        "tool_calls": tool_calls,
        "face_swap_jobs": face_swap_jobs,
        "raw_scene_artifacts": raw_scenes,
    }
