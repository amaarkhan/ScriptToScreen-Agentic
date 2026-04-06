from __future__ import annotations

import json
from pathlib import Path

from phase2.workflow import run_phase2_pipeline


def _copy_manifest(source: Path, destination: Path) -> None:
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_phase2_scene_parser_builds_task_graph_and_logs(tmp_path: Path) -> None:
    manifest_src = Path("output/acceptance/auto_v4/scene_manifest.json")
    manifest_path = tmp_path / "scene_manifest.json"
    _copy_manifest(manifest_src, manifest_path)

    result = run_phase2_pipeline(
        manifest_path.as_posix(),
        request_id="phase2-d2-test-1",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )

    assert result["status"] == "completed"
    assert result["task_graph"]["scene_tasks"]
    assert len(result["task_graph"]["scene_tasks"]) == 3
    assert len(result["tasks"]) == 12
    assert result["task_graph_logs"]
    assert Path(result["checkpoint_path"]).exists()
    assert any(branch.startswith("scene_") for branch in result["audit"]["branch_history"])


def test_phase2_pipeline_resumes_from_checkpoint(tmp_path: Path) -> None:
    manifest_src = Path("output/acceptance/manual_v4/scene_manifest.json")
    manifest_path = tmp_path / "scene_manifest.json"
    _copy_manifest(manifest_src, manifest_path)

    first = run_phase2_pipeline(
        manifest_path.as_posix(),
        request_id="phase2-d2-test-2",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )
    second = run_phase2_pipeline(
        manifest_path.as_posix(),
        request_id="phase2-d2-test-2",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )

    assert first["status"] == "completed"
    assert second["status"] in {"completed", "resumed"}
    assert Path(second["checkpoint_path"]).exists()


def test_phase2_invalid_manifest_fails(tmp_path: Path) -> None:
    missing = tmp_path / "missing_scene_manifest.json"

    result = run_phase2_pipeline(
        missing.as_posix(),
        request_id="phase2-d2-test-3",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )

    assert result["status"] == "failed"
    assert any(err["code"] == "SPARSE_INVALID_MANIFEST" for err in result["errors"])


def test_phase2_audio_branch_writes_wav_artifacts(tmp_path: Path) -> None:
    manifest_src = Path("output/acceptance/manual_v4/scene_manifest.json")
    manifest_path = tmp_path / "scene_manifest.json"
    _copy_manifest(manifest_src, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_tracks = sum(len(scene.get("dialogue", [])) for scene in manifest.get("scenes", []))

    result = run_phase2_pipeline(
        manifest_path.as_posix(),
        request_id="phase2-d3-test-1",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )

    audio_tracks = result["artifacts"]["audio_tracks"]
    assert result["status"] == "completed"
    assert len(audio_tracks) == expected_tracks
    assert len(result["memory_refs"]["audio_memory_ids"]) == expected_tracks
    assert all(track["path"].endswith(".wav") for track in audio_tracks)
    assert all(Path(track["path"]).exists() for track in audio_tracks)


def test_phase2_video_and_face_swap_branch_writes_scene_artifacts(tmp_path: Path) -> None:
    manifest_src = Path("output/acceptance/auto_v4/scene_manifest.json")
    manifest_path = tmp_path / "scene_manifest.json"
    _copy_manifest(manifest_src, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_scenes = len(manifest.get("scenes", []))

    result = run_phase2_pipeline(
        manifest_path.as_posix(),
        request_id="phase2-d4-test-1",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )

    frame_sequences = result["artifacts"]["frame_sequences"]
    video_scenes = result["artifacts"]["video_scenes"]
    raw_scenes = result["artifacts"]["raw_scenes"]

    assert result["status"] == "completed"
    assert len(frame_sequences) == expected_scenes
    assert len(video_scenes) == expected_scenes
    assert len(raw_scenes) == expected_scenes
    assert len(result["memory_refs"]["video_memory_ids"]) == expected_scenes

    assert all(item["path"].endswith(".json") for item in frame_sequences)
    assert all(item["path"].endswith(".mp4") for item in video_scenes)
    assert all(item["path"].endswith(".mp4") for item in raw_scenes)
    assert all(Path(item["path"]).exists() for item in frame_sequences)
    assert all(Path(item["path"]).exists() for item in video_scenes)
    assert all(Path(item["path"]).exists() for item in raw_scenes)


def test_phase2_lip_sync_branch_writes_final_raw_scenes(tmp_path: Path) -> None:
    manifest_src = Path("output/acceptance/manual_v4/scene_manifest.json")
    manifest_path = tmp_path / "scene_manifest.json"
    _copy_manifest(manifest_src, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_scenes = len(manifest.get("scenes", []))

    result = run_phase2_pipeline(
        manifest_path.as_posix(),
        request_id="phase2-d5-test-1",
        output_dir=tmp_path.as_posix(),
        mcp_config_path="config/phase2_mcp_tools.json",
    )

    final_raw_scenes = result["artifacts"]["raw_scenes"]
    sync_jobs = result["sync_jobs"]

    assert result["status"] == "completed"
    assert len(final_raw_scenes) == expected_scenes
    assert len(sync_jobs) == expected_scenes
    assert len(result["memory_refs"]["sync_memory_ids"]) == expected_scenes
    assert all(item["path"].endswith(".mp4") for item in final_raw_scenes)
    assert all(Path(item["path"]).exists() for item in final_raw_scenes)
    assert [Path(item["path"]).name for item in final_raw_scenes] == ["scene_01.mp4", "scene_02.mp4", "scene_03.mp4"]
    assert "voice_synth_node" in result["audit"]["node_history"]
    assert "video_gen_node" in result["audit"]["node_history"]
    assert "face_swap_node" in result["audit"]["node_history"]
    assert "lip_sync_node" in result["audit"]["node_history"]
