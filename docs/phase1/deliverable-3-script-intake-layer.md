# Deliverable 3: Script Intake Layer (Manual + Autonomous)

Status: Implemented
Date: 2026-04-02

## Scope Implemented
- Manual script intake with structural validation and normalization
- Autonomous prompt-to-script generation with multi-scene coherent structure
- Unified standardized screenplay JSON output for both modes
- Validation failure handling with actionable correction suggestions

## Manual Mode Workflow
1. Accept uploaded script text
2. Validate required structure:
- Scene headers (SCENE n: ... or INT./EXT. ...)
- ACTION lines per scene
- Labeled dialogue lines (Speaker: line)
3. Return either:
- Rejected status with error codes + suggestion details
- Normalized script object in standard scene format

## Autonomous Mode Workflow
1. Accept prompt
2. Generate a multi-scene screenplay arc (setup -> escalation -> resolution)
3. Include dialogue and visual cues per scene
4. Return normalized script object in the same standard scene format used by manual mode

## Standard Output Shape (Both Modes)
Each scene includes:
- scene_id
- order
- location
- time_of_day
- characters
- actions
- dialogue (speaker, line, visual_clue)
- visual_cues

## Files Added/Updated
- src/phase1/intake/script_intake.py
- src/phase1/intake/__init__.py
- src/phase1/orchestration/nodes.py
- tests/test_phase1_workflow.py

## Validation and Tests
Covered by automated tests:
- Manual invalid script rejection with correction suggestions
- Manual valid script normalization and scene parsing
- Autonomous generation completion and standardized scene structure
- Contract shape parity between manual and autonomous scene outputs
