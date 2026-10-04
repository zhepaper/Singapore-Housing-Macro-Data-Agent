"""Legacy catalog-specific LangGraph retained for sample-run reproducibility."""

from __future__ import annotations

import json
import calendar
import hashlib
import os
import shutil
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict

from housing_agent.adapters.datagov import normalize_datagov
from housing_agent.adapters.mom import parse_mom_non_resident_employment
from housing_agent.models import Observation
from housing_agent.run_context import RunPaths, finalize_manifest, initialize_run, save_checkpoint
from housing_agent.retrieval import retrieve_catalog_sources, use_approved_cached_fallback
from housing_agent.legacy.reporting import (
    DeterministicWriter,
    LangChainWriter,
    PROMPT_VERSION,
    compose_report,
)
from housing_agent.legacy.verification import verify_report
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
    allow_cached_fallback: bool
    warnings: list[str]
    observations: list[dict[str, Any]]
    derived_observations: list[dict[str, Any]]
    validation_errors: list[str]
    evidence: dict[str, dict[str, Any]]
    report_markdown: str
    writer_mode: Literal["deterministic", "openai"]
    writer_model: str
    writer_narrative: str
    writer_metadata: dict[str, Any]
    writer_error: str | None
    claim_ledger: list[dict[str, Any]]
    verification_result: dict[str, Any]
    verification_errors: list[str]
    freshness_results: dict[str, dict[str, Any]]
    requires_human_review: bool
    revision_count: int
    max_revisions: int
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
    "three_month_compounded_sora__compounded_singapore_overnight_rate_average_sora_3_month__quarter_end__qoq_pp_change",
    "real_gdp_growth__gdp_in_chained_2015_dollars",
    "real_gdp_growth__gdp_in_chained_2015_dollars__previous_quarter_pp_change",
}

