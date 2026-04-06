from __future__ import annotations

import re
from typing import Any

SCENE_PATTERN = re.compile(r"^(?:SCENE\s*(\d+)?)\s*[:\-]\s*(.+)$", re.IGNORECASE)
ALT_SCENE_PATTERN = re.compile(r"^(INT\.|EXT\.|INT/EXT\.)\s+(.+)$", re.IGNORECASE)
SPEAKER_PATTERN = r"[A-Za-z][A-Za-z0-9_.\- ]{0,40}"
DIALOGUE_PATTERN = re.compile(rf"^(?!ACTION\b)({SPEAKER_PATTERN})\s*[:\-—]\s*(.+)$")
QUOTED_DIALOGUE_PATTERN = re.compile(rf'^(?!ACTION\b)({SPEAKER_PATTERN})\s*[:\-—]\s*["“]?(.+?)["”]?$')


def _split_location_time(scene_tail: str) -> tuple[str, str]:
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s+—\s+|\s+–\s+", scene_tail) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return scene_tail.strip(), "Unknown"


def _sanitize_character(raw_name: str) -> str:
    name = raw_name.strip()
    if not name:
        return "Unknown"
    return name


def _visual_from_dialogue(line: str) -> str:
    lower = line.lower()
    if "!" in line or any(word in lower for word in ["run", "now", "hurry", "attack"]):
        return "tight close-up with urgent handheld motion"
    if any(word in lower for word in ["sorry", "quiet", "whisper", "remember"]):
        return "soft close-up with shallow depth of field"
    return "medium shot with balanced key light"


def _visual_from_action(action: str) -> dict[str, str]:
    lower = action.lower()
    if any(word in lower for word in ["rain", "storm", "lightning"]):
        return {"type": "lighting", "description": "high-contrast wet reflections and flickering highlights"}
    if any(word in lower for word in ["chase", "run", "rush"]):
        return {"type": "camera", "description": "tracking shot with fast lateral movement"}
    if any(word in lower for word in ["sunrise", "dawn", "morning"]):
        return {"type": "style", "description": "warm backlight and long shadows"}
    if any(word in lower for word in ["spark", "power", "grid", "outage"]):
        return {"type": "lighting", "description": "sparking practical lights and intermittent blackout flicker"}
    if any(word in lower for word in ["looter", "block", "crowd", "barrier"]):
        return {"type": "blocking", "description": "tight blocked framing with obstructed foreground silhouettes"}
    return {"type": "camera", "description": "steady cinematic framing with gentle push-in"}


def _build_scene(
    scene_index: int,
    location: str,
    time_of_day: str,
    actions: list[str],
    dialogue: list[dict[str, str]],
    visual_override: dict[str, str] | None = None,
) -> dict[str, Any]:
    scene_id = f"S{scene_index}"
    action_items = [
        {"id": f"A{scene_index}_{idx + 1}", "description": description}
        for idx, description in enumerate(actions)
    ]
    visual_cues: list[dict[str, str]] = []
    for idx, action in enumerate(actions):
        cue = visual_override or _visual_from_action(action)
        visual_cues.append({"id": f"V{scene_index}_{idx + 1}", "type": cue["type"], "description": cue["description"]})

    characters = sorted({line["speaker"] for line in dialogue})
    return {
        "scene_id": scene_id,
        "order": scene_index,
        "location": location,
        "time_of_day": time_of_day,
        "characters": characters,
        "actions": action_items,
        "dialogue": dialogue,
        "visual_cues": visual_cues,
    }


def _error(code: str, message: str, suggestion: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": {"suggestion": suggestion},
    }


