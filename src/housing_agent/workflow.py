from __future__ import annotations

import json
import calendar
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypedDict

from housing_agent.adapters.datagov import normalize_datagov
from housing_agent.adapters.mom import parse_mom_non_resident_employment
from housing_agent.models import Observation
from housing_agent.run_context import RunPaths, finalize_manifest, initialize_run, save_checkpoint
from housing_agent.retrieval import retrieve_catalog_sources
from housing_agent.transforms import (
    absolute_change,
    derive_pipeline_under_construction_share,
    derive_vacancy_rate,
    percent_change,
    quarterly_last_month_end,
)


class AgentState(TypedDict, total=False):
    run_id: str
    reporting_as_of_date: str
    project_root: str
    catalog_version: str
    prompt_version: str
    run_paths: dict[str, str]
    started_at: str
    completed_at: str | None
    catalog: dict[str, Any]
    snapshot_paths: dict[str, str]
    execution_mode: Literal["live", "snapshots"]
    request_interval_seconds: float
    retrieval_results: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    derived_observations: list[dict[str, Any]]
    validation_errors: list[str]
    evidence: dict[str, dict[str, Any]]
    report_markdown: str
    run_status: Literal[
        "initializing", "running", "validated", "reported",
        "blocked", "partial", "failed", "complete"
    ]


# Compatibility alias while callers migrate to the final state name.
WorkflowState = AgentState


REPORT_SERIES_IDS = {
    "ura_non_landed_price_index__non_landed",
    "ura_non_landed_price_index__non_landed__qoq_pct",
    "ura_non_landed_price_index__non_landed__yoy_pct",
    "ura_non_landed_rental_index__non_landed_whole_island",
    "ura_non_landed_rental_index__non_landed_whole_island__qoq_pct",
    "ura_non_landed_rental_index__non_landed_whole_island__yoy_pct",
    "private_residential_pipeline_supply__total_non_landed_properties",
    "private_residential_pipeline_supply__total_non_landed_properties__qoq_absolute_change",
    "private_residential_pipeline_supply__total_non_landed_properties__yoy_pct",
    "private_residential_pipeline_supply__under_construction_share",
    "non_resident_population__non_resident_population",
    "non_resident_population__non_resident_population__yoy_pct",
    "non_resident_employment_change__quarterly_change",
    "private_non_landed_vacancy_rate__rate",
    "private_non_landed_vacancy_rate__rate__qoq_pp_change",
    "private_non_landed_vacancy_rate__rate__yoy_pp_change",
    "three_month_compounded_sora__compounded_singapore_overnight_rate_average_sora_3_month__quarter_end",
    "real_gdp_growth__gdp_in_chained_2015_dollars",
    "real_gdp_growth__gdp_in_chained_2015_dollars__previous_quarter_pp_change",
}


def load_catalog_node(state: WorkflowState) -> WorkflowState:
    root = Path(state.get("project_root", "."))
    catalog = json.loads((root / "config/data_catalog.yaml").read_text())
    return {
        "catalog": catalog,
        "catalog_version": str(catalog["catalog_version"]),
        "validation_errors": [],
        "run_status": "initializing",
    }


def initialize_run_node(state: AgentState) -> AgentState:
    run_id, paths, manifest = initialize_run(
        project_root=Path(state.get("project_root", ".")),
        reporting_as_of_date=state["reporting_as_of_date"],
        catalog_version=state["catalog_version"],
        prompt_version=state.get("prompt_version", "deterministic-v1"),
        run_id=state.get("run_id"),
    )
    return {
        "run_id": run_id,
        "run_paths": paths.to_dict(),
        "started_at": manifest["started_at"],
        "completed_at": None,
        "prompt_version": manifest["prompt_version"],
        "run_status": "running",
    }


def discover_snapshots_node(state: WorkflowState) -> WorkflowState:
    root = Path(state.get("project_root", "."))
    paths: dict[str, str] = {}
    errors: list[str] = []
    for source in state["catalog"]["sources"]:
        suffix = "html" if source["source_type"] == "mom_report_html" else "json"
        candidates = sorted((root / "data/raw").glob(f"spike_*/{source['source_id']}.{suffix}"))
        if not candidates:
            errors.append(f"No raw snapshot found for {source['source_id']}")
        else:
            paths[source["source_id"]] = str(candidates[-1])
    return {"snapshot_paths": paths, "validation_errors": errors}


