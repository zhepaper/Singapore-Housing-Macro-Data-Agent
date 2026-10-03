from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from housing_agent.report_generation.composer import compose_report
from housing_agent.report_generation.models import ReportContext, ReportVerification
from housing_agent.report_generation.prompt import build_prompt
from housing_agent.report_generation.verification import verify_report
from housing_agent.report_generation.writer import ReportWriter


class Stage4GraphState(TypedDict, total=False):
    context: ReportContext
    writer: ReportWriter
    max_attempts: int
    attempt: int
    feedback: tuple[str, ...]
    prompt_text: str
    prompt_history: list[str]
    narrative: str
    report: str
    verification: ReportVerification
    writer_history: list[dict[str, Any]]


def writer_node(state: Stage4GraphState) -> Stage4GraphState:
    context = state["context"]
    attempt = state.get("attempt", 0) + 1
    feedback = state.get("feedback", ())
    system_prompt, human_prompt = build_prompt(context, feedback)
    prompt_text = f"SYSTEM\n{system_prompt}\n\nUSER\n{human_prompt}\n"
    output = state["writer"].write(
        context,
        attempt=attempt,
        feedback=feedback,
    )
    history = [*state.get("writer_history", [])]
    history.append(output.model_dump(mode="json", exclude={"narrative"}))
    prompt_history = [*state.get("prompt_history", []), prompt_text]
    return {
        "attempt": attempt,
        "prompt_text": prompt_text,
        "narrative": output.narrative,
        "prompt_history": prompt_history,
        "writer_history": history,
    }


def compose_node(state: Stage4GraphState) -> Stage4GraphState:
    return {"report": compose_report(state["context"], state["narrative"])}


def verification_node(state: Stage4GraphState) -> Stage4GraphState:
    result = verify_report(state["report"], state["context"])
    return {"verification": result, "feedback": result.errors}


def route_after_verification(state: Stage4GraphState) -> str:
    if state["verification"].status == "pass":
        return "complete"
    if state.get("attempt", 0) < state["max_attempts"]:
        return "revise"
    return "blocked"


def build_stage4_graph():
    graph = StateGraph(Stage4GraphState)
    graph.add_node("writer", writer_node)
    graph.add_node("compose", compose_node)
    graph.add_node("verify", verification_node)
    graph.add_edge(START, "writer")
    graph.add_edge("writer", "compose")
    graph.add_edge("compose", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verification,
        {"complete": END, "revise": "writer", "blocked": END},
    )
    return graph.compile()
