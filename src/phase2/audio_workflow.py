from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from phase2.memory import commit_memory
from phase2.mcp import Phase2MCPRuntime
from phase2.state import Phase2State


def _runtime(state: Phase2State) -> Phase2MCPRuntime:
    config_path = state.get("test_flags", {}).get("mcp_config_path", "config/phase2_mcp_tools.json")
    return Phase2MCPRuntime(config_path)


def _add_error(state: Phase2State, code: str, message: str, details: Any | None = None) -> None:
    err = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    state["errors"].append(err)


def voice_synth_node(state: Phase2State) -> Phase2State:
    runtime = _runtime(state)
    output_dir = state.get("test_flags", {}).get("output_dir", "output/phase2")
    audio_tracks: list[dict[str, Any]] = []
    audio_jobs: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    branches = state.get("branch_history", [])
    scene_task = state.get("scene_task", {})
    scene_id = scene_task.get("scene_id", "unknown")
    scene_status = state.get("scene_status", "queued")
    if scene_status == "resumed":
        return {
            "node_history": ["voice_synth_node"],
            "branch_history": branches,
            "tool_calls": [],
            "audio_jobs": [],
            "audio_artifacts": [],
        }

    source_scene = state.get("source_scene", {})
    audio_task = (scene_task.get("audio_tasks") or [{}])[0]
    speaker = audio_task.get("speaker", "Unknown")
    dialogue_lines: list[dict[str, Any]] = source_scene.get("dialogue", [])

    for line in dialogue_lines:
        speaker_name = line.get("speaker", speaker)
        payload = {
            "request_id": state["request_id"],
            "scene_id": scene_id,
            "speaker": speaker_name,
            "dialogue": line.get("line", ""),
            "emotion": "tense" if "!" in line.get("line", "") else "neutral",
            "output_dir": output_dir,
        }
        result = runtime.invoke_capability("voice_synthesis", payload)
        tool_calls.append(
            {
                "tool": result.get("tool", "voice_cloning_synthesizer"),
                "status": "success" if result.get("ok") else "failure",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if not result.get("ok"):
            err = result.get("error", {})
            return {
                "node_history": ["voice_synth_node"],
                "branch_history": branches,
                "tool_calls": tool_calls,
                "errors": [
                    {
                        "code": err.get("code", "VOICE_SYNTH_FAILED"),
                        "message": err.get("message", "Voice synthesis failed."),
                    }
                ],
            }
        audio_track = result["result"]["audio_track"]
        audio_tracks.append(audio_track)
        audio_jobs.append(
            {
                "task_id": audio_task.get("task_id", f"{scene_id}_A1"),
                "scene_id": scene_id,
                "speaker": speaker_name,
                "status": "completed",
                "artifact_id": audio_track["artifact_id"],
            }
        )

    existing_artifacts = state.get("artifacts", {})
    committed_audio = existing_artifacts.get("audio_tracks", []) + audio_tracks
    memory_refs = state.get("memory_refs", {})
    commit_memory(
        request_id=state["request_id"],
        output_dir=output_dir,
        state_snapshot={
            "request_id": state["request_id"],
            "task_graph": state.get("task_graph", {}),
            "tasks": state.get("tasks", []),
            "artifacts": {
                "audio_tracks": committed_audio,
                "frame_sequences": existing_artifacts.get("frame_sequences", []),
                "video_scenes": existing_artifacts.get("video_scenes", []),
                "raw_scenes": existing_artifacts.get("raw_scenes", []),
                "task_graph_logs": existing_artifacts.get("task_graph_logs", []),
            },
            "memory_refs": {
                "task_graph_ids": memory_refs.get("task_graph_ids", []),
                "audio_memory_ids": memory_refs.get("audio_memory_ids", []) + [item["artifact_id"] for item in audio_tracks],
                "video_memory_ids": memory_refs.get("video_memory_ids", []),
                "sync_memory_ids": memory_refs.get("sync_memory_ids", []),
            },
            "completed_scene_ids": [item.get("scene_id") for item in state.get("scene_results", []) if item.get("scene_id")],
        },
    )

    updated_memory_refs = {
        "task_graph_ids": memory_refs.get("task_graph_ids", []),
        "audio_memory_ids": memory_refs.get("audio_memory_ids", []) + [item["artifact_id"] for item in audio_tracks],
        "video_memory_ids": memory_refs.get("video_memory_ids", []),
        "sync_memory_ids": memory_refs.get("sync_memory_ids", []),
    }

    return {
        "node_history": ["voice_synth_node"],
        "branch_history": branches,
        "tool_calls": tool_calls,
        "audio_jobs": audio_jobs,
        "audio_artifacts": audio_tracks,
    }
