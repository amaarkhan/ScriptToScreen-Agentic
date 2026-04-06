from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from phase2.audio_workflow import voice_synth_node
from phase2.memory import commit_memory, load_checkpoint
from phase2.mcp import Phase2MCPRuntime
from phase2.sync_workflow import lip_sync_node
from phase2.state import Phase2State, empty_phase2_state
from phase2.task_graph import write_task_graph_log
from phase2.video_workflow import face_swap_node, video_gen_node


def _add_error(state: Phase2State, code: str, message: str, details: Any | None = None) -> None:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    state["errors"].append(error)


def _add_event(state: Phase2State, field: str, value: Any) -> None:
    state.setdefault(field, [])
    state[field].append(value)


def _runtime(state: Phase2State) -> Phase2MCPRuntime:
    config_path = state.get("test_flags", {}).get("mcp_config_path", "config/phase2_mcp_tools.json")
    return Phase2MCPRuntime(config_path)


def _final_artifacts_from_disk(output_dir: str, request_id: str) -> dict[str, list[dict[str, Any]]]:
    run_dir = Path(output_dir) / "phase2" / request_id
    audio_tracks: list[dict[str, Any]] = []
    for path in sorted((run_dir / "audio").glob("*.wav")):
        scene_id = path.stem.split("_")[0]
        audio_tracks.append({"artifact_id": f"wav_{scene_id}", "path": path.as_posix(), "scene_id": scene_id, "type": "wav"})

    frame_sequences: list[dict[str, Any]] = []
    video_scenes: list[dict[str, Any]] = []
    raw_scenes: list[dict[str, Any]] = []
    video_root = run_dir / "video"
    if video_root.exists():
        for scene_dir in sorted(p for p in video_root.iterdir() if p.is_dir()):
            scene_id = scene_dir.name
            frames_json = scene_dir / "frames.json"
            video_mp4 = scene_dir / f"{scene_id}_video_scene.mp4"
            raw_mp4 = scene_dir / f"{scene_id}_raw_scene.mp4"
            if frames_json.exists():
                frame_sequences.append({"artifact_id": f"frames_{scene_id}", "path": frames_json.as_posix(), "scene_id": scene_id, "type": "frame_sequence"})
            if video_mp4.exists():
                video_scenes.append({"artifact_id": f"vscene_{scene_id}", "path": video_mp4.as_posix(), "scene_id": scene_id, "type": "mp4"})
            if raw_mp4.exists():
                raw_scenes.append({"artifact_id": f"raw_{scene_id}", "path": raw_mp4.as_posix(), "scene_id": scene_id, "type": "mp4"})

    final_raw_scenes: list[dict[str, Any]] = []
    final_root = run_dir / "raw_scenes"
    for path in sorted(final_root.glob("*.mp4")):
        scene_id = path.stem
        final_raw_scenes.append({"artifact_id": f"sync_{scene_id}", "path": path.as_posix(), "scene_id": scene_id, "type": "mp4"})

    task_graph_logs: list[dict[str, Any]] = []
    task_graph_path = run_dir / "task_graph_logs" / "task_graph.json"
    if task_graph_path.exists():
        task_graph_logs.append({"artifact_id": f"tlog_{request_id}", "path": task_graph_path.as_posix(), "type": "task_graph_log"})

    return {
        "audio_tracks": audio_tracks,
        "frame_sequences": frame_sequences,
        "video_scenes": video_scenes,
        "raw_scenes": final_raw_scenes if final_raw_scenes else raw_scenes,
        "task_graph_logs": task_graph_logs,
    }


