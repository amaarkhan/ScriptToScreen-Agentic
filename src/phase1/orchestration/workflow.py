from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    character_node,
    failed_node,
    hitl_node,
    image_node,
    memory_commit_node,
    mode_selector_node,
    rejected_node,
    route_after_generation_or_validation,
    route_after_hitl,
    route_after_linear_step,
    route_from_mode_selector,
    scriptwriter_node,
    validator_node,
)
from .state import WorkflowState


def build_phase1_graph():
    graph_builder = StateGraph(WorkflowState)

    graph_builder.add_node("mode_selector_node", mode_selector_node)
    graph_builder.add_node("validator_node", validator_node)
    graph_builder.add_node("scriptwriter_node", scriptwriter_node)
    graph_builder.add_node("hitl_node", hitl_node)
    graph_builder.add_node("character_node", character_node)
    graph_builder.add_node("image_node", image_node)
    graph_builder.add_node("memory_commit_node", memory_commit_node)
    graph_builder.add_node("rejected_node", rejected_node)
    graph_builder.add_node("failed_node", failed_node)

    graph_builder.add_edge(START, "mode_selector_node")

    graph_builder.add_conditional_edges(
        "mode_selector_node",
        route_from_mode_selector,
        {
            "validator_node": "validator_node",
            "scriptwriter_node": "scriptwriter_node",
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_conditional_edges(
        "validator_node",
        route_after_generation_or_validation,
        {
            "hitl_node": "hitl_node",
            "rejected_node": "rejected_node",
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_conditional_edges(
        "scriptwriter_node",
        route_after_generation_or_validation,
        {
            "hitl_node": "hitl_node",
            "rejected_node": "rejected_node",
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_conditional_edges(
        "hitl_node",
        route_after_hitl,
        {
            "character_node": "character_node",
            "validator_node": "validator_node",
            "scriptwriter_node": "scriptwriter_node",
            "rejected_node": "rejected_node",
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_conditional_edges(
        "character_node",
        route_after_linear_step,
        {
            "image_node": "image_node",
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_conditional_edges(
        "image_node",
        route_after_linear_step,
        {
            "memory_commit_node": "memory_commit_node",
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_conditional_edges(
        "memory_commit_node",
        route_after_linear_step,
        {
            "end": END,
            "failed_node": "failed_node",
        },
    )

    graph_builder.add_edge("rejected_node", END)
    graph_builder.add_edge("failed_node", END)

    return graph_builder.compile()