REQUIRED_LATEST_DERIVED_IDS = {
    "ura_non_landed_price_index": {
        "ura_non_landed_price_index__non_landed__qoq_pct",
        "ura_non_landed_price_index__non_landed__yoy_pct",
    },
    "ura_non_landed_rental_index": {
        "ura_non_landed_rental_index__non_landed_whole_island__qoq_pct",
        "ura_non_landed_rental_index__non_landed_whole_island__yoy_pct",
    },
    "non_resident_population": {
        "non_resident_population__non_resident_population__yoy_pct",
    },
    "private_residential_pipeline_supply": {
        "private_residential_pipeline_supply__total_non_landed_properties__qoq_absolute_change",
        "private_residential_pipeline_supply__total_non_landed_properties__yoy_pct",
        "private_residential_pipeline_supply__under_construction_share",
    },
    "private_non_landed_vacancy_rate": {
        "private_non_landed_vacancy_rate__rate",
        "private_non_landed_vacancy_rate__rate__qoq_pp_change",
        "private_non_landed_vacancy_rate__rate__yoy_pp_change",
    },
    "three_month_compounded_sora": {
        "three_month_compounded_sora__compounded_singapore_overnight_rate_average_sora_3_month__quarter_end",
        "three_month_compounded_sora__compounded_singapore_overnight_rate_average_sora_3_month__quarter_end__qoq_pp_change",
    },
    "real_gdp_growth": {
        "real_gdp_growth__gdp_in_chained_2015_dollars__previous_quarter_pp_change",
    },
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
        prompt_version=state.get("prompt_version", PROMPT_VERSION),
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
    retrieval_results: list[dict[str, Any]] = []
    errors: list[str] = []
    for source in state["catalog"]["sources"]:
        suffix = "html" if source["source_type"] == "mom_report_html" else "json"
        candidates = sorted((root / "data/raw").glob(f"spike_*/{source['source_id']}.{suffix}"))
        if not candidates:
            errors.append(f"No raw snapshot found for {source['source_id']}")
        else:
            selected = candidates[-1]
            if state.get("run_paths"):
                destination = Path(state["run_paths"]["raw"]) / f"{source['source_id']}.{suffix}"
                shutil.copy2(selected, destination)
                selected = destination
            body = selected.read_bytes()
            paths[source["source_id"]] = str(selected)
            retrieval_results.append({
                "source_id": source["source_id"],
                "source_url": source["retrieval_url"],
                "retrieved_at": datetime.fromtimestamp(
                    selected.stat().st_mtime, timezone.utc
                ).isoformat(),
                "retrieval_status": "success",
                "http_status": 200,
                "content_type": "application/json" if suffix == "json" else "text/html",
                "raw_snapshot_path": str(selected),
                "raw_file_sha256": hashlib.sha256(body).hexdigest(),
                "raw_page_paths": [str(selected)],
                "raw_page_sha256s": [hashlib.sha256(body).hexdigest()],
                "bytes_received": len(body),
                "retry_count": 0,
                "error_category": None,
                "error_message": None,
            })
    return {
        "snapshot_paths": paths,
        "retrieval_results": retrieval_results,
        "validation_errors": errors,
    }


def retrieve_sources_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    results = retrieve_catalog_sources(
        state["catalog"]["sources"],
        Path(paths.raw),
        request_interval_seconds=state.get("request_interval_seconds", 13.0),
    )
    if state.get("allow_cached_fallback", False):
        source_by_id = {
            source["source_id"]: source for source in state["catalog"]["sources"]
        }
        results = [
            use_approved_cached_fallback(
                result,
                source_by_id[result.source_id],
                project_root=Path(state.get("project_root", ".")),
                run_raw_dir=Path(paths.raw),
            ) if result.retrieval_status == "failed" else result
            for result in results
        ]
    snapshots = {
        result.source_id: result.raw_snapshot_path
        for result in results
        if result.retrieval_status in {"success", "fallback"} and result.raw_snapshot_path
    }
    errors = [
        f"{result.source_id}: {result.error_category}: {result.error_message}"
        for result in results
        if result.retrieval_status != "success"
        and result.retrieval_status != "fallback"
    ]
    warnings = [
        f"{result.source_id}: live retrieval failed; an explicitly approved cached official "
        f"snapshot was used ({result.error_category})."
        for result in results if result.retrieval_status == "fallback"
    ]
    return {
        "retrieval_results": [result.to_dict() for result in results],
        "snapshot_paths": snapshots,
        "validation_errors": errors,
        "warnings": warnings,
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
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
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


def _next_period_end(period: str) -> date:
    if "-Q" in period:
        year_text, quarter_text = period.split("-Q")
        year, quarter = int(year_text), int(quarter_text)
        if quarter == 4:
            return date(year + 1, 3, 31)
        month = (quarter + 1) * 3
        return date(year, month, calendar.monthrange(year, month)[1])
    if "-" in period:
        year, month = (int(part) for part in period.split("-"))
        if month == 12:
            return date(year + 1, 1, 31)
        next_month = month + 1
        return date(year, next_month, calendar.monthrange(year, next_month)[1])
    return date(int(period) + 1, 6, 30)


def freshness_status(latest_period: str, expected_lag_days: int, cutoff: date) -> dict[str, Any]:
    next_expected_period_end = _next_period_end(latest_period)
    expected_release_by = next_expected_period_end + timedelta(days=expected_lag_days)
    if cutoff <= next_expected_period_end:
        status = "current"
    elif cutoff <= expected_release_by:
        status = "not_yet_released"
    else:
        status = "stale"
    return {
        "status": status,
        "latest_period": latest_period,
        "next_expected_release_by": expected_release_by.isoformat(),
    }


def _items(state: WorkflowState, source_id: str) -> list[Observation]:
    return [
        Observation(**item)
        for item in state.get("observations", [])
        if item["source_id"] == source_id
    ]


def transform_node(state: WorkflowState) -> WorkflowState:
    derived: list[Observation] = []
    errors = list(state.get("validation_errors", []))

    def add(source_id: str, transformation: str, producer: Any) -> None:
        try:
            derived.extend(producer())
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{source_id}: {transformation} failed: {exc}")

    for source_id in ("ura_non_landed_price_index", "ura_non_landed_rental_index"):
        items = _items(state, source_id)
        add(source_id, "qoq_percent_change", lambda items=items: percent_change(items, 1, "qoq_pct"))
        add(source_id, "yoy_percent_change", lambda items=items: percent_change(items, 4, "yoy_pct"))

    population = _items(state, "non_resident_population")
    add(
        "non_resident_population", "yoy_percent_change",
        lambda: percent_change(population, 1, "yoy_pct"),
    )

    pipeline = _items(state, "private_residential_pipeline_supply")
    total_pipeline = [item for item in pipeline if item.series_label == "Total Non-Landed Properties"]
    add(
        "private_residential_pipeline_supply", "qoq_absolute_change",
        lambda: absolute_change(total_pipeline, 1, "qoq_absolute_change", "dwelling units"),
    )
    add(
        "private_residential_pipeline_supply", "yoy_percent_change",
        lambda: percent_change(total_pipeline, 4, "yoy_pct"),
    )
    add(
        "private_residential_pipeline_supply", "under_construction_share",
        lambda: derive_pipeline_under_construction_share(pipeline),
    )

    vacancy: list[Observation] = []
    try:
        vacancy = derive_vacancy_rate(_items(state, "private_non_landed_vacancy_rate"))
        derived.extend(vacancy)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"private_non_landed_vacancy_rate: rate derivation failed: {exc}")
    if vacancy:
        add(
            "private_non_landed_vacancy_rate", "qoq_percentage_point_change",
            lambda: absolute_change(vacancy, 1, "qoq_pp_change", "percentage points"),
        )
        add(
            "private_non_landed_vacancy_rate", "yoy_percentage_point_change",
            lambda: absolute_change(vacancy, 4, "yoy_pp_change", "percentage points"),
        )

    quarterly_sora: list[Observation] = []
    try:
        quarterly_sora = quarterly_last_month_end(_items(state, "three_month_compounded_sora"))
        derived.extend(quarterly_sora)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"three_month_compounded_sora: quarter-end conversion failed: {exc}")
    if quarterly_sora:
        add(
            "three_month_compounded_sora", "qoq_percentage_point_change",
            lambda: absolute_change(quarterly_sora, 1, "qoq_pp_change", "percentage points"),
        )

    gdp = _items(state, "real_gdp_growth")
    add(
        "real_gdp_growth", "previous_quarter_percentage_point_change",
        lambda: absolute_change(gdp, 1, "previous_quarter_pp_change", "percentage points"),
    )
    return {
        "derived_observations": [item.to_dict() for item in derived],
        "validation_errors": errors,
    }


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
        period = item.get("period", "")
        try:
            _period_end(period)
        except (TypeError, ValueError):
            errors.append(f"Invalid or missing period for {key}: {period!r}")
        if item.get("role") == "derived":
            if not item.get("derivation"):
                errors.append(f"Derived observation has no formula: {key}")
            if not item.get("source_periods") or not item.get("input_series_ids"):
                errors.append(f"Derived observation has incomplete lineage: {key}")
    expected_units = {
        source["source_id"]: source.get("unit") for source in state["catalog"]["sources"]
    }
    for item in state.get("observations", []):
        expected_unit = expected_units.get(item["source_id"])
        if expected_unit and item.get("unit") != expected_unit:
            errors.append(
                f"{item['source_id']}: unexpected unit {item.get('unit')!r}; "
                f"expected {expected_unit!r}"
            )

    derived_items = state.get("derived_observations", [])
    for source_id, required_series in REQUIRED_LATEST_DERIVED_IDS.items():
        source_items = [
            item for item in state.get("observations", [])
            if item.get("source_id") == source_id and item.get("value") is not None
        ]
        if not source_items:
            continue
        latest_source_period = max(item["period"] for item in source_items)
        if source_id == "three_month_compounded_sora":
            year, month = latest_source_period.split("-")
            latest_period = f"{year}-Q{(int(month) - 1) // 3 + 1}"
        else:
            latest_period = latest_source_period
        available_latest = {
            item["series_id"] for item in derived_items
            if item.get("source_id") == source_id and item.get("period") == latest_period
        }
        for missing_series in sorted(required_series - available_latest):
            errors.append(
                f"{source_id}: latest derived metric {missing_series} is unavailable for "
                f"{latest_period}; a required comparison period or formula input is missing"
            )
    cutoff = date.fromisoformat(state["reporting_as_of_date"])
    freshness_results: dict[str, dict[str, Any]] = {}
    for source in state["catalog"]["sources"]:
        source_items = [
            item for item in state.get("observations", [])
            if item["source_id"] == source["source_id"]
        ]
        minimum = int(source.get("minimum_normalized_observations", 1))
        if source_items and len(source_items) < minimum:
            errors.append(
                f"{source['source_id']}: normalized history has {len(source_items)} observations; "
                f"expected at least {minimum}"
            )
        valid_source_items = []
        for item in source_items:
            try:
                _period_end(item["period"])
            except (TypeError, ValueError):
                continue
            valid_source_items.append(item)
        if valid_source_items:
            latest = max(item["period"] for item in valid_source_items)
            freshness = freshness_status(
                latest,
                int(source["freshness_rule"]["expected_lag_days"]),
                cutoff,
            )
            freshness_results[source["source_id"]] = freshness
            if freshness["status"] == "stale":
                errors.append(
                    f"{source['source_id']}: latest period {latest} is stale; "
                    f"next release expected by {freshness['next_expected_release_by']}"
                )
    return {
        "validation_errors": errors,
        "freshness_results": freshness_results,
        "run_status": "blocked" if errors else "validated",
        "requires_human_review": any(
            marker in error.lower()
            for error in errors
            for marker in ("exact series", "configured series", "schema", "unexpected unit", "ambiguous")
        ),
    }


