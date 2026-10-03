from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, TypedDict
from urllib.parse import urlparse

from housing_agent.onboarding.discovery_models import (
    DataDiscoveryProposal,
    DataDiscoveryValidation,
    DataSourceCandidate,
    DiscoveryCandidateScore,
    DraftCatalogEntry,
    SourceProbeResult,
    load_discovery_proposal,
)
from housing_agent.onboarding.discovery_tools import probe_data_source
from housing_agent.research.models import (
    ApprovedResearchScope,
    PredictorCandidate,
    load_predictor_candidate,
)
from housing_agent.research.providers import provider_spec
from housing_agent.retrieval import validate_official_url


DISCOVERY_PROMPT_VERSION = "data-discovery-v2-structural-only"
DISCOVERY_INSTRUCTIONS = """You are a public-data discovery agent. Your task is to find one or two
official, publicly accessible datasets for exactly one human-approved predictor concept.

BOUNDARIES
- Search only official Singapore government or statutory-board sources.
- Do not broaden or replace the approved predictor concept.
- Do not invent an endpoint, dataset ID, table ID, field, unit, or update schedule.
- A source page and a machine retrieval URL are different fields; provide both.
- Prefer a stable JSON or CSV endpoint. HTML or XLSX may be proposed only if no stable
  machine-readable source exists.
- Search official data.gov.sg and SingStat mirrors as well as the originating agency;
  a public display page alone is not a machine-readable retrieval endpoint.
- Describe uncertainty in unresolved_questions rather than guessing.
- Return every field in English and conform exactly to the supplied JSON schema.

SCHEMA MAPPING
- Use long_records when each row has an explicit period field and value field.
- Use wide_period_columns when periods are column names. For SingStat-style wide monthly
  data use wide_period_format=singstat_month; for quarterly use singstat_quarter.
- For a wide source, set series_field to the field selecting the series. The placeholder
  date_field_candidates and value_field_candidates must be ["__period_column__"] and
  ["__period_value__"].

STRUCTURAL SERIES PROFILE
- Classify the published series as stock, flow, rate, or index from its official definition.
- Do not propose an aggregation method, target frequency, change calculation, lag,
  interpolation rule, incomplete-period rule, or missing-value treatment. A later
  preparation-advisor stage makes those recommendations only after verified sources and
  confirmed project memory are available.

The program independently probes every retrieval URL. Official-domain, HTTP-access, and
machine-readable-format failures remain hard failures. Field-name mismatches are retained
as warnings because the later full-snapshot Mapping Agent owns the authoritative mapping."""


class DiscoveryClient(Protocol):
    def discover(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str,
        max_search_tool_calls: int,
    ) -> tuple[DataDiscoveryProposal, dict[str, Any], set[str], dict[str, Any]]: ...


class DiscoveryStructuredOutputError(ValueError):
    def __init__(self, message: str, *, raw_response: dict[str, Any], metadata: dict[str, Any]):
        super().__init__(message)
        self.raw_response = raw_response
        self.metadata = metadata


def _extract_urls(value: object) -> set[str]:
    urls: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, dict):
            if item.get("url"):
                urls.add(str(item["url"]))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return urls


def _parse_proposal(
    text: str, *, raw_response: dict[str, Any], metadata: dict[str, Any]
) -> tuple[DataDiscoveryProposal, bool]:
    try:
        return load_discovery_proposal(json.loads(text)), False
    except Exception:
        try:
            from json_repair import repair_json

            repaired = repair_json(text, return_objects=True)
            return load_discovery_proposal(repaired), True
        except Exception as exc:
            raise DiscoveryStructuredOutputError(
                "Provider output could not be repaired into a schema-valid data discovery proposal.",
                raw_response=raw_response,
                metadata=metadata,
            ) from exc