def retrieve_sources_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    results = retrieve_catalog_sources(
        state["catalog"]["sources"],
        Path(paths.raw),
        request_interval_seconds=state.get("request_interval_seconds", 13.0),
    )
    snapshots = {
        result.source_id: result.raw_snapshot_path
        for result in results
        if result.retrieval_status == "success" and result.raw_snapshot_path
    }
    errors = [
        f"{result.source_id}: {result.error_category}: {result.error_message}"
        for result in results
        if result.retrieval_status != "success"
    ]
    return {
        "retrieval_results": [result.to_dict() for result in results],
        "snapshot_paths": snapshots,
        "validation_errors": errors,
    }


def route_execution_mode(state: AgentState) -> str:
    return "retrieve_sources" if state.get("execution_mode", "live") == "live" else "discover_snapshots"


def normalize_node(state: WorkflowState) -> WorkflowState:
    root = Path(state.get("project_root", ".")).resolve()
    observations: list[dict[str, Any]] = []
    errors = list(state.get("validation_errors", []))
    for source in state["catalog"]["sources"]:
        raw_path = state.get("snapshot_paths", {}).get(source["source_id"])
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        try:
            if source["source_type"] == "datagov_json":
                items = normalize_datagov(json.loads(path.read_text()), source)
            elif source["source_type"] == "mom_report_html":
                items = parse_mom_non_resident_employment(path.read_bytes(), source)
            else:
                raise ValueError(f"Unsupported source type {source['source_type']!r}")
            cutoff = date.fromisoformat(state["reporting_as_of_date"])
            for item in items:
                if _period_end(item.period) > cutoff:
                    continue
                if item.release_date and date.fromisoformat(item.release_date) > cutoff:
                    errors.append(
                        f"{source['source_id']}: selected report was released after the as-of date"
                    )
                    continue
                observations.append(item.to_dict())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{source['source_id']}: {exc}")
    return {"observations": observations, "validation_errors": errors}


def _period_end(period: str) -> date:
    if "-Q" in period:
        year, quarter = period.split("-Q")
        month = int(quarter) * 3
        return date(int(year), month, calendar.monthrange(int(year), month)[1])
    if "-" in period:
        year, month = (int(part) for part in period.split("-"))
        return date(year, month, calendar.monthrange(year, month)[1])
    # The selected population series is measured at end-June, not end-December.
    return date(int(period), 6, 30)


def _items(state: WorkflowState, source_id: str) -> list[Observation]:
    return [
        Observation(**item)
        for item in state.get("observations", [])
        if item["source_id"] == source_id
    ]


def transform_node(state: WorkflowState) -> WorkflowState:
    derived: list[Observation] = []

    for source_id in ("ura_non_landed_price_index", "ura_non_landed_rental_index"):
        items = _items(state, source_id)
        derived.extend(percent_change(items, 1, "qoq_pct"))
        derived.extend(percent_change(items, 4, "yoy_pct"))

    population = _items(state, "non_resident_population")
    derived.extend(percent_change(population, 1, "yoy_pct"))

    pipeline = _items(state, "private_residential_pipeline_supply")
    total_pipeline = [item for item in pipeline if item.series_label == "Total Non-Landed Properties"]
    derived.extend(absolute_change(total_pipeline, 1, "qoq_absolute_change", "dwelling units"))
    derived.extend(percent_change(total_pipeline, 4, "yoy_pct"))
    derived.extend(derive_pipeline_under_construction_share(pipeline))

    vacancy = derive_vacancy_rate(_items(state, "private_non_landed_vacancy_rate"))
    derived.extend(vacancy)
    derived.extend(absolute_change(vacancy, 1, "qoq_pp_change", "percentage points"))
    derived.extend(absolute_change(vacancy, 4, "yoy_pp_change", "percentage points"))

    derived.extend(quarterly_last_month_end(_items(state, "three_month_compounded_sora")))

    gdp = _items(state, "real_gdp_growth")
    derived.extend(absolute_change(gdp, 1, "previous_quarter_pp_change", "percentage points"))
    return {"derived_observations": [item.to_dict() for item in derived]}


def validate_node(state: WorkflowState) -> WorkflowState:
    errors = list(state.get("validation_errors", []))
    required = {source["source_id"] for source in state["catalog"]["sources"]}
    present = {item["source_id"] for item in state.get("observations", [])}
    for missing in sorted(required - present):
        errors.append(f"Required source produced no observations: {missing}")

    seen: set[tuple[str, str, str]] = set()
    for item in state.get("observations", []) + state.get("derived_observations", []):
        key = (item["source_id"], item["series_id"], item["period"])
        if key in seen:
            errors.append(f"Duplicate observation: {key}")
        seen.add(key)
    return {
        "validation_errors": errors,
        "run_status": "blocked" if errors else "validated",
    }