def route_after_validation(state: WorkflowState) -> str:
    return "halt" if state.get("validation_errors") else "build_evidence"


def build_evidence_node(state: WorkflowState) -> WorkflowState:
    combined = state.get("observations", []) + state.get("derived_observations", [])
    evidence: dict[str, dict[str, Any]] = {}
    sources = {source["source_id"]: source for source in state["catalog"]["sources"]}
    provenance = {
        result["source_id"]: result for result in state.get("retrieval_results", [])
    }
    project_root = Path(state.get("project_root", ".")).resolve()

    def portable_path(value: str | None) -> str | None:
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute():
            return value
        try:
            return str(path.resolve().relative_to(project_root))
        except ValueError:
            return value
    for item in combined:
        if item["value"] is None or item["series_id"] not in REPORT_SERIES_IDS:
            continue
        source = sources[item["source_id"]]
        run_source = provenance.get(item["source_id"], {})
        evidence_item = {
            "metric_id": item["series_id"],
            **item,
            "run_id": state["run_id"],
            "provenance_id": f"{state['run_id']}:{item['source_id']}",
            "factor": source["factor"],
            "definition": source["definition"],
            "series_identifier": source["series_identifier"],
            "observation_frequency": source["native_frequency"],
            "update_frequency": source["update_frequency"],
            "mechanism": source["mechanism"],
            "potential_lag": source["potential_lag"],
            "point_in_time_availability": source["point_in_time_availability"],
            "limitations": source["limitations"],
            "source_url": run_source.get("source_url", source["retrieval_url"]),
            "source_page_url": source["page_url"],
            "raw_snapshot_path": portable_path(run_source.get("raw_snapshot_path")),
            "raw_sha256": run_source.get("raw_file_sha256"),
            "retrieved_at": run_source.get("retrieved_at"),
            "completeness": "incomplete" if item.get("quarter_incomplete") else "complete",
            "freshness_status": state.get("freshness_results", {}).get(
                item["source_id"], {}
            ).get("status", "unavailable"),
        }
        existing = evidence.get(item["series_id"])
        if existing is None or item["period"] > existing["period"]:
            evidence[item["series_id"]] = evidence_item
    return {"evidence": evidence}


