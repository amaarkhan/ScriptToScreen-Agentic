from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from phase1.artifacts import write_character_db, write_scene_manifest
from phase1.identity import extract_character_profiles, verify_identity_consistency
from phase1.mcp import MCPRuntime

from .state import ErrorItem, WorkflowState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_node_audit(state: WorkflowState, node_name: str) -> None:
    state["audit"]["node_history"].append(node_name)


def _add_tool_audit(state: WorkflowState, tool_name: str, ok: bool) -> None:
    state["audit"]["tool_calls"].append(
        {
            "tool": tool_name,
            "status": "success" if ok else "failure",
            "timestamp": _now_iso(),
        }
    )


def _add_error(state: WorkflowState, code: str, message: str, details: object | None = None) -> None:
    err: ErrorItem = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    state["errors"].append(err)


def _validate_input_invariants(state: WorkflowState) -> bool:
    mode = state["input_mode"]
    prompt = state["raw_input"]["prompt"]
    script_text = state["raw_input"]["script_text"]

    if mode == "manual" and isinstance(script_text, str) and script_text.strip() and prompt is None:
        return True
    if mode == "auto" and isinstance(prompt, str) and prompt.strip() and script_text is None:
        return True
    return False


def _mcp_runtime(state: WorkflowState) -> MCPRuntime:
    config_path = state.get("test_flags", {}).get("mcp_config_path", "config/mcp_tools.json")
    return MCPRuntime(config_path)


def _invoke_capability(state: WorkflowState, capability: str, payload: dict) -> dict:
    try:
        runtime = _mcp_runtime(state)
    except Exception as exc:
        _add_error(state, "MCP_RUNTIME_INIT_FAILED", "Failed to initialize MCP runtime.", str(exc))
        _add_tool_audit(state, capability, False)
        return {"ok": False, "error": {"code": "MCP_RUNTIME_INIT_FAILED", "message": "MCP runtime unavailable."}}
    result = runtime.invoke_capability(capability, payload)
    if not result.get("ok"):
        err = result.get("error", {})
        _add_error(state, err.get("code", "MCP_ERROR"), err.get("message", "MCP invocation failed."))
        _add_tool_audit(state, result.get("tool", capability), False)
        return result
    _add_tool_audit(state, result.get("tool", capability), True)
    return result


def mode_selector_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "mode_selector_node")
    state["status"] = "routing"

    if not _validate_input_invariants(state):
        _add_error(
            state,
            "ROUTER_INPUT_CONTRACT_VIOLATION",
            "Input mode and raw input do not satisfy invariants.",
        )
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    state["next_node"] = "validator_node" if state["input_mode"] == "manual" else "scriptwriter_node"
    return state


def validator_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "validator_node")
    state["status"] = "validating"

    script_text = (state["raw_input"]["script_text"] or "").strip()
    mcp_result = _invoke_capability(
        state,
        "manual_script_validation",
        {
            "script_text": script_text,
        },
    )
    if not mcp_result.get("ok"):
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    payload = mcp_result["result"]
    normalized = payload.get("script")
    validation_errors = payload.get("errors", [])
    for err in validation_errors:
        _add_error(state, err["code"], err["message"], err.get("details"))

    if validation_errors or normalized is None:
        state["status"] = "rejected"
        state["next_node"] = "rejected_node"
        return state

    state["script"] = normalized
    state["scenes"] = state["script"]["scenes"]
    state["status"] = "awaiting_hitl"
    state["next_node"] = "hitl_node"
    return state


def scriptwriter_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "scriptwriter_node")
    state["status"] = "generating"

    prompt = (state["raw_input"]["prompt"] or "").strip()
    if not prompt:
        _add_error(state, "SWRITER_EMPTY_PROMPT", "Prompt is empty for autonomous generation.")
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    if state.get("test_flags", {}).get("scriptwriter_tool_unavailable"):
        _add_error(state, "SWRITER_TOOL_UNAVAILABLE", "Script generation tool unavailable.")
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    mcp_result = _invoke_capability(
        state,
        "script_generation",
        {
            "prompt": prompt,
            "num_scenes": 3,
        },
    )
    if not mcp_result.get("ok"):
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    payload = mcp_result["result"]
    normalized = payload.get("script")
    generation_errors = payload.get("errors", [])
    for err in generation_errors:
        _add_error(state, err["code"], err["message"], err.get("details"))
    if generation_errors or normalized is None:
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    state["script"] = normalized
    state["scenes"] = state["script"]["scenes"]

    if not state["scenes"]:
        _add_error(state, "SWRITER_INCOHERENT_OUTPUT", "Generated script has no scenes.")
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    state["status"] = "awaiting_hitl"
    state["next_node"] = "hitl_node"
    return state


def hitl_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "hitl_node")

    if not state["scenes"]:
        _add_error(state, "HITL_EMPTY_SCENES", "HITL checkpoint reached without scenes.")
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    decision = state.get("hitl_decision", "approve")
    if decision == "approve":
        state["status"] = "approved"
        state["next_node"] = "character_node"
        return state

    if decision == "revise":
        state["status"] = "revised"
        state["revision_count"] = state.get("revision_count", 0) + 1
        if state["revision_count"] > state.get("max_revisions", 1):
            _add_error(state, "HITL_MAX_REVISIONS_EXCEEDED", "Revision limit exceeded.")
            state["status"] = "rejected"
            state["next_node"] = "rejected_node"
            return state
        state["next_node"] = "validator_node" if state["input_mode"] == "manual" else "scriptwriter_node"
        return state

    state["status"] = "rejected"
    state["next_node"] = "rejected_node"
    return state


