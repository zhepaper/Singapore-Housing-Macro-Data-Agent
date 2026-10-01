from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Frequency = Literal["monthly", "quarterly", "annual"]
Market = Literal["sale", "rent", "shared"]
Role = Literal["benchmark", "predictor", "derived"]
ObservationStatus = Literal["observed", "missing_at_source", "derived", "incomplete_period"]


@dataclass(frozen=True)
class Observation:
    source_id: str
    series_id: str
    series_label: str
    period: str
    frequency: Frequency
    value: float | None
    unit: str
    market: Market
    role: Role
    observation_status: ObservationStatus
    release_date: str | None = None
    source_observation_period: str | None = None
    quarter_incomplete: bool = False
    derivation: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
