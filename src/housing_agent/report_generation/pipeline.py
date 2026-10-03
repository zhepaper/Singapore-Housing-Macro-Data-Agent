from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from housing_agent.processing.models import ValidatedEvidenceBundle
from housing_agent.processing.persistence import write_json
from housing_agent.report_generation.evidence import build_report_context
from housing_agent.report_generation.graph import build_stage4_graph
from housing_agent.report_generation.models import (
    ReportBrief,
    ReportRunResult,
    ReportVerification,
)
from housing_agent.report_generation.prompt import build_prompt
from housing_agent.report_generation.writer import ReportWriter, create_report_writer


def load_evidence_bundle(path: str | Path) -> ValidatedEvidenceBundle:
    return ValidatedEvidenceBundle.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_stage4(
    bundle: ValidatedEvidenceBundle,
    output_directory: str | Path,
    *,
    brief: ReportBrief | None = None,
    writer: ReportWriter | None = None,
    provider: str = "deterministic",
    model: str | None = None,
    max_attempts: int = 3,
) -> ReportRunResult:
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=True)
    if max_attempts < 1 or max_attempts > 3:
        raise ValueError("max_attempts must be between 1 and 3")
    try:
        context = build_report_context(bundle, brief)
    except Exception as exc:
        write_json(root / "failure_diagnostics.json", {
            "status": "failed",
            "errors": [f"{type(exc).__name__}: {exc}"],
        })
        return ReportRunResult(
            status="failed",
            attempts=0,
            output_directory=str(root.resolve()),
            errors=(f"{type(exc).__name__}: {exc}",),
        )

    write_json(root / "selected_evidence.json", context.claims)
    write_json(root / "report_context.json", context)
    write_json(root / "source_register.json", context.source_records)
    try:
        selected_writer = writer or create_report_writer(provider, model)
    except Exception as exc:
        write_json(root / "failure_diagnostics.json", {
            "status": "failed",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "evidence_sha256": context.evidence_sha256,
        })
        return ReportRunResult(
            status="failed",
            attempts=0,
            output_directory=str(root.resolve()),
            errors=(f"{type(exc).__name__}: {exc}",),
        )
    initial_system, initial_human = build_prompt(context, ())
    initial_prompt = f"SYSTEM\n{initial_system}\n\nUSER\n{initial_human}\n"
    (root / "report_prompt.txt").write_text(initial_prompt, encoding="utf-8")
    write_json(root / "report_prompt_manifest.json", {
        "prompt_version": context.prompt_version,
        "prompt_sha256": _sha256_text(initial_prompt),
        "evidence_sha256": context.evidence_sha256,
        "provider": selected_writer.provider,
        "model": selected_writer.model,
        "attempt": 1,
    })
    verification = ReportVerification(status="fail", claims_checked=0, errors=("Writer did not run",))
    report = ""
    writer_metadata: list[dict[str, object]] = []
    attempt = 0
    try:
        state = build_stage4_graph().invoke({
            "context": context,
            "writer": selected_writer,
            "max_attempts": max_attempts,
            "attempt": 0,
            "feedback": (),
            "prompt_history": [],
            "writer_history": [],
        })
        attempt = state["attempt"]
        report = state["report"]
        verification = state["verification"]
        writer_metadata = state["writer_history"]
        prompt_text = state["prompt_text"]
        prompt_history = state["prompt_history"]
        prompts_root = root / "prompts"
        prompts_root.mkdir(parents=True, exist_ok=True)
        for index, saved_prompt in enumerate(prompt_history, start=1):
            (prompts_root / f"attempt_{index}.txt").write_text(
                saved_prompt, encoding="utf-8"
            )
        (root / "report_prompt.txt").write_text(prompt_text, encoding="utf-8")
        write_json(root / "report_prompt_manifest.json", {
            "prompt_version": context.prompt_version,
            "prompt_sha256": _sha256_text(prompt_text),
            "evidence_sha256": context.evidence_sha256,
            "provider": selected_writer.provider,
            "model": selected_writer.model,
            "attempt": attempt,
            "attempts": [
                {
                    "attempt": index,
                    "path": f"prompts/attempt_{index}.txt",
                    "prompt_sha256": _sha256_text(saved_prompt),
                }
                for index, saved_prompt in enumerate(prompt_history, start=1)
            ],
        })
    except Exception as exc:
        attempt = max(attempt, 1)
        verification = ReportVerification(
            status="fail",
            claims_checked=0,
            errors=(f"{type(exc).__name__}: {exc}",),
        )

    write_json(root / "claim_ledger.json", context.claims)
    write_json(root / "verification_report.json", verification)
    write_json(root / "writer_metadata.json", writer_metadata)
    generated_at = datetime.now(timezone.utc).isoformat()
    status = "success" if verification.status == "pass" else "blocked"
    report_name = "final_report.md" if status == "success" else "blocked_report.md"
    stale_name = "blocked_report.md" if status == "success" else "final_report.md"
    (root / stale_name).unlink(missing_ok=True)
    (root / report_name).write_text(report, encoding="utf-8")
    write_json(root / "run_manifest.json", {
        "stage": "report_generation",
        "status": status,
        "generated_at": generated_at,
        "attempts": attempt,
        "provider": selected_writer.provider,
        "model": selected_writer.model,
        "prompt_version": context.prompt_version,
        "evidence_sha256": context.evidence_sha256,
        "report_sha256": _sha256_text(report),
    })
    return ReportRunResult(
        status=status,
        attempts=attempt,
        output_directory=str(root.resolve()),
        report_path=str((root / report_name).resolve()),
        verification_path=str((root / "verification_report.json").resolve()),
        errors=verification.errors if status == "blocked" else (),
    )
