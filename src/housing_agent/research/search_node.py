from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

from housing_agent.memory.models import MemoryManifest, MemorySnapshot
from housing_agent.memory.compiler import memory_snapshot_sha256
from housing_agent.research.models import ApprovedResearchScope, ResearchProposal
from housing_agent.research.prompt import (
    RESEARCH_PROMPT_VERSION,
    SEARCH_AGENT_INSTRUCTIONS,
    build_search_input,
)
from housing_agent.research.providers import (
    ResearchClient,
    StructuredOutputError,
    canonical_provider,
    create_research_client,
    provider_spec,
)
from housing_agent.research.rendering import render_academic_research_summary
from housing_agent.research.validation import validate_research_proposal


class ResearchSearchState(TypedDict, total=False):
    user_request: str
    approved_scope: dict[str, Any]
    memory_snapshot: dict[str, Any]
    memory_manifest: dict[str, Any]
    research_provider: str
    research_model: str | None
    max_search_tool_calls: int
    research_artifact_dir: str
    research_proposal: dict[str, Any]
    research_validation: dict[str, Any]
    research_ranking: list[dict[str, Any]]
    human_review: dict[str, Any]
    research_summary_markdown: str
    research_metadata: dict[str, Any]
    research_raw_response: dict[str, Any]
    research_personalization: dict[str, Any]
    research_errors: list[str]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _persist_research_artifacts(
    directory: Path,
    *,
    user_request: str,
    scope: ApprovedResearchScope,
    proposal: ResearchProposal | None,
    validation: dict[str, Any],
    metadata: dict[str, Any],
    raw_response: dict[str, Any],
    errors: list[str],
    ranking: list[dict[str, Any]],
    human_review: dict[str, Any],
    personalization: dict[str, Any],
) -> None:
    _write_json(directory / "research_request.json", {
        "user_request": user_request,
        "approved_scope": scope.model_dump(mode="json"),
    })
    if proposal is not None:
        _write_json(
            directory / "predictor_proposal.json",
            proposal.model_dump(mode="json"),
        )
    _write_json(directory / "research_validation.json", validation)
    _write_json(directory / "research_ranking.json", ranking)
    _write_json(directory / "human_review_template.json", human_review)
    _write_json(directory / "research_metadata.json", metadata)
    _write_json(directory / "research_personalization.json", personalization)
    _write_json(directory / "raw_api_response.json", raw_response)
    _write_json(directory / "research_errors.json", {"errors": errors})


