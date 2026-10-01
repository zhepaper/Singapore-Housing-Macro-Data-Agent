from __future__ import annotations

import re
from typing import Any, Iterable

from housing_agent.models import Frequency, Observation


MISSING_MARKERS = {"", "na", "n.a.", "-", ".."}
MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def clean_label(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def parse_number(value: object) -> float | None:
    text = str(value).strip()
    if text.lower() in MISSING_MARKERS:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Ambiguous numeric value: {value!r}") from exc


def canonical_period(raw: str) -> tuple[str, Frequency]:
    if match := re.fullmatch(r"(\d{4})-Q([1-4])", raw):
        return f"{match.group(1)}-Q{match.group(2)}", "quarterly"
    if match := re.fullmatch(r"(\d{4})([1-4])Q", raw):
        return f"{match.group(1)}-Q{match.group(2)}", "quarterly"
    if match := re.fullmatch(r"(\d{4})([A-Z][a-z]{2})", raw):
        month = MONTHS.get(match.group(2))
        if month:
            return f"{match.group(1)}-{month}", "monthly"
    if re.fullmatch(r"\d{4}", raw):
        return raw, "annual"
    raise ValueError(f"Unsupported source period: {raw!r}")


def _role(source: dict[str, Any]) -> str:
    return "benchmark" if source["role"] == "benchmark" else "predictor"


def _observation(
    source: dict[str, Any], label: str, raw_period: str, raw_value: object
) -> Observation:
    period, frequency = canonical_period(raw_period)
    value = parse_number(raw_value)
    return Observation(
        source_id=source["source_id"],
        series_id=f"{source['source_id']}__{slug(label)}",
        series_label=label,
        period=period,
        frequency=frequency,
        value=value,
        unit=source["unit"],
        market=source["market"],
        role=_role(source),
        observation_status="missing_at_source" if value is None else "observed",
    )


def _selected_wide_rows(
    records: list[dict[str, Any]], source: dict[str, Any]
) -> Iterable[tuple[dict[str, Any], str]]:
    series_field = source["series_field"]
    selected = {clean_label(item) for item in source.get("selected_series_labels", [])}
    group = source.get("series_group")
    in_group = False

    for record in records:
        label = clean_label(record.get(series_field, ""))
        if group:
            if label.startswith("Total "):
                in_group = label == group
            if in_group:
                qualified = label if label == group else f"{group} / {label}"
                yield record, qualified
        elif label in selected:
            yield record, label


def normalize_datagov(payload: dict[str, Any], source: dict[str, Any]) -> list[Observation]:
    if payload.get("success") is not True:
        raise ValueError("data.gov.sg response success is not true")
    records = payload.get("result", {}).get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("data.gov.sg response has no records")

    observations: list[Observation] = []
    if source.get("period_field") and source.get("value_field"):
        selector = source.get("selector", {})
        selected_records = [
            row for row in records
            if all(row.get(key) == value for key, value in selector.items())
        ]
        if not selected_records:
            raise ValueError(f"No records match selector {selector}")
        label = " / ".join(str(value) for value in selector.values()) or source["source_id"]
        for row in selected_records:
            observations.append(
                _observation(source, label, row[source["period_field"]], row[source["value_field"]])
            )
    else:
        metadata = {"_id", source["series_field"]}
        selected_rows = list(_selected_wide_rows(records, source))
        if not selected_rows:
            raise ValueError("Configured series selection returned no rows")
        for row, label in selected_rows:
            for raw_period, raw_value in row.items():
                if raw_period in metadata:
                    continue
                observations.append(_observation(source, label, raw_period, raw_value))

    keys = [(item.series_id, item.period) for item in observations]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate normalized series-period observations")
    return sorted(observations, key=lambda item: (item.series_id, item.period))