class GeminiDataDiscoveryClient:
    def __init__(self, *, api_key: str | None = None) -> None:
        from google import genai

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini data discovery.")
        self._client = genai.Client(api_key=key)

    def discover(self, **kwargs):
        interaction = self._client.interactions.create(
            model=kwargs["model"],
            system_instruction=(
                kwargs["instructions"]
                + f"\nUse no more than {kwargs['max_search_tool_calls']} Google Search tool calls."
            ),
            input=kwargs["input_text"],
            tools=[{"type": "google_search"}],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": DataDiscoveryProposal.model_json_schema(),
            },
            store=False,
        )
        if not interaction.output_text:
            raise RuntimeError("Gemini returned no data-discovery output text.")
        raw = interaction.model_dump(mode="json")
        metadata = {
            "provider": "gemini",
            "model": raw.get("model", kwargs["model"]),
            "interaction_id": raw.get("id"),
            "search_backend": "native_google_search",
            "usage": raw.get("usage") or {},
        }
        proposal, repaired = _parse_proposal(
            interaction.output_text,
            raw_response=raw,
            metadata=metadata,
        )
        metadata["structured_output_repaired"] = repaired
        return proposal, raw, _extract_urls(raw.get("steps", [])), metadata


def build_discovery_input(
    predictor: PredictorCandidate, scope: ApprovedResearchScope
) -> str:
    return "\n\n".join([
        "HUMAN-APPROVED PREDICTOR\n" + predictor.model_dump_json(indent=2),
        "HUMAN-APPROVED SCOPE\n" + scope.model_dump_json(indent=2),
        "Return a draft source proposal only. Human catalog approval occurs later.",
    ])


def _same_official_page(candidate_url: str, searched_urls: set[str]) -> bool:
    candidate = urlparse(candidate_url)
    candidate_path = candidate.path.rstrip("/")
    return any(
        urlparse(item).hostname == candidate.hostname
        and (
            urlparse(item).path.rstrip("/") == candidate_path
            or candidate_path in urlparse(item).path
            or urlparse(item).path.rstrip("/") in candidate_path
        )
        for item in searched_urls
    )


def validate_discovery(
    proposal: DataDiscoveryProposal,
    predictor: PredictorCandidate,
    probes: list[SourceProbeResult],
    *,
    searched_urls: set[str] | None = None,
) -> DataDiscoveryValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if proposal.predictor_id != predictor.predictor_id:
        errors.append("Discovery proposal does not match the approved predictor ID.")
    probe_by_id = {item.candidate_id: item for item in probes}
    scores: list[DiscoveryCandidateScore] = []
    for candidate in proposal.candidates:
        failures: list[str] = []
        try:
            validate_official_url(candidate.source_page_url)
            validate_official_url(candidate.retrieval_url)
        except ValueError as exc:
            failures.append(str(exc))
        probe = probe_by_id.get(candidate.candidate_id)
        if probe is None or probe.status != "pass":
            failures.append("The deterministic source probe did not pass.")
        elif not probe.date_field_matches or not probe.value_field_matches:
            warnings.append(
                f"{candidate.candidate_id}: discovery field hints did not match the sampled schema; authoritative mapping is deferred to the full-snapshot Mapping Agent."
            )
        if predictor.data_requirement.preferred_frequency not in {
            candidate.native_frequency,
            candidate.update_frequency,
        } and candidate.native_frequency not in predictor.data_requirement.acceptable_frequencies:
            warnings.append(
                f"{candidate.candidate_id}: source frequency requires human comparison with the approved data requirement."
            )
        if searched_urls and not _same_official_page(candidate.source_page_url, searched_urls):
            warnings.append(
                f"{candidate.candidate_id}: source page was not matched exactly in the provider search trace; the independent probe still governs accessibility."
            )
        breakdown = {
            "official_authority": 20 if not any("allowlist" in item for item in failures) else 0,
            "successful_probe": 25 if probe and probe.status == "pass" else 0,
            "schema_match": 20 if probe and probe.date_field_matches and probe.value_field_matches else 0,
            "frequency_suitability": 15 if candidate.native_frequency in predictor.data_requirement.acceptable_frequencies else 8,
            "machine_readability": 10 if candidate.source_type.value in {"datagov_json", "generic_json", "csv"} else 4,
            "point_in_time_documentation": 10,
        }
        scores.append(DiscoveryCandidateScore(
            candidate_id=candidate.candidate_id,
            total_score=sum(breakdown.values()),
            score_breakdown=breakdown,
            hard_gate_status="fail" if failures else "pass",
            hard_gate_failures=failures,
        ))
    if not any(item.hard_gate_status == "pass" for item in scores):
        errors.append("No discovered source passed the official-source and schema probe hard gates.")
    return DataDiscoveryValidation(
        automated_validation_status="fail" if errors else "pass",
        human_review_status="not_ready" if errors else "pending",
        errors=errors,
        warnings=warnings,
        candidate_scores=scores,
    )