def writer_node(state: AgentState) -> AgentState:
    feedback = state.get("verification_errors", [])
    mode = state.get("writer_mode", "deterministic")
    if mode == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            return {
                "writer_error": "OPENAI_API_KEY is not set for the OpenAI writer.",
                "writer_metadata": {
                    "writer": "langchain-openai",
                    "prompt_version": "evidence-writer-v1",
                    "model": state.get("writer_model", "gpt-5-mini"),
                    "token_usage": None,
                    "response_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "revision_count": state.get("revision_count", 0) + 1,
            }
        from langchain_openai import ChatOpenAI

        model_name = state.get("writer_model", "gpt-5-mini")
        writer = LangChainWriter(ChatOpenAI(model=model_name, temperature=0))
    else:
        writer = DeterministicWriter()
    try:
        result = writer.write(state["evidence"], feedback=feedback)
    except Exception as exc:
        return {
            "writer_error": f"Writer invocation failed: {type(exc).__name__}: {exc}",
            "revision_count": state.get("revision_count", 0) + 1,
        }
    return {
        "writer_narrative": result.narrative,
        "writer_metadata": result.metadata,
        "revision_count": state.get("revision_count", 0) + 1,
        "writer_error": None,
        "run_status": "reported",
    }


def compose_report_node(state: AgentState) -> AgentState:
    markdown, ledger = compose_report(
        reporting_as_of_date=state["reporting_as_of_date"],
        narrative=state["writer_narrative"],
        evidence=state["evidence"],
        warnings=state.get("warnings", []),
    )
    return {"report_markdown": markdown, "claim_ledger": ledger}


def route_after_writer(state: AgentState) -> str:
    return "halt" if state.get("writer_error") else "compose_report"


def verify_report_node(state: AgentState) -> AgentState:
    result = verify_report(
        state["report_markdown"],
        state["claim_ledger"],
        state["evidence"],
    )
    return {
        "verification_result": result,
        "verification_errors": result["errors"],
    }


def route_after_verification(state: AgentState) -> str:
    if state.get("verification_result", {}).get("status") == "pass":
        return "persist_artifacts"
    if state.get("revision_count", 0) < state.get("max_revisions", 2):
        return "writer"
    return "halt"


def halt_node(state: WorkflowState) -> WorkflowState:
    return {"run_status": "blocked"}


def _checkpoint(state: AgentState, stage: str) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    save_checkpoint(paths, stage, dict(state))
    return {}


def checkpoint_retrieved_node(state: AgentState) -> AgentState:
    return _checkpoint(state, "retrieved")


def checkpoint_normalized_node(state: AgentState) -> AgentState:
    return _checkpoint(state, "normalized")


def checkpoint_transformed_node(state: AgentState) -> AgentState:
    return _checkpoint(state, "transformed")


def checkpoint_validated_node(state: AgentState) -> AgentState:
    return _checkpoint(state, "validated")


def persist_artifacts_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    normalized_path = Path(paths.normalized) / "observations.jsonl"
    metrics_path = Path(paths.metrics) / "derived_observations.jsonl"
    evidence_path = Path(paths.metrics) / "evidence.json"
    report_path = Path(paths.report) / "report.md"
    ledger_path = Path(paths.report) / "claim_ledger.json"
    verification_path = Path(paths.report) / "verification.json"
    writer_metadata_path = Path(paths.report) / "writer_metadata.json"

    def with_provenance(item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "run_id": state["run_id"],
            "provenance_id": f"{state['run_id']}:{item['source_id']}",
        }

    normalized_path.write_text(
        "".join(
            json.dumps(with_provenance(item), sort_keys=True) + "\n"
            for item in state.get("observations", [])
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        "".join(
            json.dumps(with_provenance(item), sort_keys=True) + "\n"
            for item in state.get("derived_observations", [])
        ),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(state.get("evidence", {}), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(state["report_markdown"], encoding="utf-8")
    ledger_path.write_text(
        json.dumps(state.get("claim_ledger", []), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verification_path.write_text(
        json.dumps(state.get("verification_result", {}), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    writer_metadata_path.write_text(
        json.dumps(state.get("writer_metadata", {}), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {}


def persist_diagnostics_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    diagnostics = {
        "validation_errors": state.get("validation_errors", []),
        "writer_error": state.get("writer_error"),
        "verification_result": state.get("verification_result"),
        "warnings": state.get("warnings", []),
        "requires_human_review": state.get("requires_human_review", False),
    }
    (Path(paths.root) / "failure_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {}


def finalize_run_node(state: AgentState) -> AgentState:
    paths = RunPaths(**state["run_paths"])
    blocked = bool(state.get("validation_errors"))
    blocked = blocked or bool(state.get("verification_errors"))
    blocked = blocked or bool(state.get("writer_error"))
    used_fallback = any(
        result.get("retrieval_status") == "fallback"
        for result in state.get("retrieval_results", [])
    )
    terminal_status = "failed" if blocked else ("partial" if used_fallback else "complete")
    observations_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in state.get("observations", []):
        observations_by_source.setdefault(item["source_id"], []).append(item)
    enriched_sources: list[dict[str, Any]] = []
    for result in state.get("retrieval_results", []):
        source_id = result["source_id"]
        source_items = observations_by_source.get(source_id, [])
        source_errors = [
            error for error in state.get("validation_errors", [])
            if error.startswith(f"{source_id}:")
            or error.endswith(f": {source_id}")
        ]
        enriched_sources.append({
            **result,
            "latest_available_period": max(
                (item["period"] for item in source_items), default=None
            ),
            "freshness_status": state.get("freshness_results", {}).get(
                source_id, {}
            ).get("status", "unavailable"),
            "validation_status": "fail" if source_errors else (
                "pass" if source_items else "not_run"
            ),
            "record_count": len(source_items),
        })
    manifest = finalize_manifest(
        paths,
        status=terminal_status,
        sources=enriched_sources,
        validation_errors=(
            state.get("validation_errors", [])
            + state.get("verification_errors", [])
            + ([state["writer_error"]] if state.get("writer_error") else [])
        ),
        counts={
            "observations": len(state.get("observations", [])),
            "derived_observations": len(state.get("derived_observations", [])),
            "evidence_series": len(state.get("evidence", {})),
        },
        warnings=state.get("warnings", []),
    )
    return {
        "completed_at": manifest["completed_at"],
        "run_status": "failed" if blocked else ("partial" if used_fallback else "complete"),
    }


def build_graph(*, resume_from: str | None = None):
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
    graph.add_node("writer", writer_node)
    graph.add_node("compose_report", compose_report_node)
    graph.add_node("verify_report", verify_report_node)
    graph.add_node("halt", halt_node)
    graph.add_node("checkpoint_retrieved", checkpoint_retrieved_node)
    graph.add_node("checkpoint_normalized", checkpoint_normalized_node)
    graph.add_node("checkpoint_transformed", checkpoint_transformed_node)
    graph.add_node("checkpoint_validated", checkpoint_validated_node)
    graph.add_node("persist_artifacts", persist_artifacts_node)
    graph.add_node("persist_diagnostics", persist_diagnostics_node)
    graph.add_node("finalize_run", finalize_run_node)
    if resume_from is None:
        graph.add_edge(START, "load_catalog")
        graph.add_edge("load_catalog", "initialize_run")
    elif resume_from in {"normalize", "transform", "validate", "build_evidence"}:
        graph.add_edge(START, resume_from)
    else:
        raise ValueError(f"Unsupported resume entry point: {resume_from!r}")
    graph.add_conditional_edges(
        "initialize_run", route_execution_mode,
        {"retrieve_sources": "retrieve_sources", "discover_snapshots": "discover_snapshots"},
    )
    graph.add_edge("retrieve_sources", "checkpoint_retrieved")
    graph.add_edge("discover_snapshots", "checkpoint_retrieved")
    graph.add_edge("checkpoint_retrieved", "normalize")
    graph.add_edge("normalize", "checkpoint_normalized")
    graph.add_edge("checkpoint_normalized", "transform")
    graph.add_edge("transform", "checkpoint_transformed")
    graph.add_edge("checkpoint_transformed", "validate")
    graph.add_edge("validate", "checkpoint_validated")
    graph.add_conditional_edges(
        "checkpoint_validated", route_after_validation,
        {"build_evidence": "build_evidence", "halt": "halt"},
    )
    graph.add_edge("build_evidence", "writer")
    graph.add_conditional_edges(
        "writer", route_after_writer,
        {"compose_report": "compose_report", "halt": "halt"},
    )
    graph.add_edge("compose_report", "verify_report")
    graph.add_conditional_edges(
        "verify_report", route_after_verification,
        {"persist_artifacts": "persist_artifacts", "writer": "writer", "halt": "halt"},
    )
    graph.add_edge("persist_artifacts", "finalize_run")
    graph.add_edge("halt", "persist_diagnostics")
    graph.add_edge("persist_diagnostics", "finalize_run")
    graph.add_edge("finalize_run", END)
    return graph.compile()