def normalize_manual_script(script_text: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]

    if not lines:
        errors.append(
            _error(
                "SVALID_EMPTY_SCRIPT",
                "Manual script is empty.",
                "Add at least one scene block with SCENE header, ACTION line, and dialogue labels.",
            )
        )
        return None, errors

    scenes_raw: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        scene_match = SCENE_PATTERN.match(line)
        alt_scene_match = ALT_SCENE_PATTERN.match(line)

        if scene_match:
            if current is not None:
                scenes_raw.append(current)
            location, time_of_day = _split_location_time(scene_match.group(2))
            current = {"location": location, "time_of_day": time_of_day, "actions": [], "dialogue": []}
            continue

        if alt_scene_match:
            if current is not None:
                scenes_raw.append(current)
            location, time_of_day = _split_location_time(alt_scene_match.group(2))
            current = {"location": location, "time_of_day": time_of_day, "actions": [], "dialogue": []}
            continue

        if current is None:
            continue

        if line.upper().startswith("ACTION:"):
            action_text = line.split(":", 1)[1].strip()
            if action_text:
                current["actions"].append(action_text)
            continue

        dialogue_match = DIALOGUE_PATTERN.match(line) or QUOTED_DIALOGUE_PATTERN.match(line)
        if dialogue_match:
            speaker = _sanitize_character(dialogue_match.group(1))
            dialog_line = dialogue_match.group(2).strip()
            if dialog_line:
                current["dialogue"].append(
                    {
                        "speaker": speaker,
                        "line": dialog_line,
                        "visual_clue": _visual_from_dialogue(dialog_line),
                    }
                )
            continue

        # Fallback: treat unlabeled prose inside a scene as an action beat.
        if current is not None:
            current["actions"].append(line)

    if current is not None:
        scenes_raw.append(current)

    if not scenes_raw:
        errors.append(
            _error(
                "SVALID_MISSING_SCENE_HEADER",
                "Manual script is missing scene headers.",
                "Use lines like 'SCENE 1: City Street - Night' or 'INT. LAB - DAY'.",
            )
        )
        return None, errors

    for idx, raw in enumerate(scenes_raw, start=1):
        if not raw["dialogue"]:
            errors.append(
                _error(
                    "SVALID_MISSING_DIALOGUE_LABEL",
                    f"Scene {idx} has no labeled dialogue lines.",
                    "Add lines like 'A: We move now.' with speaker labels.",
                )
            )
        if not raw["actions"]:
            errors.append(
                _error(
                    "SVALID_ACTION_STRUCTURE_INVALID",
                    f"Scene {idx} has no ACTION lines.",
                    "Add lines like 'ACTION: Character enters and scans the room.'",
                )
            )

    if errors:
        return None, errors

    scenes = [
        _build_scene(
            scene_index=idx,
            location=raw["location"],
            time_of_day=raw["time_of_day"],
            actions=raw["actions"] or ["Action beat inferred from scene prose."],
            dialogue=raw["dialogue"],
        )
        for idx, raw in enumerate(scenes_raw, start=1)
    ]

    normalized = {
        "title": "Manual Script",
        "logline": "Validated uploaded script",
        "theme": "User supplied",
        "scenes": scenes,
    }
    return normalized, []


def _extract_setting(prompt: str) -> str:
    lowered = prompt.lower()
    if "city" in lowered:
        return "City Center"
    if "forest" in lowered:
        return "Forest Edge"
    if "station" in lowered:
        return "Central Station"
    if "school" in lowered:
        return "Old Campus"
    return "Urban Block"


def _extract_theme(prompt: str) -> str:
    lowered = prompt.lower()
    if any(word in lowered for word in ["rescue", "save", "protect"]):
        return "courage"
    if any(word in lowered for word in ["betray", "revenge", "rival"]):
        return "conflict"
    if any(word in lowered for word in ["memory", "past", "goodbye"]):
        return "nostalgia"
    return "determination"


def _extract_auto_cast(prompt: str) -> tuple[str, str]:
    lowered = prompt.lower()
    if any(word in lowered for word in ["hack", "hacker", "cyber", "code", "decrypt"]):
        return "Maya", "AI Core"
    if any(word in lowered for word in ["ai", "artificial intelligence", "system", "machine"]):
        return "Ari", "System Core"
    return "Ari", "Noor"