def route_after_validation(state: WorkflowState) -> str:
    return "halt" if state.get("validation_errors") else "build_evidence"


def build_evidence_node(state: WorkflowState) -> WorkflowState:
    combined = state.get("observations", []) + state.get("derived_observations", [])
    evidence: dict[str, dict[str, Any]] = {}
    for item in combined:
        if item["value"] is None or item["series_id"] not in REPORT_SERIES_IDS:
            continue
        existing = evidence.get(item["series_id"])
        if existing is None or item["period"] > existing["period"]:
            evidence[item["series_id"]] = item
    return {"evidence": evidence}


def draft_report_node(state: WorkflowState) -> WorkflowState:
    """Build a deterministic evidence brief; an optional LLM may rewrite only this text."""
    lines = [
        "# Singapore Private Non-Landed Housing Indicator Brief",
        "",
        f"**Information cut-off:** {state['reporting_as_of_date']}",
        "",
        "This brief reports descriptive public-data signals. It does not claim causal effects or model forecasts.",
        "",
    ]
    headings = [("shared", "Shared supply"), ("rent", "Rental market"), ("sale", "Sale market")]
    evidence = state.get("evidence", {}).values()
    for market, heading in headings:
        lines.extend([f"## {heading}", ""])
        rows = sorted((row for row in evidence if row["market"] == market), key=lambda row: row["series_label"])
        for item in rows:
            incomplete = " (incomplete quarter)" if item.get("quarter_incomplete") else ""
            source_period = (
                f"; source month {item['source_observation_period']}"
                if item.get("source_observation_period") else ""
            )
            lines.append(
                f"- **{item['series_label']}**: {item['value']:.3f} {item['unit']} "
                f"in {item['period']}{source_period}{incomplete}."
            )
        lines.append("")
    return {"report_markdown": "\n".join(lines) + "\n", "run_status": "reported"}


def halt_node(state: WorkflowState) -> WorkflowState:
    return {"run_status": "blocked"}


def checkpoint_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    stage = state["run_status"]
    checkpoint_state = {
        key: value for key, value in state.items()
        if key not in {"catalog"}
    }
    save_checkpoint(paths, stage, checkpoint_state)
    return {}


def finalize_run_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    blocked = bool(state.get("validation_errors"))
    terminal_status = "failed" if blocked else "complete"
    manifest = finalize_manifest(
        paths,
        status=terminal_status,
        sources=state.get("retrieval_results", []),
        validation_errors=state.get("validation_errors", []),
        counts={
            "observations": len(state.get("observations", [])),
            "derived_observations": len(state.get("derived_observations", [])),
            "evidence_series": len(state.get("evidence", {})),
        },
    )
    return {
        "completed_at": manifest["completed_at"],
        "run_status": "failed" if blocked else "complete",
    }


def build_graph():
    """Compile the LangGraph. Imported lazily so pure nodes remain dependency-light."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkflowState)
    graph.add_node("load_catalog", load_catalog_node)
    graph.add_node("initialize_run", initialize_run_node)
    graph.add_node("retrieve_sources", retrieve_sources_node)
    graph.add_node("discover_snapshots", discover_snapshots_node)
    graph.add_node("normalize", normalize_node)
    graph.add_node("transform", transform_node)
    graph.add_node("validate", validate_node)
    graph.add_node("build_evidence", build_evidence_node)
    graph.add_node("draft_report", draft_report_node)
    graph.add_node("halt", halt_node)
    graph.add_node("checkpoint", checkpoint_node)
    graph.add_node("finalize_run", finalize_run_node)
    graph.add_edge(START, "load_catalog")
    graph.add_edge("load_catalog", "initialize_run")
    graph.add_conditional_edges(
        "initialize_run", route_execution_mode,
        {"retrieve_sources": "retrieve_sources", "discover_snapshots": "discover_snapshots"},
    )
    graph.add_edge("retrieve_sources", "normalize")
    graph.add_edge("discover_snapshots", "normalize")
    graph.add_edge("normalize", "transform")
    graph.add_edge("transform", "validate")
    graph.add_conditional_edges(
        "validate", route_after_validation,
        {"build_evidence": "build_evidence", "halt": "halt"},
    )
    graph.add_edge("build_evidence", "draft_report")
    graph.add_edge("draft_report", "checkpoint")
    graph.add_edge("halt", "checkpoint")
    graph.add_edge("checkpoint", "finalize_run")
    graph.add_edge("finalize_run", END)
    return graph.compile()
