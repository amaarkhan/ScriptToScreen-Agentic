# Deliverable 1: Phase 2 System Specification and Contracts

Status: Frozen for implementation
Phase: PROJECT MONTAGE - Phase 2 (The Studio Floor)
Date: 2026-04-05

## 1) Purpose and Scope
This document freezes the architecture and interface contracts for Phase 2 before coding.
It defines:
- Input contract from Phase 1 `scene_manifest.json`
- Parallel audio/video execution architecture
- LangGraph `Send()`-based branching design
- Scene Parser, Voice Synthesis, Video Generation, Face Swap, and Lip Sync agent boundaries
- Shared state contract for tasks, media jobs, synchronization, memory, and errors
- MCP tool discovery policy and runtime invocation constraints
- Output artifact contracts for `.wav`, frame sequences, MP4 scene renders, and task graph logs
- Fault tolerance and resumability requirements
- Traceability from requirements to implementation items

Out of scope:
- Model-specific tuning
- Runtime implementation details
- Performance benchmarking

## 2) High-Level Architecture (Aligned to Diagram)
Flow:
1. Input: `scene_manifest.json` from Phase 1
2. Scene Parser Agent: convert scenes into executable tasks
3. Task Graph Generation: create scene-level task graph via MCP
4. Parallel branches:
- Audio pipeline: Voice Synthesis Agent
- Video pipeline: Video Generation Agent -> Face Swap Agent
5. Convergence: Lip Sync Agent aligns audio waveform and facial motion
6. Output: `raw_scenes/*.mp4` plus audio tracks, frame sequences, and logs

Pipeline topology:
- Entry: scene manifest
- Parser -> task graph -> parallel Send() branches
- Audio branch and video branch execute concurrently
- Face-swap/video outputs merge with audio at Lip Sync Agent
- Memory commit persists intermediate and final artifacts for recovery

## 3) Architectural Design Principles
### 3.1 Parallel Processing Architecture
This phase runs the audio and video branches in parallel.
Each scene is treated as an independent unit that can be processed concurrently.
The LangGraph workflow should use `Send()` to dispatch scene tasks to branch-specific nodes.

### 3.2 Task Graph-based Execution
All scene execution must be derived from a task graph.
Each scene becomes:
- an independent workload unit
- a resumable execution record
- a synchronization boundary for later merge

The task graph is generated through MCP tooling and stored as structured logs.

### 3.3 Stateful Resumability
The system must save intermediate outputs so that interrupted or failed runs can resume.
Persistent memory must store:
- parsed scene tasks
- audio jobs and artifacts
- video jobs and frame outputs
- face swap and identity validation results
- synchronization state and final render progress

## 4) System Objectives
The primary goal of Phase 2 is to produce:
- `raw_scenes/*.mp4` -> final synchronized audiovisual scenes
- audio `.wav` tracks
- intermediate frame sequences
- task graph logs

Additionally, the phase ensures:
- compatibility with downstream editing/compositing stages
- frame-accurate lip synchronization
- parallel throughput across scenes
- support for recovery after partial failure

## 5) Multi-Agent Collaboration Model
This phase follows a parallel worker model coordinated by LangGraph routing.

Coordinator role:
- Scene Parser Agent is the logical entry point
- LangGraph controls routing and branching
- The graph merges work at the Lip Sync Agent

Worker agents:
1. Scene Parser Agent
- Role: transform `scene_manifest.json` into executable tasks
- Responsibilities: scene segmentation, task distribution, parallel routing, task graph creation

2. Voice Synthesis Agent
- Role: generate speech aligned with character identity
- Responsibilities: dialogue-to-speech mapping, emotion-aware synthesis, voice cloning selection

3. Video Generation Agent
- Role: generate visual scene content from descriptions and character references
- Responsibilities: visual cue interpretation, environment generation, frame production

4. Face Swap Agent
- Role: map generated characters onto video frames
- Responsibilities: identity validation, face mapping, frame-level alignment preparation

5. Lip Sync Agent
- Role: synchronize speech waveform with facial movement
- Responsibilities: temporal alignment, frame-to-audio synchronization, final merge

## 6) MCP-based Tool Discovery Constraint
A strict constraint is enforced:
- All tools must be discovered dynamically via MCP
- No hardcoded APIs or direct provider calls in orchestration logic

Thus:
- Agents query MCP registry at runtime
- Tools are invoked via structured schemas
- Tool payloads must be validated before execution

### Required MCP Tools
- `get_task_graph`
- `commit_memory`
- `voice_cloning_synthesizer`
- `query_stock_footage`
- `face_swapper`
- `identity_validator`
- `lip_sync_aligner`

Example payload:
```json
{
  "tool": "voice_cloning_synthesizer",
  "input": {
    "speaker": "Ari",
    "dialogue": "We have one shot.",
    "emotion": "tense"
  }
}
```

## 7) Stateful Memory System
All agents interact with a persistent memory layer.
The memory layer stores:
- task graph state
- scene execution checkpoints
- audio generation records
- video generation records
- face swap and sync state
- artifact references

This directly supports:
- continuity across scenes
- recovery from failure
- resuming interrupted runs

## 8) LangGraph Workflow Design
LangGraph uses `Send()` for branching.

Nodes:
- `Scene_parser_node`
- `Voice_synth_node`
- `Video_gen_node`
- `Face_swap_node`
- `Lip_sync_node`

Routing requirement:
- Scene parser dispatches per-scene work into parallel audio/video branches
- Branches run concurrently per scene
- Convergence occurs at lip sync once branch outputs are available

## 9) Shared State Contract
Canonical state object:

