from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.as_posix() not in sys.path:
    sys.path.insert(0, SRC.as_posix())

from phase1.orchestration.state import empty_state
from phase1.orchestration.workflow import build_phase1_graph


def run_case(case_name: str, state: dict) -> dict:
    app = build_phase1_graph()
    result = app.invoke(state)
    print(f"{case_name}: status={result['status']}")
    print(f"  scene_manifest={result.get('artifacts', {}).get('scene_manifest', 'NA')}")
    print(f"  character_db={result.get('artifacts', {}).get('character_db', 'NA')}")
    print(f"  images_dir={result.get('artifacts', {}).get('images_dir', 'NA')}")
    print(f"  memory_dir={result.get('artifacts', {}).get('memory_dir', 'NA')}")
    return result


def main() -> None:
    root = Path("output/acceptance")

    # 🔥 NEW AUTO TEST (Adventure in Space)
    auto_state = empty_state(
        request_id="accept-auto-004",
        input_mode="auto",
        prompt=(
            "A crew of astronauts lands on an uncharted planet, only to discover "
            "a mysterious alien artifact that seems to alter reality around them. "
            "They must figure out its purpose before their ship is trapped forever."
        ),
        script_text=None,
    )
    auto_state["hitl_decision"] = "approve"
    auto_state["test_flags"] = {"output_dir": (root / "auto_v4").as_posix()}

    # 🔥 NEW MANUAL TEST (User Script: Haunted Mansion)
    manual_state = empty_state(
        request_id="accept-manual-004",
        input_mode="manual",
        prompt=None,
        script_text="""SCENE 1: Mansion Foyer - Night
ACTION: The door creaks as the group enters the dark foyer.
Lara: This place gives me the chills.
Jonas: Keep your eyes open.

SCENE 2: Grand Hall - Night
ACTION: Shadows flicker as chandeliers sway with a gust of wind.
Lara: Did you hear that whisper?
Jonas: Just the wind... I hope.

SCENE 3: Attic - Midnight
ACTION: Dust swirls as an old chest rattles on its own.
Lara: The chest... it's moving!
Jonas: Run!
""",
    )
    manual_state["hitl_decision"] = "approve"
    manual_state["test_flags"] = {"output_dir": (root / "manual_v4").as_posix()}

    auto_result = run_case("AUTO_V4", auto_state)
    manual_result = run_case("MANUAL_V4", manual_state)

    if auto_result["status"] != "completed" or manual_result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()