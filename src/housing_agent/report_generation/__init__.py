"""Evidence-bound Stage 4 report generation."""

from housing_agent.report_generation.models import (
    EvidenceClaim,
    LiteratureRecord,
    ReportBrief,
    ReportContext,
    ReportRunResult,
    ReportVerification,
    SourceRecord,
)
from housing_agent.report_generation.pipeline import load_evidence_bundle, run_stage4
from housing_agent.report_generation.graph import build_stage4_graph
from housing_agent.report_generation.memory_bridge import report_brief_from_memory

__all__ = [
    "EvidenceClaim",
    "LiteratureRecord",
    "ReportBrief",
    "ReportContext",
    "ReportRunResult",
    "ReportVerification",
    "SourceRecord",
    "load_evidence_bundle",
    "build_stage4_graph",
    "report_brief_from_memory",
    "run_stage4",
]
