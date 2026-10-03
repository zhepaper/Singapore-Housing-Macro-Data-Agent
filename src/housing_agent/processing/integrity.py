from __future__ import annotations

import hashlib
from pathlib import Path

from housing_agent.processing.models import (
    FrozenDataPlan,
    ProcessingIssue,
    RecoveryRoute,
    VerificationResult,
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_data_plan(plan: FrozenDataPlan) -> VerificationResult:
    issues: list[ProcessingIssue] = []
    verified = 0
    if plan.computed_sha256() != plan.plan_sha256:
        issues.append(ProcessingIssue(
            code="PLAN_HASH_MISMATCH",
            severity="error",
            route=RecoveryRoute.HARD_STOP,
            message="Frozen plan content no longer matches its approved SHA-256.",
        ))

    outcomes = {item.market_role for item in plan.series if item.portfolio_role == "outcome"}
    for market in ("sale", "rent"):
        if market not in outcomes:
            issues.append(ProcessingIssue(
                code="MISSING_OUTCOME",
                severity="error",
                route=RecoveryRoute.DATA_DISCOVERY,
                message=f"The frozen plan has no {market} outcome series.",
            ))
    if not any(item.portfolio_role == "predictor" for item in plan.series):
        issues.append(ProcessingIssue(
            code="MISSING_PREDICTORS",
            severity="error",
            route=RecoveryRoute.DATA_DISCOVERY,
            message="The frozen plan has no approved predictor series.",
        ))

    for item in plan.series:
        path = Path(item.snapshot_path)
        if not path.is_file():
            issues.append(ProcessingIssue(
                code="RAW_SNAPSHOT_MISSING",
                severity="error",
                route=RecoveryRoute.DATA_DISCOVERY,
                message=f"Raw snapshot does not exist: {path}",
                source_id=item.source_id,
                series_id=item.series_id,
            ))
            continue
        actual = sha256_file(path)
        if actual != item.snapshot_sha256:
            issues.append(ProcessingIssue(
                code="RAW_CHECKSUM_MISMATCH",
                severity="error",
                route=RecoveryRoute.HARD_STOP,
                message="Raw snapshot SHA-256 does not match the approved value.",
                source_id=item.source_id,
                series_id=item.series_id,
            ))
            continue
        verified += 1

    if any(issue.route == RecoveryRoute.HARD_STOP for issue in issues):
        status = "fail"
    elif issues:
        status = "recovery_required"
    else:
        status = "pass"
    return VerificationResult(
        status=status,
        plan_sha256=plan.plan_sha256,
        verified_snapshot_count=verified,
        issues=tuple(issues),
    )
