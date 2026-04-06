# Deliverable 1: Phase 1 System Specification and Contracts

Status: Frozen for implementation
Phase: PROJECT MONTAGE - Phase 1 (The Writer's Room)
Date: 2026-04-02

## 1) Purpose and Scope
This document freezes the architecture and interface contracts for Phase 1 before coding.
It defines:
- High-level architecture and flow
- Supervisor-worker agent model
- Shared LangGraph state contract
- Agent input/output interfaces
- MCP tool usage policy
- Output schema contracts
- Downstream compatibility contract
- Traceability from requirements to implementation items

Out of scope:
- Runtime implementation details
- Model-specific prompt engineering
- Performance benchmarking

## 2) High-Level Architecture (Aligned to Diagram)
Flow:
1. User Input: Prompt or script upload
2. Mode Selector: Decide manual validation flow vs autonomous generation flow
3. LangGraph Stateful Workflow: Route through appropriate agent nodes
4. Human-in-the-Loop (HITL): Approval/revision checkpoint
5. Character and Image Pipeline: Character Designer then Image Synthesizer
6. Memory Commit Layer: Persist script, character, and image references
7. Outputs: scene_manifest.json, character_db.json, Images/

Pipeline topology:
- Entry: User input
- Branch A (manual): Validator -> HITL
- Branch B (auto): Scriptwriter -> HITL
- Common continuation: Character Designer -> Image Synthesizer -> Memory Commit -> Output writer

## 3) Orchestration Model: Supervisor-Worker
Supervisor pattern:
- Supervisor is implicit in LangGraph routing logic.
- Supervisor responsibilities:
  - Node selection and branching
  - Transition gating (including HITL checkpoint)
  - Error routing and retry policy
  - Completion criteria enforcement

Worker agents:
1. Scriptwriter Agent
- Role: Expand prompt into coherent multi-scene screenplay
- Responsibilities: Scene segmentation, dialogue generation, visual cue injection, narrative continuity

2. Script Validator Agent
- Role: Validate manually uploaded scripts
- Responsibilities: Check scene headers, dialogue labels, action structure, normalization readiness

3. HITL Agent
- Role: User approval gate before downstream commit
- Responsibilities: Present generated/normalized script, capture approve/revise/reject action

4. Character Designer Agent
- Role: Extract and normalize persistent character identities
- Responsibilities: Traits, appearance, style references, identity consistency keys

5. Image Synthesizer Agent
- Role: Generate character reference visuals
- Responsibilities: Tool-driven image generation, asset linkage to character IDs

## 4) LangGraph State Contract
Canonical state object:

```json
{
  "request_id": "string",
  "input_mode": "manual | auto",
  "raw_input": {
    "prompt": "string | null",
    "script_text": "string | null"
  },
  "script": {
    "title": "string",
    "logline": "string",
    "theme": "string",
    "scenes": []
  },
  "scenes": [],
  "characters": [],
  "images": [],
  "memory_refs": {
    "script_history_ids": [],
    "character_memory_ids": [],
    "image_memory_ids": []
  },
  "status": "received | routing | validating | generating | awaiting_hitl | approved | revised | rejected | characterizing | imaging | memory_commit | completed | failed",
  "errors": [],
  "audit": {
    "tool_calls": [],
    "node_history": []
  }
}
```

State invariants:
- Exactly one input source is provided:
  - manual mode: script_text required, prompt null
  - auto mode: prompt required, script_text null
- scenes must be non-empty before HITL approval can finalize
- characters and images are optional before HITL, required before completed
- status must follow valid node transitions
- errors must include code and message for all failed transitions

## 5) Agent Interface Contracts

### 5.1 Scriptwriter Agent
Input:
- request_id
- input_mode=auto
- raw_input.prompt
- optional memory_refs.script_history_ids

Output:
- script.scenes (normalized structure)
- scenes (projection view)
- status transition candidate: generating -> awaiting_hitl
- optional warnings

Failure codes:
- SWRITER_EMPTY_PROMPT
- SWRITER_TOOL_UNAVAILABLE
- SWRITER_INCOHERENT_OUTPUT

### 5.2 Script Validator Agent
Input:
- request_id
- input_mode=manual
- raw_input.script_text

Output (success):
- normalized script/scenes
- status transition candidate: validating -> awaiting_hitl

Output (failure):
- errors with correction suggestions
- status transition candidate: validating -> rejected

Failure codes:
- SVALID_MISSING_SCENE_HEADER
- SVALID_MISSING_DIALOGUE_LABEL
- SVALID_ACTION_STRUCTURE_INVALID

### 5.3 HITL Agent
Input:
- current normalized scenes
- validation/generation notes

Output:
- user_decision: approve | revise | reject
- status transition:
  - approve: awaiting_hitl -> characterizing
  - revise: awaiting_hitl -> generating or validating (based on mode)
  - reject: awaiting_hitl -> rejected

### 5.4 Character Designer Agent
Input:
- approved scenes
- optional existing character memory refs

Output:
- characters[] normalized entries
- status transition candidate: characterizing -> imaging

Failure codes:
- CHAR_NO_CHARACTERS_FOUND
- CHAR_IDENTITY_CONFLICT

### 5.5 Image Synthesizer Agent
Input:
- characters[]
- style references

Output:
- images[] with character linkage
- status transition candidate: imaging -> memory_commit

Failure codes:
- IMG_TOOL_UNAVAILABLE
- IMG_GENERATION_FAILED
- IMG_ASSET_WRITE_FAILED

### 5.6 Memory Commit Layer
Input:
- script, characters, images
- prior memory refs

Output:
- updated memory_refs
- status transition candidate: memory_commit -> completed

Failure codes:
- MEM_PERSIST_FAILURE
- MEM_INDEX_FAILURE

## 6) MCP Tool Discovery and Invocation Policy (Mandatory)
Policy statement:
- All external capabilities must be discovered dynamically through MCP registry at runtime.
- No hardcoded vendor endpoints, SDK-specific direct calls, or static tool binding in agent logic.

Mandatory runtime sequence:
1. Query MCP tool registry by capability intent (e.g., script generation, image synthesis, memory commit).
2. Validate returned tool schema.
3. Invoke via structured MCP payload.
4. Log tool call metadata into state.audit.tool_calls.

Compliant invocation example:

```json
{
  "tool": "generate_script_segment",
  "input": {
    "prompt": "A tense rooftop confrontation at dawn",
    "num_scenes": 5
  }
}
```

Non-compliant examples:
- Direct REST URL calls from agent code
- Hardcoded function-to-provider mapping
- Tool invocation without schema validation

## 7) Output Contracts
Required artifacts:
1. scene_manifest.json
2. character_db.json
3. Images/ directory with character assets

The canonical JSON Schemas are defined in:
- contracts/schemas/scene_manifest.schema.json
- contracts/schemas/character_db.schema.json
- contracts/schemas/langgraph_state.schema.json

## 8) Downstream Compatibility Contract (Video/Audio)
Phase 1 outputs must satisfy downstream requirements:
- Stable scene IDs for shot planning and timeline assembly
- Dialogue entries with speaker attribution for TTS and dubbing alignment
- Visual cues and action descriptors for shot prompting and compositing
- Character IDs linked to reference images for identity continuity and face consistency
- Machine-readable timestamps/ordering fields for sequencing

Compatibility guarantees:
- JSON schema versioning is explicit and immutable per release
- Optional fields are additive only; no breaking renames
- Character IDs are persistent across scene revisions

## 9) Definition of Done for Deliverable 1
Deliverable 1 is complete when:
- Full architecture is documented and aligned with the high-level flow
- Agent boundaries and interfaces are unambiguous
- LangGraph state contract is frozen and machine-readable
- MCP dynamic-discovery-only policy is documented with compliant invocation pattern
- Output schemas exist and validate required artifacts
- Downstream contract is specified
- Each requirement is traceable to implementation work items

## 10) Traceability Matrix (Requirement -> Implementation Item)
| Requirement | Contract Section | Planned Implementation Item |
|---|---|---|
| User input -> mode selector -> workflow -> HITL -> character/image -> memory -> outputs | Section 2 | StateGraph routing and node edges |
| Supervisor-worker model | Section 3 | Router node + worker node modules |
| Shared state fields (input mode, script, scenes, characters, images, status, errors, memory refs) | Section 4 | Typed state model + validators |
| Scriptwriter contract | Section 5.1 | scriptwriter node executor |
| Validator contract | Section 5.2 | validator node executor |
| HITL checkpoint contract | Section 5.3 | hitl gate node + UI hook |
| Character Designer contract | Section 5.4 | character extraction node |
| Image Synthesizer contract | Section 5.5 | image generation node |
| Memory persistence contract | Section 5.6 | memory commit node |
| MCP dynamic discovery only | Section 6 | MCP registry client + schema guard |
| scene_manifest.json + character_db.json + Images/ | Section 7 | artifact writer module |
| Downstream video/audio compatibility | Section 8 | output adapter tests |

## 11) Versioning
- Contract version: 1.0.0
- Effective date: 2026-04-02
- Change policy: breaking changes require new minor/major contract version and migration notes
