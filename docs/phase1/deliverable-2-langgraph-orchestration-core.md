# Deliverable 2: LangGraph Orchestration Core

Status: Implemented
Date: 2026-04-02

## Scope Implemented
- Stateful LangGraph orchestration with explicit node routing
- Dual-mode branch support (manual validator path and auto scriptwriter path)
- Shared state passing across all nodes
- HITL checkpoint with approve/revise/reject routing
- Failure paths for invalid manual scripts and tool failures
- Retry/revision control with max revision limit
- Deterministic status transitions and audit history logging

## Implemented Nodes
- mode_selector_node
- validator_node
- scriptwriter_node
- hitl_node
- character_node
- image_node
- memory_commit_node
- rejected_node
- failed_node

## Routing Guarantees
- Start -> mode_selector_node
- mode_selector_node -> validator_node or scriptwriter_node or failed_node
- validator_node/scriptwriter_node -> hitl_node or rejected_node or failed_node
- hitl_node -> character_node or rework node or rejected_node or failed_node
- character_node -> image_node or failed_node
- image_node -> memory_commit_node or failed_node
- memory_commit_node -> END or failed_node

## Shared State and Observability
- State shape matches Deliverable 1 contract fields
- Node history captured in audit.node_history
- Tool invocation audit captured in audit.tool_calls
- Error list stores code/message/details for failed transitions

## Test Coverage
- Auto mode happy path completes
- Manual invalid script path rejects with validation errors
- HITL revise over limit rejects
- Tool failure path transitions to failed

## Usage
Install dependencies:
- pip install -r requirements.txt

Run tests:
- pytest -q

Run demos:
- python -m phase1.orchestration.runner
