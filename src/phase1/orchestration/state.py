from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

InputMode = Literal["manual", "auto"]
Status = Literal[
    "received",
    "routing",
    "validating",
    "generating",
    "awaiting_hitl",
    "approved",
    "revised",
    "rejected",
    "characterizing",
    "imaging",
    "memory_commit",
    "completed",
    "failed",
]


class RawInput(TypedDict):
    prompt: str | None
    script_text: str | None


class MemoryRefs(TypedDict):
    script_history_ids: list[str]
    character_memory_ids: list[str]
    image_memory_ids: list[str]


class ErrorItem(TypedDict):
    code: str
    message: str
    details: NotRequired[Any]


class ToolCallAudit(TypedDict):
    tool: str
    status: Literal["success", "failure"]
    timestamp: str


class Audit(TypedDict):
    tool_calls: list[ToolCallAudit]
    node_history: list[str]


class WorkflowState(TypedDict):
    request_id: str
    input_mode: InputMode
    raw_input: RawInput
    script: dict[str, Any]
    scenes: list[dict[str, Any]]
    characters: list[dict[str, Any]]
    images: list[dict[str, Any]]
    memory_refs: MemoryRefs
    status: Status
    errors: list[ErrorItem]
    audit: Audit
    hitl_decision: NotRequired[Literal["approve", "revise", "reject"]]
    revision_count: NotRequired[int]
    max_revisions: NotRequired[int]
    next_node: NotRequired[str]
    test_flags: NotRequired[dict[str, Any]]
    artifacts: NotRequired[dict[str, str]]


def empty_state(request_id: str, input_mode: InputMode, prompt: str | None, script_text: str | None) -> WorkflowState:
    return {
        "request_id": request_id,
        "input_mode": input_mode,
        "raw_input": {"prompt": prompt, "script_text": script_text},
        "script": {"title": "", "logline": "", "theme": "", "scenes": []},
        "scenes": [],
        "characters": [],
        "images": [],
        "memory_refs": {
            "script_history_ids": [],
            "character_memory_ids": [],
            "image_memory_ids": [],
        },
        "status": "received",
        "errors": [],
        "audit": {"tool_calls": [], "node_history": []},
        "revision_count": 0,
        "max_revisions": 1,
        "artifacts": {},
    }
