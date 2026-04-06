from __future__ import annotations

from typing import Any

from phase2.audio import synthesize_voice_for_dialogue
from phase2.memory import commit_memory as commit_phase2_memory
from phase2.sync import align_lip_sync
from phase2.task_graph import build_scene_task_graph
from phase2.video import apply_face_swap, generate_scene_visuals, validate_identity


def tool_get_task_graph(payload: dict[str, Any]) -> dict[str, Any]:
    scene_manifest = payload["scene_manifest"]
    result = build_scene_task_graph(scene_manifest)
    return {"task_graph": result["task_graph"], "tasks": result["tasks"], "errors": []}


def tool_commit_memory(payload: dict[str, Any]) -> dict[str, Any]:
    result = commit_phase2_memory(
        request_id=payload["request_id"],
        output_dir=payload["output_dir"],
        state_snapshot=payload["state_snapshot"],
    )
    return {"result": result, "errors": []}


def tool_voice_cloning_synthesizer(payload: dict[str, Any]) -> dict[str, Any]:
    audio_track = synthesize_voice_for_dialogue(
        request_id=payload["request_id"],
        scene_id=payload["scene_id"],
        speaker=payload["speaker"],
        dialogue=payload["dialogue"],
        emotion=payload["emotion"],
        output_dir=payload["output_dir"],
    )
    return {"audio_track": audio_track, "errors": []}


def tool_query_stock_footage(payload: dict[str, Any]) -> dict[str, Any]:
    visuals = generate_scene_visuals(
        request_id=payload["request_id"],
        scene_id=payload["scene_id"],
        visual_cues=payload.get("visual_cues", []),
        location=payload["location"],
        output_dir=payload["output_dir"],
    )
    return {"frame_sequence": visuals["frame_sequence"], "video_scene": visuals["video_scene"], "errors": []}


def tool_face_swapper(payload: dict[str, Any]) -> dict[str, Any]:
    swapped = apply_face_swap(
        request_id=payload["request_id"],
        scene_id=payload["scene_id"],
        source_video_path=payload["source_video_path"],
        characters=payload.get("characters", []),
        output_dir=payload["output_dir"],
    )
    return {"raw_scene": swapped["raw_scene"], "errors": []}


def tool_identity_validator(payload: dict[str, Any]) -> dict[str, Any]:
    identity = validate_identity(
        scene_id=payload["scene_id"],
        characters=payload.get("characters", []),
        threshold=payload.get("threshold", 0.8),
    )
    return {"identity_validation": identity, "errors": []}


def tool_lip_sync_aligner(payload: dict[str, Any]) -> dict[str, Any]:
    synced_scene = align_lip_sync(
        request_id=payload["request_id"],
        scene_id=payload["scene_id"],
        audio_path=payload["audio_path"],
        video_path=payload["video_path"],
        output_dir=payload["output_dir"],
        scene_order=payload.get("scene_order"),
    )
    return {"synced_scene": synced_scene, "errors": []}


TOOL_HANDLERS = {
    "get_task_graph": tool_get_task_graph,
    "commit_memory": tool_commit_memory,
    "voice_cloning_synthesizer": tool_voice_cloning_synthesizer,
    "query_stock_footage": tool_query_stock_footage,
    "face_swapper": tool_face_swapper,
    "identity_validator": tool_identity_validator,
    "lip_sync_aligner": tool_lip_sync_aligner,
}
