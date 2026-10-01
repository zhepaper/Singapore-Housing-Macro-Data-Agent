#!/usr/bin/env python3
"""Run a read-only connectivity and minimum-contract check for every source.

The catalogue file uses JSON syntax, which is a valid YAML 1.2 subset. This lets
the spike run with the Python standard library before project dependencies exist.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_AGENT = "Singapore-Housing-Macro-Data-Agent/0.1 (+public-data-research)"


@dataclass
class CheckResult:
    source_id: str
    status: str
    http_status: int | None
    content_type: str | None
    bytes_received: int
    raw_snapshot_path: str | None
    sha256: str | None
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config/data_catalog.yaml"),
        help="Path to the JSON-compatible YAML data catalogue.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/raw"),
        help="Directory under which a timestamped spike run is written.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--source-id",
        action="append",
        dest="source_ids",
        help="Check only this source ID; repeat to select more than one source.",
    )
    return parser.parse_args()


def load_catalog(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    if catalog.get("catalog_version") != 1:
        raise ValueError("Unsupported or missing catalog_version")
    if not catalog.get("sources"):
        raise ValueError("Catalogue contains no sources")
    return catalog


def fetch(url: str, timeout: float) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        content_type = response.headers.get_content_type()
        body = response.read()
    return status, content_type, body


def rows_from_singstat(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("StatusCode") != 200:
        raise ValueError(f"SingStat body StatusCode={payload.get('StatusCode')!r}")
    data = payload.get("Data")
    if not isinstance(data, dict) or not isinstance(data.get("row"), list):
        raise ValueError("SingStat response missing Data.row")
    return data["row"]


def validate_datagov(payload: dict[str, Any], source: dict[str, Any]) -> str:
    if payload.get("success") is not True:
        raise ValueError("data.gov.sg response success is not true")
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        raise ValueError("data.gov.sg response missing result.records")
    records = result["records"]
    if not records:
        raise ValueError("data.gov.sg returned no records")
    selector = source.get("selector", {})
    matching = [row for row in records if all(row.get(key) == value for key, value in selector.items())]
    if not matching:
        raise ValueError(f"No records match selector {selector}")
    series_field = source.get("series_field")
    if series_field:
        labels = [re.sub(r"\s+", " ", str(row.get(series_field, ""))).strip() for row in records]
        exact = source.get("exact_series_label")
        if exact and exact not in labels:
            raise ValueError(f"Exact series label not found in {series_field}: {exact!r}")
        terms = [term.lower() for term in source.get("required_series_terms", [])]
        if terms and not any(all(term in label.lower() for term in terms) for label in labels):
            raise ValueError(f"No {series_field} label contains all required terms: {terms}")
        term_groups = source.get("required_series_term_groups", [])
        missing_groups = [
            group
            for group in term_groups
            if not any(all(term.lower() in label.lower() for term in group) for label in labels)
        ]
        if missing_groups:
            raise ValueError(f"No {series_field} labels match required term groups: {missing_groups}")
    return f"{len(records)} records; {len(matching)} match selector"


def validate_singstat(payload: dict[str, Any], source: dict[str, Any]) -> str:
    rows = rows_from_singstat(payload)
    labels = [str(row.get("rowText", "")) for row in rows]
    exact = source.get("exact_series_label")
    if exact and exact not in labels:
        raise ValueError(f"Exact series label not found: {exact!r}")
    terms = source.get("required_series_terms", [])
    missing_terms = [term for term in terms if not any(term.lower() in label.lower() for label in labels)]
    if missing_terms:
        raise ValueError(f"Required series terms not found: {missing_terms}")
    populated_rows = sum(bool(row.get("columns")) for row in rows)
    if populated_rows == 0:
        raise ValueError("SingStat returned no observation columns")
    return f"{len(rows)} series; {populated_rows} contain observations"


def visible_text(body: bytes) -> str:
    decoded = body.decode("utf-8", errors="replace")
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", decoded, flags=re.I | re.S)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def validate_mom_report(body: bytes, source: dict[str, Any]) -> str:
    text = visible_text(body)
    missing = [term for term in source.get("required_text_terms", []) if term.lower() not in text.lower()]
    if missing:
        raise ValueError(f"Required report terms not found: {missing}")
    values = re.findall(
        r"non-resident employment(?:\s+(?:growth|change))?[^.]{0,160}?(?:grew|increased|declined|fell|change(?:d)?)\s+(?:by\s+|\()?(-?[\d,]+)",
        text,
        flags=re.I,
    )
    if not values:
        raise ValueError("Report found, but no non-resident employment value matched the spike pattern")
    return f"report terms present; candidate non-resident values={values[:3]}"


def validate(source: dict[str, Any], body: bytes) -> str:
    source_type = source["source_type"]
    if source_type in {"datagov_json", "singstat_json"}:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Expected JSON but received invalid JSON: {exc}") from exc
        if source_type == "datagov_json":
            return validate_datagov(payload, source)
        return validate_singstat(payload, source)
    if source_type == "mom_report_html":
        return validate_mom_report(body, source)
    raise ValueError(f"Unsupported source_type={source_type!r}")


def extension_for(content_type: str | None, source_type: str) -> str:
    if content_type == "application/json" or source_type.endswith("_json"):
        return ".json"
    if content_type == "application/pdf":
        return ".pdf"
    return ".html"


def check_source(source: dict[str, Any], run_dir: Path, timeout: float) -> CheckResult:
    source_id = source["source_id"]
    try:
        status, content_type, body = fetch(source["retrieval_url"], timeout)
        suffix = extension_for(content_type, source["source_type"])
        raw_path = run_dir / f"{source_id}{suffix}"
        raw_path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        detail = validate(source, body)
        return CheckResult(
            source_id=source_id,
            status="pass",
            http_status=status,
            content_type=content_type,
            bytes_received=len(body),
            raw_snapshot_path=str(raw_path),
            sha256=digest,
            detail=detail,
        )
    except urllib.error.HTTPError as exc:
        return CheckResult(source_id, "fail", exc.code, exc.headers.get_content_type(), 0, None, None, str(exc))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return CheckResult(source_id, "fail", None, None, 0, None, None, str(exc))


def print_table(results: list[CheckResult]) -> None:
    widths = {
        "source": max(len("source"), *(len(item.source_id) for item in results)),
        "status": max(len("status"), *(len(item.status) for item in results)),
    }
    print(f"{'source':<{widths['source']}}  {'status':<{widths['status']}}  http  bytes     detail")
    print(f"{'-' * widths['source']}  {'-' * widths['status']}  ----  --------  ------")
    for item in results:
        http_status = str(item.http_status) if item.http_status is not None else "-"
        print(
            f"{item.source_id:<{widths['source']}}  {item.status:<{widths['status']}}  "
            f"{http_status:<4}  {item.bytes_received:<8}  {item.detail}"
        )


def main() -> int:
    args = parse_args()
    catalog = load_catalog(args.catalog)
    sources = catalog["sources"]
    if args.source_ids:
        requested = set(args.source_ids)
        sources = [source for source in sources if source["source_id"] in requested]
        found = {source["source_id"] for source in sources}
        missing = sorted(requested - found)
        if missing:
            raise ValueError(f"Unknown source IDs: {missing}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_root / f"spike_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)

    results = [check_source(source, run_dir, args.timeout) for source in sources]
    manifest = {
        "run_id": run_id,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "catalog_path": str(args.catalog),
        "results": [asdict(result) for result in results],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print_table(results)
    print(f"\nManifest: {run_dir / 'manifest.json'}")
    return 0 if all(result.status == "pass" for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
