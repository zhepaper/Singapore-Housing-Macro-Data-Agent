from __future__ import annotations

import csv
import json
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from housing_agent.processing.models import (
    CanonicalObservation,
    FrozenDataPlan,
    FrozenSeriesPlan,
)


class MappingFailure(ValueError):
    """The approved mapping no longer describes the raw snapshot."""


MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}


def _json_value(payload: Any, path: Iterable[str | int]) -> Any:
    current = payload
    for part in path:
        try:
            current = current[part]
        except (KeyError, IndexError, TypeError) as exc:
            raise MappingFailure(f"records_path component {part!r} does not exist") from exc
    return current


def get_record_value(record: dict[str, Any], field_path: str) -> Any:
    """Resolve an exact key first, then a dotted nested-field path."""
    if field_path in record:
        return record[field_path]
    current: Any = record
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _load_xlsx(path: Path, sheet_name: str | None, header_row: int) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise RuntimeError("openpyxl is required to normalize xlsx snapshots") from exc
    workbook = load_workbook(path, read_only=True, data_only=True)
    if sheet_name and sheet_name not in workbook.sheetnames:
        raise MappingFailure(f"approved Excel sheet {sheet_name!r} no longer exists")
    sheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    for _ in range(header_row - 1):
        next(rows, None)
    headers = next(rows, None)
    if not headers:
        raise MappingFailure("Excel snapshot has no approved header row")
    names = [str(value).strip() if value is not None else "" for value in headers]
    return [dict(zip(names, row, strict=False)) for row in rows]


def load_mapping_records(
    snapshot_path: str | Path, contract: Any
) -> list[dict[str, Any]]:
    """Load the record set selected by an approved or proposed mapping contract."""
    path = Path(snapshot_path)
    if contract.source_format == "json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        selected = _json_value(payload, contract.records_path)
        if isinstance(selected, dict):
            records = [selected]
        elif isinstance(selected, list):
            records = selected
        else:
            raise MappingFailure("approved records_path does not resolve to an object or list")
    elif contract.source_format == "csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
    else:
        records = _load_xlsx(path, contract.sheet_name, contract.header_row)
    records = [item for item in records if isinstance(item, dict)]
    if contract.series_filter_field:
        if not any(
            get_record_value(item, contract.series_filter_field) is not None
            for item in records
        ):
            raise MappingFailure(
                f"approved series filter field {contract.series_filter_field!r} is missing"
            )
        records = [
            item for item in records
            if str(get_record_value(item, contract.series_filter_field))
            == contract.series_filter_value
        ]
    for field, expected in contract.additional_series_filters.items():
        if not any(get_record_value(item, field) is not None for item in records):
            raise MappingFailure(f"approved additional series filter field {field!r} is missing")
        records = [
            item for item in records
            if str(get_record_value(item, field)) == expected
        ]
    if not records:
        raise MappingFailure("approved mapping selected no records")
    return records


def load_raw_records(series: FrozenSeriesPlan) -> list[dict[str, Any]]:
    return load_mapping_records(series.snapshot_path, series.mapping_contract)


def parse_decimal(value: Any, missing_markers: tuple[str, ...]) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {marker.strip().lower() for marker in missing_markers}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()").replace(",", "").replace("%", "").strip()
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise MappingFailure(f"value {text!r} cannot be parsed as a decimal") from exc
    return -parsed if negative else parsed


def parse_period(value: Any, frequency: str) -> tuple[str, date]:
    text = str(value).strip()
    if frequency == "annual":
        match = re.fullmatch(r"(\d{4})", text)
        if match:
            year = int(match.group(1))
            return str(year), date(year, 12, 31)
    elif frequency == "quarterly":
        match = re.fullmatch(r"(\d{4})[- ]?Q([1-4])", text, re.IGNORECASE)
        singstat_match = re.fullmatch(r"(\d{4})([1-4])Q", text, re.IGNORECASE)
        if match:
            year, quarter = int(match.group(1)), int(match.group(2))
            month = quarter * 3
            return f"{year}-Q{quarter}", date(year, month, monthrange(year, month)[1])
        if singstat_match:
            year, quarter = int(singstat_match.group(1)), int(singstat_match.group(2))
            month = quarter * 3
            return f"{year}-Q{quarter}", date(year, month, monthrange(year, month)[1])
    elif frequency == "monthly":
        numeric = re.fullmatch(r"(\d{4})[-/]?(0?[1-9]|1[0-2])", text)
        named = re.fullmatch(r"(\d{4})[- ]?([A-Za-z]{3})", text)
        if numeric:
            year, month = int(numeric.group(1)), int(numeric.group(2))
            return f"{year}-{month:02d}", date(year, month, monthrange(year, month)[1])
        if named and named.group(2).lower() in MONTHS:
            year, month = int(named.group(1)), MONTHS[named.group(2).lower()]
            return f"{year}-{month:02d}", date(year, month, monthrange(year, month)[1])
    raise MappingFailure(f"period {text!r} does not match {frequency} frequency")


