"""LLM-assisted, human-governed predictor research components."""

from housing_agent.research.models import (
    ApprovedResearchScope,
    PredictorCandidate,
    ResearchProposal,
)
__all__ = [
    "ApprovedResearchScope",
    "PredictorCandidate",
    "ResearchProposal",
    "ResearchSearchState",
    "build_research_search_graph",
    "make_search_predictors_node",
    "search_predictors_node",
]


def __getattr__(name: str):
    """Load graph objects lazily so typed memory can import research models safely."""
    if name in {
        "ResearchSearchState",
        "build_research_search_graph",
        "make_search_predictors_node",
        "search_predictors_node",
    }:
        from housing_agent.research import search_node

        return getattr(search_node, name)
    raise AttributeError(name)
