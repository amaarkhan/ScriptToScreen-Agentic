from pathlib import Path

from phase1.identity import verify_identity_consistency
from phase1.orchestration.state import empty_state
from phase1.orchestration.workflow import build_phase1_graph


def _assert_standard_scene_shape(scene: dict) -> None:
    expected_keys = {
        "scene_id",
        "order",
        "location",
        "time_of_day",
        "characters",
        "actions",
        "dialogue",
        "visual_cues",
    }
    assert expected_keys.issubset(scene.keys())


def test_auto_mode_happy_path_completes(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-auto-1",
        input_mode="auto",
        prompt="A rescue mission in a flooded city.",
        script_text=None,
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    assert len(out["scenes"]) >= 1
    _assert_standard_scene_shape(out["scenes"][0])
    assert len(out["scenes"][0]["dialogue"]) >= 1
    assert len(out["scenes"][0]["visual_cues"]) >= 1
    assert len(out["characters"]) >= 1
    assert len(out["images"]) >= 1
    assert Path(out["artifacts"]["character_db"]).exists()
    assert Path(out["artifacts"]["images_dir"]).exists()
    assert Path(out["artifacts"]["scene_manifest"]).exists()
    assert Path(out["artifacts"]["memory_dir"]).exists()
    assert Path(out["images"][0]["path"]).exists()
    assert out["memory_refs"]["script_history_ids"]
    tool_names = {item["tool"] for item in out["audit"]["tool_calls"]}
    assert "generate_script_segment" in tool_names
    assert "generate_character_image" in tool_names
    assert "commit_memory" in tool_names
    assert "mode_selector_node" in out["audit"]["node_history"]


def test_auto_mode_hacker_vs_ai_prompt_stays_semantic(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-auto-hacker-ai",
        input_mode="auto",
        prompt="In a futuristic city, a young hacker discovers a hidden AI controlling the entire power grid.",
        script_text=None,
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    characters = {character["name"] for character in out["characters"]}
    assert "AI Core" in characters
    assert "Maya" in characters
    dialogue_speakers = {line["speaker"] for scene in out["scenes"] for line in scene["dialogue"]}
    assert "AI Core" in dialogue_speakers
    assert "Maya" in dialogue_speakers


def test_manual_mode_invalid_script_rejects() -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-manual-invalid",
        input_mode="manual",
        prompt=None,
        script_text="Only plain text with no screenplay structure",
    )

    out = app.invoke(state)

    assert out["status"] == "rejected"
    codes = {err["code"] for err in out["errors"]}
    assert "SVALID_MISSING_SCENE_HEADER" in codes
    suggestions = [err.get("details", {}).get("suggestion", "") for err in out["errors"]]
    assert any("SCENE" in suggestion for suggestion in suggestions)


def test_manual_mode_valid_script_normalizes_to_standard_format(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-manual-valid",
        input_mode="manual",
        prompt=None,
        script_text="""SCENE 1: City Street - Night
ACTION: Rain lashes the empty road.
A: We move now.
B: Then we move together.
SCENE 2: Rooftop - Dawn
ACTION: The skyline brightens behind them.
A: No more delay.
B: We finish this today.
""",
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    assert len(out["scenes"]) == 2
    _assert_standard_scene_shape(out["scenes"][0])
    assert out["scenes"][0]["location"] == "City Street"
    assert out["scenes"][0]["time_of_day"] == "Night"
    assert out["scenes"][1]["order"] == 2
    assert Path(out["artifacts"]["character_db"]).exists()
    assert Path(out["artifacts"]["scene_manifest"]).exists()
    assert Path(out["artifacts"]["memory_dir"]).exists()
    assert len(list(Path(out["artifacts"]["images_dir"]).glob("*.png"))) >= 1
    assert out["characters"][0].get("stock_footage_ref") is not None


def test_manual_mode_preserves_exact_speaker_labels(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-manual-exact-speakers",
        input_mode="manual",
        prompt=None,
        script_text="""SCENE 1: Control Room - Night
ACTION: Screens flicker across the wall.
AI Core: System stability compromised.
MAYA: I know who you are.
""",
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    assert out["scenes"][0]["dialogue"][0]["speaker"] == "AI Core"
    assert out["scenes"][0]["dialogue"][1]["speaker"] == "MAYA"
    assert {character["name"] for character in out["characters"]} == {"AI Core", "MAYA"}


def test_manual_mode_accepts_alternate_scene_header_and_dialogue_styles(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-manual-alt-format",
        input_mode="manual",
        prompt=None,
        script_text="""INT. Abandoned Street - Night
The streetlights flicker while the city trembles.
Zara - The whole grid is down.
Rehan — Then we fix it before it spreads.

EXT. Power Control Room - Dawn
Sparks fly as systems begin to reboot.
Zara: It’s working!
Rehan: Hold it steady, almost there.
""",
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    assert len(out["scenes"]) == 2
    assert out["scenes"][0]["location"] == "Abandoned Street"
    assert set(out["scenes"][0]["characters"]) == {"Rehan", "Zara"}
    assert out["scenes"][0]["actions"]
    assert out["scenes"][0]["dialogue"]
    assert out["scenes"][1]["location"] == "Power Control Room"


def test_manual_mode_handles_dotted_and_hyphenated_speaker_names(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-manual-speaker-names",
        input_mode="manual",
        prompt=None,
        script_text="""SCENE 1: Research Lab - Night
ACTION: Sparks fly as machines overload and alarms blare.
Dr. Elena: The core is destabilizing!
Unit-7: Emergency protocol initiated.
""",
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    assert set(out["scenes"][0]["characters"]) == {"Dr. Elena", "Unit-7"}
    speakers = [line["speaker"] for line in out["scenes"][0]["dialogue"]]
    assert "Dr. Elena" in speakers
    assert "Unit-7" in speakers


def test_dual_modes_produce_same_scene_contract_shape(tmp_path: Path) -> None:
    app = build_phase1_graph()

    auto_state = empty_state(
        request_id="t-shape-auto",
        input_mode="auto",
        prompt="A tense pursuit across a station district.",
        script_text=None,
    )
    auto_state["hitl_decision"] = "approve"
    auto_state["test_flags"] = {"output_dir": (tmp_path / "auto").as_posix()}
    auto_out = app.invoke(auto_state)

    manual_state = empty_state(
        request_id="t-shape-manual",
        input_mode="manual",
        prompt=None,
        script_text="""SCENE 1: Central Station - Night
ACTION: Sirens echo through the terminal.
Rae: We cannot miss this train.
Ivo: Then stop looking back.
""",
    )
    manual_state["hitl_decision"] = "approve"
    manual_state["test_flags"] = {"output_dir": (tmp_path / "manual").as_posix()}
    manual_out = app.invoke(manual_state)

    assert auto_out["status"] == "completed"
    assert manual_out["status"] == "completed"

    auto_keys = set(auto_out["scenes"][0].keys())
    manual_keys = set(manual_out["scenes"][0].keys())
    assert auto_keys == manual_keys


def test_output_artifacts_use_images_directory(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-image-assets",
        input_mode="auto",
        prompt="A negotiation at a train station during a storm.",
        script_text=None,
    )
    state["hitl_decision"] = "approve"
    state["test_flags"] = {"output_dir": tmp_path.as_posix()}

    out = app.invoke(state)

    assert out["status"] == "completed"
    assert Path(out["artifacts"]["images_dir"]).name == "Images"


def test_identity_consistency_detects_duplicate_normalized_names() -> None:
    scenes = [
        {
            "characters": ["Ari", "ari"],
            "dialogue": [{"speaker": "Ari", "line": "Move.", "visual_clue": "close-up"}],
            "visual_cues": [],
        }
    ]
    characters = [
        {"name": "Ari"},
        {"name": "ari"},
    ]

    errors = verify_identity_consistency(scenes, characters)

    assert any(err["code"] == "CHAR_IDENTITY_CONFLICT" for err in errors)


def test_missing_mcp_config_fails_cleanly(tmp_path: Path) -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-mcp-missing",
        input_mode="auto",
        prompt="A bridge standoff before sunrise.",
        script_text=None,
    )
    state["test_flags"] = {
        "output_dir": tmp_path.as_posix(),
        "mcp_config_path": (tmp_path / "missing_tools.json").as_posix(),
    }

    out = app.invoke(state)

    assert out["status"] == "failed"
    assert any(err["code"] == "MCP_RUNTIME_INIT_FAILED" for err in out["errors"])


def test_hitl_revise_routes_back_then_completes() -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-revise-1",
        input_mode="auto",
        prompt="A train station farewell that turns into a chase.",
        script_text=None,
    )
    state["hitl_decision"] = "revise"
    state["max_revisions"] = 0

    out = app.invoke(state)

    assert out["status"] == "rejected"
    assert any(err["code"] == "HITL_MAX_REVISIONS_EXCEEDED" for err in out["errors"])


def test_hitl_requires_explicit_human_decision() -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-hitl-required",
        input_mode="auto",
        prompt="A tense rooftop standoff at dawn.",
        script_text=None,
    )
    state["test_flags"] = {"llm_mode": "fallback"}

    out = app.invoke(state)

    assert out["status"] == "rejected"
    assert any(err["code"] == "HITL_DECISION_REQUIRED" for err in out["errors"])


def test_tool_failure_routes_to_failed() -> None:
    app = build_phase1_graph()
    state = empty_state(
        request_id="t-fail-1",
        input_mode="auto",
        prompt="A midnight confession in a parking lot.",
        script_text=None,
    )
    state["test_flags"] = {"scriptwriter_tool_unavailable": True}

    out = app.invoke(state)

    assert out["status"] == "failed"
    assert any(err["code"] == "SWRITER_TOOL_UNAVAILABLE" for err in out["errors"])