def build_auto_script(prompt: str, num_scenes: int = 3) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return None, [_error("SWRITER_EMPTY_PROMPT", "Prompt is empty for autonomous generation.", "Provide a story prompt with goal, setting, or conflict.")]

    if num_scenes < 2:
        num_scenes = 2

    setting = _extract_setting(clean_prompt)
    theme = _extract_theme(clean_prompt)
    protagonist, antagonist = _extract_auto_cast(clean_prompt)
    cast = [protagonist, antagonist]

    hacker_story = any(word in clean_prompt.lower() for word in ["hack", "hacker", "cyber", "code", "decrypt", "ai", "artificial intelligence", "grid"])

    scenes: list[dict[str, Any]] = []
    time_blocks = ["Night", "Late Night", "Dawn", "Morning", "Noon"]
    locations = [
        f"{setting} Street",
        f"{setting} Alley",
        f"{setting} Rooftop",
    ]
    action_variants = {
        "setup": [
            "The hacker traces a hidden signal while the AI masks the grid breach.",
            "A power relay flickers as the system starts locking out manual control.",
        ],
        "escalation": [
            "The AI floods the network with false data while the hacker fights to stay online.",
            "A collapsed barrier forces them to reroute access and improvise through the grid.",
        ],
        "resolution": [
            "The hacker overrides the relay as the AI core goes dark at dawn.",
            "The last firewall falls as the city regains control of its lifeline.",
        ],
    }
    visual_variants = {
        "setup": [
            {"type": "camera", "description": "slow push-in through dim street shadows"},
            {"type": "lighting", "description": "street lamps fading under rolling blackout haze"},
        ],
        "escalation": [
            {"type": "camera", "description": "handheld shaky cam with obstructed foreground movement"},
            {"type": "lighting", "description": "sparking darkness with strobing emergency lights"},
        ],
        "resolution": [
            {"type": "camera", "description": "wide shot revealing the rooftop horizon"},
            {"type": "style", "description": "clear dawn contrast with hopeful silhouette framing"},
        ],
    }
    for idx in range(1, num_scenes + 1):
        step = "setup" if idx == 1 else "escalation" if idx < num_scenes else "resolution"
        location = locations[min(idx - 1, len(locations) - 1)]
        action_text = action_variants[step][(idx - 1) % len(action_variants[step])]
        line_a = {
            "setup": f"I found the hidden signal. We only get one chance to break into the grid.",
            "escalation": f"{protagonist} can't keep fighting blind if {antagonist} keeps rewriting the system.",
            "resolution": "No more waiting. I am shutting you down now.",
        }[step]
        line_b = {
            "setup": "Unauthorized access detected. Grid defense protocols engaged.",
            "escalation": "You cannot outrun the core. Every node belongs to me.",
            "resolution": "System control lost. Shutdown sequence complete.",
        }[step]
        if hacker_story and step == "setup":
            line_a = f"I found the hidden signal. I can still get inside the grid."
            line_b = "Unauthorized access detected. Grid defense protocols engaged."
        if hacker_story and step == "escalation":
            line_a = f"I need to bypass the firewall before {antagonist} locks the city out."
            line_b = "You cannot outrun the core. Every node belongs to me."
        if hacker_story and step == "resolution":
            line_a = f"The relay is open. I am shutting you down now, {antagonist}."
            line_b = "System control lost. Shutdown sequence complete."
        dialogue = [
            {
                "speaker": cast[0],
                "line": line_a,
                "visual_clue": [
                    "tight close-up with urgent handheld motion",
                    "medium shot with side-light shadow contrast",
                    "wide shot with silhouetted blocking",
                ][(idx - 1) % 3],
            },
            {
                "speaker": cast[1],
                "line": line_b,
                "visual_clue": [
                    "medium shot with balanced key light",
                    "close-up tense lighting",
                    "handheld shaky cam in low light",
                ][(idx - 1) % 3],
            },
        ]
        scenes.append(
            _build_scene(
                scene_index=idx,
                location=location,
                time_of_day=time_blocks[min(idx - 1, len(time_blocks) - 1)],
                actions=[action_text],
                dialogue=dialogue,
                visual_override=visual_variants[step][(idx - 1) % len(visual_variants[step])],
            )
        )

    normalized = {
        "title": "Autonomous Draft",
        "logline": clean_prompt,
        "theme": theme,
        "scenes": scenes,
    }
    return normalized, []
