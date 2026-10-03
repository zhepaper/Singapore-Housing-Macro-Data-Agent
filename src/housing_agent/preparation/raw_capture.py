from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from housing_agent.onboarding.models import ApprovedCatalogEntry
from housing_agent.preparation.models import RawSnapshotEvidence
from housing_agent.retrieval import USER_AGENT, validate_official_url


MONTH_NUMBER = {
    name: index for index, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")


def _content_type(headers: Any) -> str | None:
    if hasattr(headers, "get_content_type"):
        return headers.get_content_type()
    value = headers.get("Content-Type") if headers else None
    return value.split(";", 1)[0].strip() if value else None


def _json_records(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        records = payload["result"].get("records", [])
    elif isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = [payload]
    else:
        records = []
    return [item for item in records if isinstance(item, dict)]


def _period_key(value: str) -> tuple[int, int]:
    if re.fullmatch(r"\d{4}Q[1-4]", value):
        return int(value[:4]), int(value[-1]) * 3
    return int(value[:4]), MONTH_NUMBER[value[4:]]


def _inspect(
    body: bytes, content_type: str | None, approved: ApprovedCatalogEntry
) -> tuple[list[dict[str, Any]], str | None, str | None, int | None]:
    entry = approved.entry
    if content_type == "application/json" or entry.source_type.value.endswith("json"):
        records = _json_records(json.loads(body))
    elif content_type in {"text/csv", "application/csv"} or entry.source_type.value == "csv":
        records = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    else:
        return [], None, None, None
    if entry.series_field and entry.exact_series_label:
        selected = [
            item for item in records
            if str(item.get(entry.series_field)) == entry.exact_series_label
        ]
        if selected:
            records = selected
    if not records:
        return [], None, None, None
    if entry.schema_orientation == "wide_period_columns":
        record = records[0]
        period_fields = [
            key for key in record
            if re.fullmatch(r"\d{4}(?:Q[1-4]|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", key)
        ]
        observed = [
            period for period in period_fields
            if record.get(period) is not None and str(record.get(period)).strip() not in {"", "-", "..", "na", "n.a."}
        ]
        ordered = sorted(observed, key=_period_key)
        recent = list(reversed(ordered[-3:]))
        return (
            [{"period": period, "value": record.get(period)} for period in recent],
            ordered[0] if ordered else None,
            ordered[-1] if ordered else None,
            len(ordered),
        )
    date_field = entry.proposed_date_field
    value_field = entry.proposed_value_field
    observed = [
        {"period": item.get(date_field), "value": item.get(value_field)}
        for item in records
        if item.get(date_field) is not None and item.get(value_field) is not None
    ]
    ordered = sorted(observed, key=lambda item: str(item["period"]))
    return (
        list(reversed(ordered[-3:])),
        str(ordered[0]["period"]) if ordered else None,
        str(ordered[-1]["period"]) if ordered else None,
        len(ordered),
    )


def capture_raw_snapshot(
    approved: ApprovedCatalogEntry,
    *,
    snapshot_directory: Path,
    timeout: float = 30.0,
    max_bytes: int = 20_000_000,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> RawSnapshotEvidence:
    entry = approved.entry
    retrieved_at = datetime.now(timezone.utc)
    errors: list[str] = []
    status: int | None = None
    content_type: str | None = None
    body = b""
    snapshot_path: Path | None = None
    digest: str | None = None
    preview: list[dict[str, Any]] = []
    observed_period_start: str | None = None
    observed_period_end: str | None = None
    non_null_observation_count: int | None = None
    try:
        validate_official_url(entry.retrieval_url)
        request = urllib.request.Request(
            entry.retrieval_url,
            headers={
                "Accept": "application/json,text/csv;q=0.9,*/*;q=0.5",
                "User-Agent": USER_AGENT,
            },
        )
        with opener(request, timeout=timeout) as response:
            status = int(response.status)
            validate_official_url(response.geturl())
            content_type = _content_type(response.headers)
            body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"raw response exceeds {max_bytes} bytes")
        if not body:
            raise ValueError("raw response is empty")
        (
            preview,
            observed_period_start,
            observed_period_end,
            non_null_observation_count,
        ) = _inspect(body, content_type, approved)
        if not preview:
            raise ValueError("raw response did not yield a preview for the approved series mapping")
        digest = hashlib.sha256(body).hexdigest()
        extension = ".json" if content_type == "application/json" else ".csv" if content_type in {"text/csv", "application/csv"} else ".bin"
        snapshot_directory.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_directory / f"{_safe_name(entry.source_id)}_{digest[:12]}{extension}"
        snapshot_path.write_bytes(body)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return RawSnapshotEvidence(
        source_id=entry.source_id,
        status="fail" if errors else "pass",
        retrieval_url=entry.retrieval_url,
        retrieved_at=retrieved_at,
        http_status=status,
        content_type=content_type,
        byte_count=len(body),
        sha256=digest,
        snapshot_path=str(snapshot_path) if snapshot_path else None,
        preview_records=preview,
        observed_period_start=observed_period_start,
        observed_period_end=observed_period_end,
        non_null_observation_count=non_null_observation_count,
        errors=errors,
    )


def capture_unmapped_raw_snapshot(
    approved: ApprovedCatalogEntry,
    *,
    snapshot_directory: Path,
    timeout: float = 30.0,
    max_bytes: int = 20_000_000,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> RawSnapshotEvidence:
    """Preserve an approved source before a Mapping Contract exists.

    Unlike ``capture_raw_snapshot``, this function does not require a mapped preview. The
    deterministic SchemaProfiler and MappingExecutor perform structural inspection later.
    """
    entry = approved.entry
    retrieved_at = datetime.now(timezone.utc)
    errors: list[str] = []
    status: int | None = None
    content_type: str | None = None
    body = b""
    snapshot_path: Path | None = None
    digest: str | None = None
    try:
        validate_official_url(entry.retrieval_url)
        request = urllib.request.Request(
            entry.retrieval_url,
            headers={
                "Accept": (
                    "application/json,text/csv;q=0.9,"
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;q=0.8,"
                    "*/*;q=0.5"
                ),
                "User-Agent": USER_AGENT,
            },
        )
        with opener(request, timeout=timeout) as response:
            status = int(response.status)
            validate_official_url(response.geturl())
            content_type = _content_type(response.headers)
            body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"raw response exceeds {max_bytes} bytes")
        if not body:
            raise ValueError("raw response is empty")
        digest = hashlib.sha256(body).hexdigest()
        format_value = entry.source_type.value
        if format_value.endswith("json") or content_type == "application/json":
            extension = ".json"
        elif format_value == "csv" or content_type in {"text/csv", "application/csv"}:
            extension = ".csv"
        elif format_value == "xlsx" or content_type in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }:
            extension = ".xlsx"
        else:
            extension = ".bin"
        snapshot_directory.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_directory / f"{_safe_name(entry.source_id)}_{digest[:12]}{extension}"
        snapshot_path.write_bytes(body)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return RawSnapshotEvidence(
        source_id=entry.source_id,
        status="fail" if errors else "pass",
        retrieval_url=entry.retrieval_url,
        retrieved_at=retrieved_at,
        http_status=status,
        content_type=content_type,
        byte_count=len(body),
        sha256=digest,
        snapshot_path=str(snapshot_path) if snapshot_path else None,
        preview_records=[],
        errors=errors,
    )
