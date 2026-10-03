from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from housing_agent.onboarding.mapping_models import (
    MappedValue,
    MappingExecutionReport,
    MappingProposal,
    RawSchemaProfile,
)
from housing_agent.processing.normalization import (
    MappingFailure,
    get_record_value,
    load_mapping_records,
    parse_decimal,
    parse_period,
)


def validate_mapping_against_profile(
    proposal: MappingProposal, profile: RawSchemaProfile
) -> list[str]:
    contract = proposal.mapping_contract
    errors: list[str] = []
    if proposal.source_id != profile.source_id:
        errors.append("Proposal source_id does not match the raw schema profile.")
    if contract.source_format != profile.source_format:
        errors.append(
            f"Mapping format {contract.source_format!r} differs from profiled format {profile.source_format!r}."
        )
    table = next(
        (item for item in profile.tables if item.location == proposal.selected_table_location),
        None,
    )
    if table is None:
        errors.append("selected_table_location does not exist in the schema profile.")
        return errors
    if tuple(contract.records_path) != tuple(table.records_path):
        errors.append("Mapping records_path differs from the selected profiled table.")
    if contract.source_format == "xlsx":
        if contract.sheet_name != table.sheet_name:
            errors.append("Mapping sheet_name differs from the selected profiled sheet.")
        if contract.header_row != table.header_row:
            errors.append("Mapping header_row differs from the profiled header row.")
    fields = {item.path for item in table.fields}
    for name, value in (
        ("date_field", contract.date_field),
        ("value_field", contract.value_field),
        ("series_filter_field", contract.series_filter_field),
        ("release_date_field", contract.release_date_field),
    ):
        if value and value not in fields:
            errors.append(f"{name} {value!r} is absent from the selected table profile.")
    if contract.layout != table.likely_layout and table.likely_layout != "unknown":
        errors.append(
            f"Mapping layout {contract.layout!r} conflicts with profiled layout {table.likely_layout!r}."
        )
    if contract.layout == "wide" and contract.wide_period_pattern:
        try:
            pattern = re.compile(contract.wide_period_pattern)
        except re.error as exc:
            errors.append(f"wide_period_pattern is invalid: {exc}")
        else:
            if not any(pattern.fullmatch(field) for field in fields):
                errors.append("wide_period_pattern matches no profiled field.")
    return errors


def execute_mapping(
    *,
    proposal: MappingProposal,
    profile: RawSchemaProfile,
    observation_frequency: str,
    allowed_unit_scales: tuple[str, ...] = ("1",),
    max_observations_in_report: int = 1000,
) -> MappingExecutionReport:
    contract = proposal.mapping_contract
    errors = validate_mapping_against_profile(proposal, profile)
    if str(contract.unit_scale) not in set(allowed_unit_scales):
        errors.append(
            f"unit_scale {contract.unit_scale} is not among the documented allowed scales {list(allowed_unit_scales)}."
        )
    warnings: list[str] = []
    observations: list[MappedValue] = []
    selected_count = 0
    extracted_count = 0
    all_periods: list[str] = []
    all_non_null = 0
    all_missing = 0
    if not errors:
        try:
            records = load_mapping_records(profile.snapshot_path, contract)
            selected_count = len(records)
            raw_items: list[tuple[Any, Any, str]] = []
            if contract.layout == "long":
                assert contract.date_field and contract.value_field
                raw_items = [
                    (
                        get_record_value(record, contract.date_field),
                        get_record_value(record, contract.value_field),
                        f"record:{index}/field:{contract.value_field}",
                    )
                    for index, record in enumerate(records)
                ]
            else:
                assert contract.wide_period_pattern
                pattern = re.compile(contract.wide_period_pattern)
                for index, record in enumerate(records):
                    for field, value in record.items():
                        if pattern.fullmatch(str(field)):
                            raw_items.append((field, value, f"record:{index}/field:{field}"))
            extracted_count = len(raw_items)
            if not raw_items:
                errors.append("Mapping extracted no candidate observations.")
            for raw_period, raw_value, reference in raw_items:
                try:
                    period, _ = parse_period(raw_period, observation_frequency)
                except Exception as exc:
                    errors.append(f"{reference}: invalid period {raw_period!r}: {exc}")
                    period = None
                try:
                    value = parse_decimal(raw_value, contract.missing_markers)
                    scaled = value * contract.unit_scale if value is not None else None
                except Exception as exc:
                    errors.append(f"{reference}: invalid value {raw_value!r}: {exc}")
                    scaled = None
                    period = None
                if len(observations) < max_observations_in_report:
                    observations.append(MappedValue(
                        period=period,
                        value=str(scaled) if scaled is not None else None,
                        raw_period=str(raw_period),
                        raw_value=None if raw_value is None else str(raw_value),
                        raw_record_reference=reference,
                    ))
                if period is not None:
                    all_periods.append(period)
                    if scaled is None:
                        all_missing += 1
                    else:
                        all_non_null += 1
            if len(raw_items) > max_observations_in_report:
                warnings.append(
                    f"Observation preview truncated to {max_observations_in_report} rows; validation used all extracted rows."
                )
        except MappingFailure as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    valid_periods = all_periods
    counts = Counter(valid_periods)
    duplicates = sorted(period for period, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"Mapping produced duplicate periods: {duplicates[:20]}")
    parsed_count = len(valid_periods)
    non_null = all_non_null
    missing = all_missing
    if parsed_count < 2:
        errors.append("Mapping must produce at least two valid observations.")
    if non_null < 2:
        errors.append("Mapping must produce at least two non-null observations.")
    if extracted_count and parsed_count != extracted_count:
        errors.append(
            f"Raw-to-mapped reconciliation failed: extracted={extracted_count}, parsed={parsed_count}."
        )
    return MappingExecutionReport(
        source_id=proposal.source_id,
        series_id=proposal.series_id,
        status="fail" if errors else "pass",
        selected_record_count=selected_count,
        extracted_observation_count=extracted_count,
        parsed_observation_count=parsed_count,
        non_null_observation_count=non_null,
        missing_observation_count=missing,
        duplicate_periods=duplicates,
        observed_period_start=min(valid_periods) if valid_periods else None,
        observed_period_end=max(valid_periods) if valid_periods else None,
        observations=observations,
        errors=errors,
        warnings=warnings,
    )