```json
{
  "request_id": "string",
  "input_manifest": {
    "path": "string",
    "scene_count": 0
  },
  "scenes": [],
  "tasks": [],
  "task_graph": {},
  "audio_jobs": [],
  "video_jobs": [],
  "face_swap_jobs": [],
  "sync_jobs": [],
  "artifacts": {
    "audio_tracks": [],
    "frame_sequences": [],
    "video_scenes": [],
    "raw_scenes": [],
    "task_graph_logs": []
  },
  "memory_refs": {
    "task_graph_ids": [],
    "audio_memory_ids": [],
    "video_memory_ids": [],
    "sync_memory_ids": []
  },
  "status": "received | parsing | graphing | branching | processing_audio | processing_video | face_swapping | syncing | completed | failed | resumed",
  "errors": [],
  "audit": {
    "tool_calls": [],
    "node_history": [],
    "branch_history": []
  }
}
```

State invariants:
- A valid `scene_manifest.json` must be present before parsing starts
- Each scene must produce a task graph entry
- Audio and video branches may run independently but must reconcile in lip sync
- `raw_scenes/*.mp4` is only emitted after sync completion
- errors must always carry code and message

## 10) Agent Interface Contracts

### 10.1 Scene Parser Agent
Input:
- request_id
- input_manifest.path
- input_manifest.scene_count
- scene_manifest payload

Output:
- `scenes` normalized for execution
- `tasks` with per-scene task items
- `task_graph`
- status transition candidate: parsing -> graphing

Failure codes:
- SPARSE_INVALID_MANIFEST
- SPARSE_EMPTY_SCENES
- SPARSE_TASK_GRAPH_FAILED

### 10.2 Voice Synthesis Agent
Input:
- task items for dialogue
- character voice profile references
- emotional / timing metadata

Output:
- `.wav` audio tracks
- audio job metadata
- status transition candidate: processing_audio -> synced-ready

Failure codes:
- VOICE_SYNTH_FAILED
- VOICE_PROFILE_MISSING
- VOICE_AUDIO_WRITE_FAILED

### 10.3 Video Generation Agent
Input:
- task items for scene visuals
- visual cues
- character references
- environment description

Output:
- intermediate frame sequences
- generated scene visuals
- status transition candidate: processing_video -> face_swapping

Failure codes:
- VIDEO_GEN_FAILED
- VIDEO_FRAME_WRITE_FAILED
- VIDEO_REFERENCE_MISSING

### 10.4 Face Swap Agent
Input:
- generated frames
- identity references
- character mapping data

Output:
- face-mapped frames
- identity validation records
- status transition candidate: face_swapping -> syncing

Failure codes:
- FACE_SWAP_FAILED
- IDENTITY_VALIDATION_FAILED
- FACE_MISSING_REFERENCE

### 10.5 Lip Sync Agent
Input:
- audio waveform
- face-mapped frames
- timing metadata

Output:
- synchronized scene MP4
- lip-sync metadata
- status transition candidate: syncing -> completed

Failure codes:
- LIPSYNC_FAILED
- TEMPORAL_ALIGNMENT_FAILED
- FINAL_RENDER_FAILED

## 11) Output Contracts
Required artifacts:
- `raw_scenes/*.mp4`
- `audio/*.wav`
- `frames/<scene_id>/*.png`
- `task_graph_logs/*.json`

The canonical JSON Schemas are defined in:
- `contracts/schemas/phase2_state.schema.json`
- `contracts/schemas/phase2_task_graph.schema.json`
- `contracts/schemas/phase2_artifacts.schema.json`

Compatibility requirements:
- artifact names must be deterministic per scene
- partial artifacts must remain available for resumability
- final scene MP4s must map back to the originating scene IDs

## 12) Downstream Compatibility Contract
Phase 2 outputs must satisfy downstream editing and publication workflows:
- each MP4 must represent a single scene or clearly labeled scene chunk
- each `.wav` must align to the corresponding dialogue payload
- frame sequences must preserve ordering and timestamps
- task graph logs must provide traceability for debugging and recovery

## 13) Fault Tolerance and Resumability
The system must support:
- recovery after agent failure
- resuming from completed scene checkpoints
- skipping completed task graph nodes on retry
- preserving intermediate artifacts in memory and on disk

Required behavior:
- commit state after major stages
- do not overwrite valid artifacts unless explicitly re-rendering
- log each resume decision in the audit trail

## 14) Definition of Done for Deliverable 1
Deliverable 1 is complete when:
- architecture is documented and aligned to the diagram
- agent boundaries and interfaces are unambiguous
- state contract is frozen and machine-readable
- MCP dynamic-discovery-only policy is documented
- output schemas exist and cover all required artifacts
- resumability and fault tolerance are specified
- each requirement is traceable to implementation work items

## 15) Traceability Matrix (Requirement -> Implementation Item)
| Requirement | Contract Section | Planned Implementation Item |
|---|---|---|
| scene_manifest.json input | Sections 1, 2, 9 | Scene parser node |
| Parallel audio/video branches | Sections 3.1, 8 | LangGraph Send() routing |
| Task graph generation | Sections 3.2, 6 | MCP task graph node |
| Stateful resumability | Sections 3.3, 7, 13 | Memory commit and checkpointing |
| Voice synthesis | Section 10.2 | Voice synth node |
| Video generation | Section 10.3 | Video gen node |
| Face swap | Section 10.4 | Face swap node |
| Lip sync | Section 10.5 | Lip sync node |
| Raw MP4/audio/frame outputs | Section 11 | Artifact writer modules |
| MCP integration | Section 6 | MCP runtime client and schemas |

## 16) Versioning
- Contract version: 1.0.0
- Effective date: 2026-04-05
- Change policy: breaking changes require a new contract version and migration notes