def build_draft_entries(
    proposal: DataDiscoveryProposal,
    validation: DataDiscoveryValidation,
    probes: list[SourceProbeResult],
) -> list[DraftCatalogEntry]:
    passed = {
        item.candidate_id
        for item in validation.candidate_scores
        if item.hard_gate_status == "pass"
    }
    probe_by_id = {item.candidate_id: item for item in probes}
    entries: list[DraftCatalogEntry] = []
    for candidate in proposal.candidates:
        if candidate.candidate_id not in passed:
            continue
        probe = probe_by_id[candidate.candidate_id]
        wide = candidate.schema_orientation == "wide_period_columns"
        entries.append(DraftCatalogEntry(
            predictor_id=candidate.predictor_id,
            candidate_id=candidate.candidate_id,
            source_id=candidate.candidate_id,
            official_agency=candidate.official_agency,
            dataset_title=candidate.dataset_title,
            source_type=candidate.source_type,
            source_page_url=candidate.source_page_url,
            retrieval_url=candidate.retrieval_url,
            definition_url=candidate.definition_url,
            dataset_id=candidate.dataset_id,
            table_id=candidate.table_id,
            definition=candidate.definition,
            unit=candidate.unit,
            native_frequency=candidate.native_frequency,
            update_frequency=candidate.update_frequency,
            series_identifier=candidate.series_identifier,
            schema_orientation=candidate.schema_orientation,
            series_field=probe.series_field_match or candidate.series_field,
            wide_period_format=candidate.wide_period_format,
            proposed_date_field=(
                "__period_column__" if wide
                else probe.date_field_matches[0] if probe.date_field_matches
                else candidate.date_field_candidates[0]
            ),
            proposed_value_field=(
                "__period_value__" if wide
                else probe.value_field_matches[0] if probe.value_field_matches
                else candidate.value_field_candidates[0]
            ),
            exact_series_label=candidate.exact_series_label,
            series_type=candidate.series_type,
            point_in_time_notes=candidate.point_in_time_notes,
            limitations=candidate.limitations,
            probe=probe,
        ))
    return entries