def scene_parser_node(state: Phase2State) -> Phase2State:
    state["node_history"].append("scene_parser_node")
    state["status"] = "parsing"

    manifest_path = Path(state["input_manifest"]["path"])
    if not manifest_path.exists():
        _add_error(state, "SPARSE_INVALID_MANIFEST", f"Manifest not found: {manifest_path.as_posix()}")
        state["status"] = "failed"
        return state

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("scenes"):
        _add_error(state, "SPARSE_EMPTY_SCENES", "Scene manifest has no scenes.")
        state["status"] = "failed"
        return state

    state["request_id"] = manifest.get("request_id", state["request_id"])
    state["scenes"] = manifest["scenes"]

    runtime = _runtime(state)
    result = runtime.invoke_capability(
        "task_graph_generation",
        {"request_id": state["request_id"], "scene_manifest_path": manifest_path.as_posix(), "scene_manifest": manifest},
    )
    state["tool_calls"].append(
        {
            "tool": result.get("tool", "get_task_graph"),
            "status": "success" if result.get("ok") else "failure",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    if not result.get("ok"):
        err = result.get("error", {})
        _add_error(state, err.get("code", "SPARSE_TASK_GRAPH_FAILED"), err.get("message", "Task graph generation failed."))
        state["status"] = "failed"
        return state

    payload = result["result"]
    state["task_graph"] = payload["task_graph"]
    state["tasks"] = payload["tasks"]
    state["status"] = "graphing"

    run_dir = Path(state.get("test_flags", {}).get("output_dir", "output/phase2")) / "phase2" / state["request_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    graph_log = write_task_graph_log(payload["task_graph"], (run_dir / "task_graph_logs").as_posix())
    state["artifacts"]["task_graph_logs"] = [
        {
            "artifact_id": f"tlog_{state['request_id']}",
            "path": graph_log.as_posix(),
            "type": "task_graph_log",
        }
    ]
    state["checkpoint_path"] = (run_dir / "checkpoint.json").as_posix()

    initial_checkpoint = commit_memory(
        request_id=state["request_id"],
        output_dir=state.get("test_flags", {}).get("output_dir", "output/phase2"),
        state_snapshot={
            "request_id": state["request_id"],
            "task_graph": state["task_graph"],
            "tasks": state["tasks"],
            "artifacts": state["artifacts"],
            "memory_refs": state["memory_refs"],
            "completed_scene_ids": [],
        },
    )
    state["checkpoint_path"] = initial_checkpoint["checkpoint_path"]
    state["memory_refs"]["task_graph_ids"] = initial_checkpoint["memory_refs"]["task_graph_ids"]
    state["status"] = "branching"
    return state


def route_scene_tasks(state: Phase2State):
    checkpoint = load_checkpoint(state.get("test_flags", {}).get("output_dir", "output/phase2"), state["request_id"])
    completed_scene_ids = set(checkpoint.get("completed_scene_ids", []))
    sends = []
    for scene_task in state.get("task_graph", {}).get("scene_tasks", []):
        sends.append(
            Send(
                "scene_task_node",
                {
                    "scene_task": scene_task,
                    "output_dir": state.get("test_flags", {}).get("output_dir", "output/phase2"),
                    "checkpoint_path": state.get("checkpoint_path", ""),
                    "completed_scene_ids": list(completed_scene_ids),
                },
            )
        )
    return sends


def scene_task_node(state: Phase2State) -> Phase2State:
    scene_id = state["scene_task"]["scene_id"]
    branch_name = f"scene_{scene_id}"
    scene_task = state["scene_task"]
    completed_scene_ids = set(state.get("completed_scene_ids", []))

    if scene_id in completed_scene_ids:
        result_status = "resumed"
    else:
        result_status = "queued"
        completed_scene_ids.add(scene_id)

    scene_result = {
        "scene_id": scene_id,
        "order": scene_task["order"],
        "audio_tasks": scene_task["audio_tasks"],
        "video_tasks": scene_task["video_tasks"],
        "sync_tasks": scene_task["sync_tasks"],
        "status": result_status,
    }
    source_scene = {}
    for scene in state.get("scenes", []):
        if scene.get("scene_id") == scene_id:
            source_scene = scene
            break
    return {
        "node_history": ["scene_task_node"],
        "branch_history": [branch_name],
        "scene_task": scene_task,
        "scene_status": result_status,
        "source_scene": source_scene,
        "scene_results": [scene_result],
        "task_graph_logs": [
            {
                "artifact_id": f"log_{scene_id}",
                "path": state.get("checkpoint_path", ""),
                "type": "task_graph_log",
                "scene_id": scene_id,
            }
        ],
    }


def route_media_branches(state: Phase2State):
    scene_result = state.get("scene_results", [])[-1] if state.get("scene_results") else {}
    scene_id = scene_result.get("scene_id", "")
    if not scene_id:
        return []

    scene_task = {}
    for task in state.get("task_graph", {}).get("scene_tasks", []):
        if task.get("scene_id") == scene_id:
            scene_task = task
            break
    if not scene_task:
        return []

    source_scene = {}
    for scene in state.get("scenes", []):
        if scene.get("scene_id") == scene_id:
            source_scene = scene
            break

    scene_status = scene_result.get("status", "queued")

    payload = {
        "scene_task": scene_task,
        "scene_status": scene_status,
        "source_scene": source_scene,
        "test_flags": state.get("test_flags", {}),
        "request_id": state.get("request_id", ""),
        "task_graph": state.get("task_graph", {}),
        "tasks": state.get("tasks", []),
        "artifacts": state.get("artifacts", {}),
        "memory_refs": state.get("memory_refs", {}),
        "scene_results": state.get("scene_results", []),
        "audio_artifacts": state.get("audio_artifacts", []),
        "video_scene_artifacts": state.get("video_scene_artifacts", []),
        "raw_scene_artifacts": state.get("raw_scene_artifacts", []),
        "sync_artifacts": state.get("sync_artifacts", []),
        "branch_history": state.get("branch_history", []),
    }
    return [Send("voice_synth_node", payload), Send("video_gen_node", payload)]


def build_phase2_graph():
    builder = StateGraph(Phase2State)
    builder.add_node("scene_parser_node", scene_parser_node)
    builder.add_node("scene_task_node", scene_task_node)
    builder.add_node("voice_synth_node", voice_synth_node)
    builder.add_node("video_gen_node", video_gen_node)
    builder.add_node("face_swap_node", face_swap_node)
    builder.add_node("lip_sync_node", lip_sync_node)
    builder.add_edge(START, "scene_parser_node")
    builder.add_conditional_edges("scene_parser_node", route_scene_tasks)
    builder.add_conditional_edges("scene_task_node", route_media_branches)
    builder.add_edge("video_gen_node", "face_swap_node")
    builder.add_edge("voice_synth_node", "lip_sync_node")
    builder.add_edge("face_swap_node", "lip_sync_node")
    builder.add_edge("lip_sync_node", END)
    return builder.compile()


def run_phase2_pipeline(manifest_path: str, request_id: str, output_dir: str, mcp_config_path: str | None = None) -> Phase2State:
    app = build_phase2_graph()
    state = empty_phase2_state(request_id=request_id, manifest_path=manifest_path)
    state["test_flags"] = {"output_dir": output_dir}
    if mcp_config_path:
        state["test_flags"]["mcp_config_path"] = mcp_config_path
    result = app.invoke(state)

    if result.get("status") == "failed":
        result["audit"] = {
            "tool_calls": result.get("tool_calls", []),
            "node_history": result.get("node_history", []),
            "branch_history": result.get("branch_history", []),
        }
        return result

    completed_scene_ids = [scene["scene_id"] for scene in result.get("scene_results", [])]
    final_artifacts = _final_artifacts_from_disk(output_dir, result.get("request_id", request_id))
    audio_artifacts = final_artifacts["audio_tracks"]
    frame_artifacts = final_artifacts["frame_sequences"]
    video_scene_artifacts = final_artifacts["video_scenes"]
    raw_scene_artifacts = final_artifacts["raw_scenes"]
    task_graph_logs = final_artifacts["task_graph_logs"]
    final_memory_refs = {
        "task_graph_ids": [item["artifact_id"] for item in task_graph_logs],
        "audio_memory_ids": [item["artifact_id"] for item in audio_artifacts],
        "video_memory_ids": [item["artifact_id"] for item in raw_scene_artifacts],
        "sync_memory_ids": [item["artifact_id"] for item in raw_scene_artifacts],
    }
    artifacts = final_artifacts
    checkpoint = commit_memory(
        request_id=request_id,
        output_dir=output_dir,
        state_snapshot={
            "request_id": result.get("request_id", request_id),
            "task_graph": result.get("task_graph", {}),
            "tasks": result.get("tasks", []),
            "artifacts": artifacts,
            "memory_refs": final_memory_refs,
            "completed_scene_ids": completed_scene_ids,
        },
    )
    result["checkpoint_path"] = checkpoint["checkpoint_path"]
    result["memory_refs"] = checkpoint["memory_refs"]
    result["completed_scene_ids"] = checkpoint["completed_scene_ids"]
    result["scene_results"] = result.get("scene_results", [])
    result["task_graph_logs"] = result.get("task_graph_logs", [])
    result["tool_calls"] = result.get("tool_calls", [])
    result["node_history"] = result.get("node_history", [])
    result["branch_history"] = result.get("branch_history", [])
    result["artifacts"] = artifacts
    result["memory_refs"] = final_memory_refs
    result["status"] = "resumed" if result.get("scene_results") and all(item.get("status") == "resumed" for item in result.get("scene_results", [])) else "completed"
    result["audit"] = {
        "tool_calls": result.get("tool_calls", []),
        "node_history": result.get("node_history", []),
        "branch_history": result.get("branch_history", []),
    }
    return result
