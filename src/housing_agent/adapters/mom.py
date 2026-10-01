from __future__ import annotations

import html
import re

from housing_agent.models import Observation


def visible_text(body: bytes) -> str:
    decoded = body.decode("utf-8", errors="replace")
    decoded = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", decoded, flags=re.I | re.S)
    decoded = re.sub(r"<[^>]+>", " ", decoded)
    return re.sub(r"\s+", " ", html.unescape(decoded)).strip()


def previous_quarter(year: int, quarter: int) -> str:
    if quarter == 1:
        return f"{year - 1}-Q4"
    return f"{year}-Q{quarter - 1}"


def parse_mom_non_resident_employment(body: bytes, source: dict[str, object]) -> list[Observation]:
    text = visible_text(body)
    quarter_match = re.search(r"expanded\s+by\s+[\d,]+\s+in\s+([1-4])Q\s+(\d{4})", text, re.I)
    release_match = re.search(
        r"Released\s+on:\s*(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})", text, re.I
    )
    value_match = re.search(
        r"non-resident employment,?\s+which\s+(grew|increased|declined|fell)\s+by\s+"
        r"([\d,]+),\s+(?:up|down)\s+from\s+(-?[\d,]+)\s+in\s+the\s+previous\s+quarter",
        text,
        re.I,
    )
    if not quarter_match:
        raise ValueError("Could not identify the reference quarter in the final MOM report")
    if not release_match:
        raise ValueError("Could not identify the MOM report release date")
    if not value_match:
        raise ValueError("Could not unambiguously parse current and previous non-resident employment changes")

    quarter = int(quarter_match.group(1))
    year = int(quarter_match.group(2))
    direction = -1 if value_match.group(1).lower() in {"declined", "fell"} else 1
    current = direction * float(value_match.group(2).replace(",", ""))
    prior = float(value_match.group(3).replace(",", ""))
    month_names = {
        name: number for number, name in enumerate(
            ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"],
            start=1,
        )
    }
    release_month = month_names[release_match.group(2).title()]
    release_date = f"{int(release_match.group(3)):04d}-{release_month:02d}-{int(release_match.group(1)):02d}"

    common = {
        "source_id": str(source["source_id"]),
        "series_id": "non_resident_employment_change__quarterly_change",
        "series_label": "Non-resident employment change",
        "frequency": "quarterly",
        "unit": str(source["unit"]),
        "market": "rent",
        "role": "predictor",
        "observation_status": "observed",
        "release_date": release_date,
    }
    return [
        Observation(period=previous_quarter(year, quarter), value=prior, **common),
        Observation(period=f"{year}-Q{quarter}", value=current, **common),
    ]

