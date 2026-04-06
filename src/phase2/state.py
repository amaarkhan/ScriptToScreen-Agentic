from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict


class Phase2State(TypedDict, total=False):
    request_id: str
    input_manifest: dict[str, Any]
    scenes: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    task_graph: dict[str, Any]
    audio_jobs: Annotated[list[dict[str, Any]], add]
    audio_artifacts: Annotated[list[dict[str, Any]], add]
    frame_artifacts: Annotated[list[dict[str, Any]], add]
    video_scene_artifacts: Annotated[list[dict[str, Any]], add]
    raw_scene_artifacts: Annotated[list[dict[str, Any]], add]
    sync_artifacts: Annotated[list[dict[str, Any]], add]
    video_jobs: Annotated[list[dict[str, Any]], add]
    face_swap_jobs: Annotated[list[dict[str, Any]], add]
    sync_jobs: Annotated[list[dict[str, Any]], add]
    artifacts: dict[str, list[dict[str, Any]]]
    memory_refs: dict[str, list[str]]
    status: Literal[
        "received",
        "parsing",
        "graphing",
        "branching",
        "processing_audio",
        "processing_video",
        "face_swapping",
        "syncing",
        "audio_synthesizing",
        "completed",
        "failed",
        "resumed",
    ]
    errors: list[dict[str, Any]]
    audit: dict[str, list[dict[str, Any]] | list[str]]
    checkpoint_path: str
    test_flags: dict[str, Any]
    scene_results: Annotated[list[dict[str, Any]], add]
    task_graph_logs: Annotated[list[dict[str, Any]], add]
    tool_calls: Annotated[list[dict[str, Any]], add]
    node_history: Annotated[list[str], add]
    branch_history: Annotated[list[str], add]


def empty_phase2_state(request_id: str, manifest_path: str, scene_count: int = 0) -> Phase2State:
    return {
        "request_id": request_id,
        "input_manifest": {"path": manifest_path, "scene_count": scene_count},
        "scenes": [],
        "tasks": [],
        "task_graph": {},
        "audio_jobs": [],
        "audio_artifacts": [],
        "frame_artifacts": [],
        "video_scene_artifacts": [],
        "raw_scene_artifacts": [],
        "sync_artifacts": [],
        "video_jobs": [],
        "face_swap_jobs": [],
        "sync_jobs": [],
        "artifacts": {
            "audio_tracks": [],
            "frame_sequences": [],
            "video_scenes": [],
            "raw_scenes": [],
            "task_graph_logs": [],
        },
        "memory_refs": {
            "task_graph_ids": [],
            "audio_memory_ids": [],
            "video_memory_ids": [],
            "sync_memory_ids": [],
        },
        "status": "received",
        "errors": [],
        "audit": {"tool_calls": [], "node_history": [], "branch_history": []},
        "scene_results": [],
        "task_graph_logs": [],
        "tool_calls": [],
        "node_history": [],
        "branch_history": [],
        "test_flags": {},
    }