class DataDiscoveryState(TypedDict, total=False):
    approved_scope: dict[str, Any]
    approved_predictors: list[dict[str, Any]]
    target_predictor_id: str
    discovery_provider: str
    discovery_model: str | None
    max_search_tool_calls: int
    max_discovery_attempts: int
    discovery_artifact_dir: str
    discovery_proposal: dict[str, Any]
    discovery_probes: list[dict[str, Any]]
    discovery_validation: dict[str, Any]
    draft_catalog_entries: list[dict[str, Any]]
    discovery_metadata: dict[str, Any]
    discovery_errors: list[str]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_data_discovery_node(
    client_factory: Callable[[], DiscoveryClient] | None = None,
    probe: Callable[[DataSourceCandidate], SourceProbeResult] = probe_data_source,
):
    def node(state: DataDiscoveryState) -> DataDiscoveryState:
        errors: list[str] = []
        raw: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        proposal: DataDiscoveryProposal | None = None
        probes: list[SourceProbeResult] = []
        validation: DataDiscoveryValidation | None = None
        drafts: list[DraftCatalogEntry] = []
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            scope = ApprovedResearchScope.model_validate(state["approved_scope"])
            predictors = [load_predictor_candidate(item) for item in state["approved_predictors"]]
            target = state["target_predictor_id"]
            predictor_by_id = {item.predictor_id: item for item in predictors}
            if target not in predictor_by_id:
                raise ValueError("target_predictor_id is not in the human-approved predictor set")
            provider = state.get("discovery_provider", "gemini")
            if provider != "gemini":
                raise ValueError("DataDiscoveryNode v1 currently supports provider='gemini'")
            model = state.get("discovery_model") or provider_spec("gemini").default_model
            client = client_factory() if client_factory else GeminiDataDiscoveryClient()
            maximum_attempts = state.get("max_discovery_attempts", 2)
            if not isinstance(maximum_attempts, int) or not 1 <= maximum_attempts <= 3:
                raise ValueError("max_discovery_attempts must be an integer from 1 to 3")
            base_input = build_discovery_input(predictor_by_id[target], scope)
            feedback = ""
            raw_attempts: list[dict[str, Any]] = []
            for attempt_number in range(1, maximum_attempts + 1):
                proposal, attempt_raw, searched_urls, attempt_metadata = client.discover(
                    instructions=DISCOVERY_INSTRUCTIONS,
                    input_text=base_input + feedback,
                    model=model,
                    max_search_tool_calls=state.get("max_search_tool_calls", 12),
                )
                raw_attempts.append(attempt_raw)
                metadata = attempt_metadata
                probes = [probe(candidate) for candidate in proposal.candidates]
                validation = validate_discovery(
                    proposal,
                    predictor_by_id[target],
                    probes,
                    searched_urls=searched_urls,
                )
                if validation.automated_validation_status == "pass":
                    break
                if attempt_number < maximum_attempts:
                    failure_bundle = {
                        "validation_errors": validation.errors,
                        "probe_errors": {
                            item.candidate_id: item.errors for item in probes
                        },
                    }
                    feedback = (
                        "\n\nPREVIOUS ATTEMPT FAILED DETERMINISTIC PROBING\n"
                        + json.dumps(failure_bundle, indent=2)
                        + "\nFind a different official machine-readable source or correct "
                        "the endpoint and schema mapping. Do not repeat a failed display page."
                    )
            raw = {"attempts": raw_attempts}
            metadata["discovery_attempt_count"] = len(raw_attempts)
            drafts = build_draft_entries(proposal, validation, probes)
        except Exception as exc:
            if isinstance(exc, DiscoveryStructuredOutputError):
                raw = exc.raw_response
                metadata = exc.metadata
            errors.append(f"{type(exc).__name__}: {exc}")

        metadata = {
            "execution_status": "fail" if errors else "success",
            "prompt_version": DISCOVERY_PROMPT_VERSION,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
        validation_dict = validation.model_dump(mode="json") if validation else {
            "automated_validation_status": "not_run",
            "human_review_status": "not_ready",
            "errors": errors,
            "warnings": [],
            "candidate_scores": [],
        }
        result: DataDiscoveryState = {
            "discovery_proposal": proposal.model_dump(mode="json") if proposal else {},
            "discovery_probes": [item.model_dump(mode="json") for item in probes],
            "discovery_validation": validation_dict,
            "draft_catalog_entries": [item.model_dump(mode="json") for item in drafts],
            "discovery_metadata": metadata,
            "discovery_errors": errors,
        }
        if state.get("discovery_artifact_dir"):
            directory = Path(state["discovery_artifact_dir"])
            _write_json(directory / "discovery_proposal.json", result["discovery_proposal"])
            _write_json(directory / "source_probes.json", result["discovery_probes"])
            _write_json(directory / "discovery_validation.json", validation_dict)
            _write_json(directory / "draft_catalog_entries.json", {
                "catalog_status": "draft_unapproved",
                "entries": result["draft_catalog_entries"],
            })
            _write_json(directory / "discovery_metadata.json", metadata)
            _write_json(directory / "discovery_raw_response.json", raw)
            _write_json(directory / "discovery_errors.json", {"errors": errors})
        return result

    return node


data_discovery_node = make_data_discovery_node()
