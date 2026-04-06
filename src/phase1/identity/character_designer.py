from __future__ import annotations

import hashlib
from typing import Any


_BUILD_TYPES = ["lean", "athletic", "average", "broad"]
_HAIR_TYPES = ["short dark", "curly black", "wavy brown", "buzz cut", "long tied"]
_FACE_TYPES = ["sharp jawline", "round face", "high cheekbones", "soft features"]
_WARDROBE_TYPES = ["streetwear jacket", "utility coat", "formal blazer", "layered casual"]


def _name_seed(name: str) -> int:
    return int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)


def _derive_traits(dialogue_lines: list[str]) -> list[str]:
    text = " ".join(dialogue_lines).lower()
    traits: set[str] = set()
    if any(word in text for word in ["now", "move", "hurry", "act"]):
        traits.add("decisive")
    if any(word in text for word in ["together", "trust", "with you"]):
        traits.add("loyal")
    if any(word in text for word in ["plan", "think", "careful", "wait"]):
        traits.add("strategic")
    if any(word in text for word in ["sorry", "remember", "past", "goodbye"]):
        traits.add("reflective")
    if not traits:
        traits = {"determined"}
    return sorted(traits)


def _derive_style(scenes: list[dict[str, Any]], name: str) -> str:
    joined = " ".join(
        cue.get("description", "")
        for scene in scenes
        for cue in scene.get("visual_cues", [])
        if name in scene.get("characters", [])
    ).lower()
    if "high-contrast" in joined or "hard" in joined:
        return "neo-noir cinematic"
    if "warm" in joined:
        return "natural warm drama"
    if "tracking" in joined:
        return "kinetic action realism"
    return "cinematic realistic"


def _appearance_for_name(name: str) -> dict[str, str]:
    seed = _name_seed(name)
    return {
        "age_range": "20-35",
        "build": _BUILD_TYPES[seed % len(_BUILD_TYPES)],
        "hair": _HAIR_TYPES[seed % len(_HAIR_TYPES)],
        "face": _FACE_TYPES[seed % len(_FACE_TYPES)],
        "wardrobe": _WARDROBE_TYPES[seed % len(_WARDROBE_TYPES)],
    }


def extract_character_profiles(scenes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not scenes:
        return [], [{"code": "CHAR_NO_SCENES", "message": "No scenes available for character extraction."}]

    dialogue_by_speaker: dict[str, list[str]] = {}
    appearances: dict[str, int] = {}

    for scene in scenes:
        for speaker in scene.get("characters", []):
            normalized = str(speaker).strip()
            if normalized:
                appearances[normalized] = appearances.get(normalized, 0) + 1
        for line in scene.get("dialogue", []):
            speaker = str(line.get("speaker", "")).strip()
            text = str(line.get("line", "")).strip()
            if not speaker:
                continue
            appearances[speaker] = appearances.get(speaker, 0) + 1
            dialogue_by_speaker.setdefault(speaker, []).append(text)

    characters = sorted(appearances.keys())
    if not characters:
        return [], [{"code": "CHAR_NO_CHARACTERS_FOUND", "message": "No characters were detected in scenes."}]

    profiles: list[dict[str, Any]] = []
    for idx, name in enumerate(characters, start=1):
        key = hashlib.sha256(name.lower().encode("utf-8")).hexdigest()[:16]
        profile = {
            "character_id": f"CHAR_{idx}",
            "name": name,
            "personality_traits": _derive_traits(dialogue_by_speaker.get(name, [])),
            "appearance": _appearance_for_name(name),
            "reference_style": _derive_style(scenes, name),
            "identity_consistency": {
                "embedding_key": f"emb_{key}",
                "version": "1",
                "continuity_score": min(1.0, appearances.get(name, 1) / max(1, len(scenes))),
            },
            "image_refs": [],
        }
        profiles.append(profile)

    return profiles, []


def verify_identity_consistency(scenes: list[dict[str, Any]], characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    by_name = {str(c.get("name", "")).strip().lower(): c for c in characters}

    if len(by_name) != len(characters):
        errors.append(
            {
                "code": "CHAR_IDENTITY_CONFLICT",
                "message": "Duplicate character identities detected.",
                "details": {"hint": "Ensure each character has a unique normalized name."},
            }
        )

    for scene in scenes:
        for line in scene.get("dialogue", []):
            speaker = str(line.get("speaker", "")).strip().lower()
            if speaker and speaker not in by_name:
                errors.append(
                    {
                        "code": "CHAR_IDENTITY_CONFLICT",
                        "message": "Dialogue speaker not present in character profiles.",
                        "details": {"speaker": line.get("speaker", "")},
                    }
                )

    return errors