def character_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "character_node")
    state["status"] = "characterizing"

    profiles, extraction_errors = extract_character_profiles(state["scenes"])
    for err in extraction_errors:
        _add_error(state, err["code"], err["message"], err.get("details"))

    if extraction_errors:
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    consistency_errors = verify_identity_consistency(state["scenes"], profiles)
    for err in consistency_errors:
        _add_error(state, err["code"], err["message"], err.get("details"))

    if consistency_errors:
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    stock_result = _invoke_capability(
        state,
        "stock_footage_query",
        {
            "characters": profiles,
            "prompt": state["script"].get("logline", ""),
        },
    )
    if not stock_result.get("ok"):
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    references = stock_result["result"].get("references", [])
    for profile, reference in zip(profiles, references, strict=False):
        profile["stock_footage_ref"] = reference

    state["characters"] = profiles

    state["next_node"] = "image_node"
    return state


def image_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "image_node")
    state["status"] = "imaging"

    if state.get("test_flags", {}).get("image_tool_unavailable"):
        _add_error(state, "IMG_TOOL_UNAVAILABLE", "Image synthesis tool unavailable.")
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    base_output = state.get("test_flags", {}).get("output_dir", "output")
    image_dir = Path(base_output) / "image_assets"
    mcp_result = _invoke_capability(
        state,
        "image_synthesis",
        {
            "characters": state["characters"],
            "output_dir": image_dir.as_posix(),
        },
    )
    if not mcp_result.get("ok"):
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    payload = mcp_result["result"]
    images = payload.get("images", [])
    image_errors = payload.get("errors", [])
    for err in image_errors:
        _add_error(state, err["code"], err["message"], err.get("details"))

    if image_errors:
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    state.setdefault("artifacts", {})["images_dir"] = image_dir.as_posix()

    try:
        db_path = write_character_db(state["request_id"], state["characters"], base_output)
        state["artifacts"]["character_db"] = db_path
        manifest_path = write_scene_manifest(state["request_id"], state["input_mode"], state["script"], base_output)
        state["artifacts"]["scene_manifest"] = manifest_path
    except Exception as exc:
        _add_error(state, "IMG_ASSET_WRITE_FAILED", "Failed to write character DB artifact.", str(exc))
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    state["images"] = images
    state["next_node"] = "memory_commit_node"
    return state


def memory_commit_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "memory_commit_node")
    state["status"] = "memory_commit"

    base_output = state.get("test_flags", {}).get("output_dir", "output")
    memory_dir = Path(base_output) / "memory"
    mcp_result = _invoke_capability(
        state,
        "memory_commit",
        {
            "request_id": state["request_id"],
            "script": state["script"],
            "characters": state["characters"],
            "images": state["images"],
            "memory_dir": memory_dir.as_posix(),
        },
    )
    if not mcp_result.get("ok"):
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    try:
        refs = mcp_result["result"]["memory_refs"]
        state["memory_refs"]["script_history_ids"] = refs.get("script_history_ids", [])
        state["memory_refs"]["character_memory_ids"] = refs.get("character_memory_ids", [])
        state["memory_refs"]["image_memory_ids"] = refs.get("image_memory_ids", [])
        state.setdefault("artifacts", {})["memory_dir"] = memory_dir.as_posix()
    except Exception as exc:  # pragma: no cover
        _add_error(state, "MEM_INDEX_FAILURE", "Invalid memory response payload.", str(exc))
        state["status"] = "failed"
        state["next_node"] = "failed_node"
        return state

    state["status"] = "completed"
    state["next_node"] = "end"
    return state


def rejected_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "rejected_node")
    state["status"] = "rejected"
    return state


def failed_node(state: WorkflowState) -> WorkflowState:
    _add_node_audit(state, "failed_node")
    state["status"] = "failed"
    return state


def route_from_mode_selector(state: WorkflowState) -> str:
    mapping = {
        "validator_node": "validator_node",
        "scriptwriter_node": "scriptwriter_node",
        "failed_node": "failed_node",
    }
    return mapping.get(state.get("next_node", "failed_node"), "failed_node")


def route_after_generation_or_validation(state: WorkflowState) -> str:
    if state.get("next_node") == "hitl_node":
        return "hitl_node"
    if state.get("next_node") == "rejected_node":
        return "rejected_node"
    return "failed_node"


def route_after_hitl(state: WorkflowState) -> str:
    nxt = state.get("next_node")
    if nxt == "character_node":
        return "character_node"
    if nxt in ("validator_node", "scriptwriter_node"):
        return nxt
    if nxt == "rejected_node":
        return "rejected_node"
    return "failed_node"


def route_after_linear_step(state: WorkflowState) -> str:
    nxt = state.get("next_node")
    if nxt == "image_node":
        return "image_node"
    if nxt == "memory_commit_node":
        return "memory_commit_node"
    if nxt == "end":
        return "end"
    return "failed_node"
