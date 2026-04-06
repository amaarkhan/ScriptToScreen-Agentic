from __future__ import annotations

from .state import empty_state
from .workflow import build_phase1_graph


def run_demo_auto() -> dict:
    app = build_phase1_graph()
    initial_state = empty_state(
        request_id="demo-auto-001",
        input_mode="auto",
        prompt="Two rivals become allies during a city blackout.",
        script_text=None,
    )
    initial_state["hitl_decision"] = "approve"
    return app.invoke(initial_state)


def run_demo_manual() -> dict:
    app = build_phase1_graph()
    initial_state = empty_state(
        request_id="demo-manual-001",
        input_mode="manual",
        prompt=None,
        script_text="""SCENE 1: CITY STREET
ACTION: Rain starts falling.
A: We move now.
B: I am with you.
""",
    )
    initial_state["hitl_decision"] = "approve"
    return app.invoke(initial_state)


if __name__ == "__main__":
    print(run_demo_auto()["status"])
    print(run_demo_manual()["status"])