def _parse_release_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise MappingFailure(f"release date {value!r} is not ISO YYYY-MM-DD") from exc


def _eligibility(
    period_end: date,
    value: Decimal | None,
    available_date: date,
    plan: FrozenDataPlan,
) -> str:
    if period_end < plan.historical_start_date:
        return "before_window"
    if value is None:
        return "missing_at_source"
    if period_end > plan.historical_end_date or available_date > plan.reporting_as_of_date:
        return "after_as_of"
    return "eligible"


def _emit(
    *,
    plan: FrozenDataPlan,
    series: FrozenSeriesPlan,
    period_value: Any,
    raw_value: Any,
    raw_reference: str,
    release_value: Any = None,
) -> CanonicalObservation:
    period, period_end = parse_period(period_value, series.observation_frequency)
    parsed = parse_decimal(raw_value, series.mapping_contract.missing_markers)
    scaled = parsed * series.mapping_contract.unit_scale if parsed is not None else None
    release_date = _parse_release_date(release_value)
    available_date = release_date or period_end + timedelta(days=series.release_lag_days)
    return CanonicalObservation(
        source_id=series.source_id,
        series_id=series.series_id,
        series_label=series.series_label,
        period=period,
        value=scaled,
        unit=series.unit,
        observation_frequency=series.observation_frequency,
        update_frequency=series.update_frequency,
        portfolio_role=series.portfolio_role,
        market_role=series.market_role,
        eligibility_status=_eligibility(period_end, scaled, available_date, plan),
        raw_snapshot_sha256=series.snapshot_sha256,
        raw_record_reference=raw_reference,
        original_period=str(period_value),
        original_value=None if raw_value is None else str(raw_value),
        release_date=release_date,
        available_date=available_date,
        source_periods=(period,),
        input_series_ids=(series.series_id,),
    )


def normalize_series(plan: FrozenDataPlan, series: FrozenSeriesPlan) -> list[CanonicalObservation]:
    records = load_raw_records(series)
    contract = series.mapping_contract
    output: list[CanonicalObservation] = []
    if contract.layout == "long":
        assert contract.date_field and contract.value_field
        for field in (contract.date_field, contract.value_field):
            if not any(get_record_value(record, field) is not None for record in records):
                raise MappingFailure(f"approved field {field!r} is missing")
        for index, record in enumerate(records):
            output.append(_emit(
                plan=plan,
                series=series,
                period_value=get_record_value(record, contract.date_field),
                raw_value=get_record_value(record, contract.value_field),
                release_value=(
                    get_record_value(record, contract.release_date_field)
                    if contract.release_date_field else None
                ),
                raw_reference=f"record:{index}/field:{contract.value_field}",
            ))
    else:
        assert contract.wide_period_pattern
        try:
            pattern = re.compile(contract.wide_period_pattern)
        except re.error as exc:
            raise MappingFailure("approved wide_period_pattern is invalid") from exc
        for index, record in enumerate(records):
            period_fields = [field for field in record if pattern.fullmatch(str(field))]
            if not period_fields:
                raise MappingFailure("approved wide mapping found no period fields")
            for field in period_fields:
                output.append(_emit(
                    plan=plan,
                    series=series,
                    period_value=field,
                    raw_value=record.get(field),
                    raw_reference=f"record:{index}/field:{field}",
                ))
    return sorted(output, key=lambda item: (item.period, item.raw_record_reference))


def normalize_plan(plan: FrozenDataPlan) -> list[CanonicalObservation]:
    output: list[CanonicalObservation] = []
    for series in sorted(plan.series, key=lambda item: (item.source_id, item.series_id)):
        output.extend(normalize_series(plan, series))
    return output