def make_search_predictors_node(
    client_factory: Callable[[], ResearchClient] | None = None,
):
    """Create an injectable, provider-neutral LangGraph research node."""

    def node(state: ResearchSearchState) -> ResearchSearchState:
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []
        proposal: ResearchProposal | None = None
        raw_response: dict[str, Any] = {}
        validation_dict: dict[str, Any] = {
            "automated_validation_status": "not_run",
            "scope_validation_status": "not_run",
            "evidence_validation_status": "not_run",
            "human_review_status": "not_ready",
            "errors": [],
            "warnings": [],
            "candidate_counts": {},
            "covered_scope_pairs": [],
            "candidate_scores": [],
        }
        provider_metadata: dict[str, Any] = {}
        personalization: dict[str, Any] = {
            "memory_status": "not_provided",
            "operational_recommendations_deferred": True,
        }
        memory_snapshot: MemorySnapshot | None = None
        memory_manifest: MemoryManifest | None = None
        requested_provider = state.get("research_provider", "gemini")
        requested_model = state.get("research_model")
        max_search_tool_calls = state.get("max_search_tool_calls", 20)
        try:
            user_request = state["user_request"].strip()
            if not user_request:
                raise ValueError("user_request must not be empty")
            if (
                isinstance(max_search_tool_calls, bool)
                or not isinstance(max_search_tool_calls, int)
                or not 1 <= max_search_tool_calls <= 50
            ):
                raise ValueError("max_search_tool_calls must be an integer from 1 to 50")
            scope = ApprovedResearchScope.model_validate(state["approved_scope"])
            if state.get("memory_snapshot"):
                memory_snapshot = MemorySnapshot.model_validate(state["memory_snapshot"])
                if memory_snapshot.approved_scope != scope:
                    raise ValueError(
                        "approved_scope does not match the compiled project memory"
                    )
                if not state.get("memory_manifest"):
                    raise ValueError("memory_manifest is required with memory_snapshot")
                memory_manifest = MemoryManifest.model_validate(state["memory_manifest"])
                if (
                    memory_manifest.project_id != memory_snapshot.project_id
                    or memory_manifest.memory_version != memory_snapshot.memory_version
                ):
                    raise ValueError("memory manifest does not identify this snapshot")
                if memory_manifest.snapshot_sha256 != memory_snapshot_sha256(
                    memory_snapshot
                ):
                    raise ValueError("memory snapshot checksum does not match manifest")
                personalization = {
                    "memory_status": "applied",
                    "project_id": memory_snapshot.project_id,
                    "memory_version": memory_snapshot.memory_version,
                    "memory_sha256": memory_manifest.snapshot_sha256,
                    "research_breadth": (
                        memory_snapshot.research_preferences.discovery_breadth
                    ),
                    "approved_predictor_history": [
                        item.predictor_id
                        for item in memory_snapshot.approved_predictors
                    ],
                    "pending_question_ids": [
                        item.question_id for item in memory_snapshot.pending_questions
                    ],
                    "operational_recommendations_deferred": True,
                }
            canonical = canonical_provider(requested_provider)
            spec = provider_spec(canonical)
            selected_model = requested_model or spec.default_model
            client = (
                client_factory() if client_factory is not None
                else create_research_client(canonical)
            )
            proposal, raw_response, source_urls, provider_metadata = client.search(
                instructions=SEARCH_AGENT_INSTRUCTIONS,
                input_text=build_search_input(
                    user_request,
                    scope,
                    memory_snapshot.model_dump(mode="json")
                    if memory_snapshot is not None
                    else None,
                ),
                scope=scope,
                model=selected_model,
                max_tool_calls=max_search_tool_calls,
            )
            validation = validate_research_proposal(
                proposal,
                scope,
                searched_source_urls=source_urls,
                memory_snapshot=memory_snapshot,
            )
            validation_dict = validation.model_dump(mode="json")
        except Exception as exc:
            if isinstance(exc, StructuredOutputError):
                raw_response = exc.raw_response
                provider_metadata = exc.provider_metadata
            scope_data = state.get("approved_scope", {})
            try:
                scope = ApprovedResearchScope.model_validate(scope_data)
            except Exception:
                scope = None
            errors.append(f"{type(exc).__name__}: {exc}")

        completed_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "execution_status": "fail" if errors else "success",
            "prompt_version": RESEARCH_PROMPT_VERSION,
            "requested_provider": requested_provider,
            "requested_model": requested_model,
            "max_search_tool_calls": max_search_tool_calls,
            "started_at": started_at,
            "completed_at": completed_at,
            **provider_metadata,
            "memory_version": (
                memory_snapshot.memory_version if memory_snapshot is not None else None
            ),
            "memory_sha256": (
                memory_manifest.snapshot_sha256 if memory_manifest is not None else None
            ),
        }
        if errors and validation_dict["automated_validation_status"] == "not_run":
            validation_dict["errors"] = list(errors)

        ranking = list(validation_dict.get("candidate_scores", []))
        human_review = {
            "decision": (
                "pending"
                if validation_dict.get("human_review_status") == "pending"
                else "blocked"
            ),
            "approved_predictor_ids": [],
            "rejected_predictors": [],
            "candidate_reviews": [
                {
                    "predictor_id": item["predictor_id"],
                    "research_score": item["total_score"],
                    "hard_gate_status": item["hard_gate_status"],
                    "decision": "pending",
                    "review_notes": [],
                    "selection_rationale": [],
                }
                for item in ranking
            ],
            "review_notes": [],
        }
        research_summary_markdown = ""
        if proposal is not None and validation_dict.get(
            "automated_validation_status"
        ) == "pass":
            research_summary_markdown = render_academic_research_summary(
                proposal,
                validation,
            )

        artifact_dir = state.get("research_artifact_dir")
        if artifact_dir and scope is not None:
            _persist_research_artifacts(
                Path(artifact_dir),
                user_request=state.get("user_request", ""),
                scope=scope,
                proposal=proposal,
                validation=validation_dict,
                metadata=metadata,
                raw_response=raw_response,
                errors=errors,
                ranking=ranking,
                human_review=human_review,
                personalization=personalization,
            )

        return {
            "research_proposal": (
                proposal.model_dump(mode="json") if proposal is not None else {}
            ),
            "research_validation": validation_dict,
            "research_ranking": ranking,
            "human_review": human_review,
            "research_summary_markdown": research_summary_markdown,
            "research_metadata": metadata,
            "research_raw_response": raw_response,
            "research_personalization": personalization,
            "research_errors": errors,
        }

    return node


search_predictors_node = make_search_predictors_node()


def build_research_search_graph(
    client_factory: Callable[[], ResearchClient] | None = None,
):
    """Compile the isolated SearchNode graph for review and testing."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ResearchSearchState)
    graph.add_node("search_predictors", make_search_predictors_node(client_factory))
    graph.add_edge(START, "search_predictors")
    graph.add_edge("search_predictors", END)
    return graph.compile()
