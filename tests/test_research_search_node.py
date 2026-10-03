import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from housing_agent.research.models import (
    ApprovedResearchScope,
    ResearchProposal,
)
from housing_agent.research.prompt import (
    SEARCH_AGENT_INSTRUCTIONS,
    build_search_input,
)
from housing_agent.research.providers import (
    AnthropicWebResearchClient,
    DeepSeekTavilyResearchClient,
    GeminiWebResearchClient,
    OpenAIWebResearchClient,
    StructuredOutputError,
    canonical_provider,
    provider_spec,
    provider_status,
)
from housing_agent.research.rendering import render_academic_research_summary
from housing_agent.research.search_node import (
    build_research_search_graph,
    make_search_predictors_node,
)
from housing_agent.research.validation import validate_research_proposal
from scripts.run_research_search import load_project_environment
from housing_agent.memory.compiler import compile_memory
from housing_agent.memory.store import DecisionLogStore


def approved_scope() -> dict:
    return {
        "geography": "Singapore",
        "housing_segments": ["private_residential"],
        "markets": ["sale", "rent"],
        "transaction_channels": [
            "private_new_sale",
            "private_resale",
            "private_rental",
        ],
        "excluded_channels": ["hdb_resale", "hdb_rental", "hdb_bto"],
        "reporting_as_of_date": "2026-06-30",
        "historical_start_date": "2016-01-01",
        "preferred_frequencies": ["quarterly", "monthly"],
        "factor_categories": [
            "macroeconomic",
            "financial",
            "demographic",
            "market_level",
        ],
        "scope_notes": [
            "Analyse sale and rent separately.",
            "Do not include HDB as an outcome market.",
        ],
    }


def candidate(category: str, index: int = 1) -> dict:
    predictor_id = f"{category}_predictor_{index}"
    evidence_id = f"{predictor_id}_evidence"
    return {
        "predictor_id": predictor_id,
        "name": f"{category.replace('_', ' ').title()} Predictor {index}",
        "factor_category": category,
        "market_role": "shared",
        "analytical_role": "timely_predictor",
        "concept_definition": (
            "A test predictor representing a documented Singapore housing-market mechanism."
        ),
        "mechanisms": [
            {
                "housing_segment": "private_residential",
                "market": "sale",
                "transaction_channels": ["private_new_sale", "private_resale"],
                "relevance": "primary",
                "explanation": (
                    "The predictor may affect private residential purchasing demand through "
                    "a documented economic transmission channel."
                ),
                "expected_direction": "mixed",
                "evidence_ids": [evidence_id],
            },
            {
                "housing_segment": "private_residential",
                "market": "rent",
                "transaction_channels": ["private_rental"],
                "relevance": "primary",
                "explanation": (
                    "The predictor may affect private rental demand through a separate and "
                    "documented economic transmission channel."
                ),
                "expected_direction": "ambiguous",
                "evidence_ids": [evidence_id],
            },
        ],
        "evidence_sources": [
            {
                "evidence_id": evidence_id,
                "title": f"Singapore Housing Evidence for {category}",
                "authors_or_issuer": ["Test Research Institution"],
                "publication_date": "2020-01-15",
                "url": f"https://evidence.example/{predictor_id}",
                "source_type": "academic_paper",
                "singapore_specific": True,
                "supported_claim": (
                    "The source supports the stated economic mechanism for Singapore housing."
                ),
                "locator": "Section 4, page 12",
                "temporal_role": "available_as_of",
                "inference_notes": [
                    "The source supports the mechanism, not the exact official series."
                ],
            }
        ],
        "data_requirement": {
            "target_concept": f"A quarterly operational measure of {predictor_id}",
            "preferred_frequency": "quarterly",
            "acceptable_frequencies": ["quarterly", "monthly"],
            "preferred_unit": "index",
            "likely_agencies": ["Singapore Test Agency"],
            "historical_coverage_required_from": "2016-01-01",
            "source_search_hints": [f"Singapore official {predictor_id}"],
            "frequency_rationale": (
                "Quarterly observations match the intended monitoring cadence while "
                "preserving the source's native publication frequency."
            ),
        },
        "research_assessment": {
            component: {
                "rating": "medium",
                "rationale": (
                    f"The available evidence provides a moderate basis for {component}."
                ),
                "evidence_ids": [evidence_id],
            }
            for component in (
                "literature_support",
                "singapore_specificity",
                "target_market_mechanism",
                "frequency_suitability",
                "non_redundancy",
                "interpretability",
            )
        },
        "ranking_reason": (
            "The candidate has a clear mechanism and a publicly accessible official series."
        ),
        "limitations": ["The relationship may vary across housing-market cycles."],
        "endogeneity_risks": ["The predictor may respond to the housing market itself."],
    }


def valid_proposal_dict() -> dict:
    categories = ["macroeconomic", "financial", "demographic", "market_level"]
    return {
        "scope_summary": (
            "Singapore private residential sale and rental markets are analysed separately."
        ),
        "search_queries": [
            {
                "factor_category": category,
                "query": f"Singapore private housing {category} sale rent evidence",
                "purpose": f"Identify a supported {category} predictor and official dataset.",
            }
            for category in categories
        ],
        "candidates": [candidate(category) for category in categories],
        "rejected_candidates": [],
        "unresolved_questions": [],
        "research_limitations": [
            "The proposal identifies potentially informative predictors, not causal effects."
        ],
    }


class FakeResearchClient:
    def __init__(self, proposal: dict | None = None):
        self.proposal = ResearchProposal.model_validate(proposal or valid_proposal_dict())
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return (
            self.proposal,
            {"id": "response_test", "model": kwargs["model"], "output": []},
            set(),
            {
                "provider": "fake",
                "response_id": "response_test",
                "model": kwargs["model"],
                "usage": {"input_tokens": 100, "output_tokens": 200},
            },
        )


class ProviderAdapterContractTests(unittest.TestCase):
    def _kwargs(self) -> dict:
        return {
            "instructions": "Return a grounded proposal.",
            "input_text": "Research the approved scope.",
            "scope": ApprovedResearchScope.model_validate(approved_scope()),
            "model": "test-model",
            "max_tool_calls": 8,
        }

    def test_gemini_adapter_uses_search_and_structured_output(self):
        captured = {}

        class Interactions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    output_text=json.dumps(valid_proposal_dict()),
                    model_dump=lambda **_: {
                        "id": "gemini-test",
                        "model": "test-model",
                        "steps": [],
                        "usage": {},
                    },
                )

        adapter = GeminiWebResearchClient.__new__(GeminiWebResearchClient)
        adapter._client = SimpleNamespace(interactions=Interactions())
        proposal, _, _, metadata = adapter.search(**self._kwargs())
        self.assertEqual(len(proposal.candidates), 4)
        self.assertEqual(captured["tools"], [{"type": "google_search"}])
        self.assertEqual(captured["response_format"]["mime_type"], "application/json")
        self.assertEqual(metadata["search_backend"], "native_google_search")
        self.assertFalse(metadata["structured_output_repaired"])

    def test_gemini_adapter_repairs_json_syntax_then_validates_schema(self):
        malformed = json.dumps(valid_proposal_dict())
        malformed = malformed.replace(
            '"research_limitations": [',
            '"research_limitations": [INVALID, ',
            1,
        )

        class Interactions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    output_text=malformed,
                    model_dump=lambda **_: {
                        "id": "gemini-repaired",
                        "model": "test-model",
                        "steps": [],
                        "usage": {},
                    },
                )

        adapter = GeminiWebResearchClient.__new__(GeminiWebResearchClient)
        adapter._client = SimpleNamespace(interactions=Interactions())
        proposal, _, _, metadata = adapter.search(**self._kwargs())
        self.assertEqual(len(proposal.candidates), 4)
        self.assertTrue(metadata["structured_output_repaired"])

    def test_gemini_adapter_preserves_raw_response_when_repair_fails_schema(self):
        class Interactions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    output_text='{"scope_summary": "incomplete"}',
                    model_dump=lambda **_: {
                        "id": "gemini-invalid",
                        "model": "test-model",
                        "steps": [{"url": "https://evidence.example/source"}],
                        "usage": {},
                    },
                )

        adapter = GeminiWebResearchClient.__new__(GeminiWebResearchClient)
        adapter._client = SimpleNamespace(interactions=Interactions())
        with self.assertRaises(StructuredOutputError) as caught:
            adapter.search(**self._kwargs())
        self.assertEqual(caught.exception.raw_response["id"], "gemini-invalid")
        self.assertEqual(caught.exception.provider_metadata["provider"], "gemini")

    def test_openai_adapter_uses_web_search_and_typed_parse(self):
        captured = {}

        class Responses:
            def parse(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    output_parsed=ResearchProposal.model_validate(valid_proposal_dict()),
                    model_dump=lambda **_: {
                        "id": "openai-test",
                        "model": "test-model",
                        "output": [],
                        "usage": {},
                    },
                )

        adapter = OpenAIWebResearchClient.__new__(OpenAIWebResearchClient)
        adapter._client = SimpleNamespace(responses=Responses())
        proposal, _, _, metadata = adapter.search(**self._kwargs())
        self.assertEqual(len(proposal.candidates), 4)
        self.assertEqual(captured["tools"], [{"type": "web_search"}])
        self.assertIs(captured["text_format"], ResearchProposal)
        self.assertEqual(metadata["search_backend"], "native_openai_web_search")

    def test_anthropic_adapter_uses_search_and_json_schema(self):
        captured = {}

        class Messages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    model_dump=lambda **_: {
                        "id": "anthropic-test",
                        "model": "test-model",
                        "content": [
                            {"type": "text", "text": "Search progress"},
                            {"type": "text", "text": json.dumps(valid_proposal_dict())},
                        ],
                        "usage": {},
                    }
                )

        adapter = AnthropicWebResearchClient.__new__(AnthropicWebResearchClient)
        adapter._client = SimpleNamespace(messages=Messages())
        proposal, _, _, metadata = adapter.search(**self._kwargs())
        self.assertEqual(len(proposal.candidates), 4)
        self.assertEqual(captured["tools"][0]["type"], "web_search_20250305")
        self.assertEqual(captured["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(metadata["search_backend"], "native_anthropic_web_search")

    def test_deepseek_adapter_uses_tavily_before_structured_synthesis(self):
        captured = {"queries": [], "response": {}}

        class SearchClient:
            def search(self, **kwargs):
                captured["queries"].append(kwargs["query"])
                return {"results": [{"url": "https://evidence.example/source"}]}

        class Responses:
            def create(self, **kwargs):
                captured["response"].update(kwargs)
                return SimpleNamespace(
                    output_text=json.dumps(valid_proposal_dict()),
                    model_dump=lambda **_: {
                        "id": "deepseek-test",
                        "model": "test-model",
                        "usage": {},
                    },
                )

        adapter = DeepSeekTavilyResearchClient.__new__(DeepSeekTavilyResearchClient)
        adapter._search_client = SearchClient()
        adapter._model_client = SimpleNamespace(responses=Responses())
        proposal, _, source_urls, metadata = adapter.search(**self._kwargs())
        self.assertEqual(len(proposal.candidates), 4)
        self.assertEqual(len(captured["queries"]), 8)
        self.assertIn("https://evidence.example/source", source_urls)
        self.assertIn("EXTERNALLY RETRIEVED SEARCH EVIDENCE", captured["response"]["input"])
        self.assertEqual(metadata["search_backend"], "tavily")


class ResearchModelTests(unittest.TestCase):
    def test_response_schema_avoids_unsupported_json_schema_formats(self):
        schema_text = json.dumps(ResearchProposal.model_json_schema(), sort_keys=True)
        self.assertNotIn('"format": "uri"', schema_text)
        self.assertNotIn('"format": "date"', schema_text)
        self.assertNotIn('"official_dataset"', schema_text)
        self.assertNotIn('"retrieval_url"', schema_text)
        self.assertIn('"market_role"', schema_text)
        self.assertIn('"research_assessment"', schema_text)

    def test_scope_rejects_duplicate_market_values(self):
        scope = approved_scope()
        scope["markets"] = ["sale", "sale"]
        with self.assertRaises(ValidationError):
            ApprovedResearchScope.model_validate(scope)

    def test_candidate_rejects_unknown_evidence_reference(self):
        proposal = valid_proposal_dict()
        proposal["candidates"][0]["mechanisms"][0]["evidence_ids"] = ["missing"]
        with self.assertRaises(ValidationError):
            ResearchProposal.model_validate(proposal)


class ResearchPromptTests(unittest.TestCase):
    def test_prompt_is_dynamic_and_preserves_approved_scope(self):
        scope = ApprovedResearchScope.model_validate(approved_scope())
        rendered = build_search_input(
            "Focus on private residential sale and rent.", scope
        )
        self.assertIn("Focus on private residential sale and rent.", rendered)
        self.assertIn('"private_residential"', rendered)
        self.assertIn('"sale"', rendered)
        self.assertIn('"rent"', rendered)
        self.assertIn('"hdb_resale"', rendered)
        self.assertIn("HUMAN-APPROVED RESEARCH SCOPE", rendered)

    def test_system_prompt_separates_hdb_from_public_data_access(self):
        self.assertIn("HDB is a housing segment", SEARCH_AGENT_INSTRUCTIONS)
        self.assertIn("Do not provide or guess an API endpoint", SEARCH_AGENT_INSTRUCTIONS)
        self.assertIn("market_role", SEARCH_AGENT_INSTRUCTIONS)
        self.assertIn("structural_context", SEARCH_AGENT_INSTRUCTIONS)
        self.assertIn("Write every field in English", SEARCH_AGENT_INSTRUCTIONS)


class ResearchValidationTests(unittest.TestCase):
    def test_valid_proposal_passes(self):
        result = validate_research_proposal(
            ResearchProposal.model_validate(valid_proposal_dict()),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertEqual(result.automated_validation_status, "pass")
        self.assertEqual(result.human_review_status, "pending")
        self.assertEqual(result.errors, [])
        self.assertEqual(result.candidate_counts["macroeconomic"], 1)
        self.assertIn("private_residential/sale", result.covered_scope_pairs)
        self.assertIn("private_residential/rent", result.covered_scope_pairs)
        self.assertEqual(result.candidate_scores[0].total_score, 60)
        self.assertTrue(all(
            item.hard_gate_status == "pass" for item in result.candidate_scores
        ))

    def test_requested_category_subset_does_not_require_all_four_categories(self):
        scope_data = approved_scope()
        scope_data["factor_categories"] = ["financial", "market_level"]
        proposal_data = valid_proposal_dict()
        proposal_data["search_queries"] = [
            query for query in proposal_data["search_queries"]
            if query["factor_category"] in {"financial", "market_level"}
        ]
        proposal_data["candidates"] = [
            item for item in proposal_data["candidates"]
            if item["factor_category"] in {"financial", "market_level"}
        ]
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal_data),
            ApprovedResearchScope.model_validate(scope_data),
        )
        self.assertEqual(result.automated_validation_status, "pass")
        self.assertEqual(set(result.candidate_counts), {"financial", "market_level"})

    def test_more_than_two_candidates_in_category_fails(self):
        proposal = valid_proposal_dict()
        proposal["candidates"].extend([
            candidate("macroeconomic", 2),
            candidate("macroeconomic", 3),
        ])
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertEqual(result.automated_validation_status, "fail")
        self.assertTrue(any("More than two" in error for error in result.errors))

    def test_mechanism_outside_approved_market_fails(self):
        scope_data = approved_scope()
        scope_data["markets"] = ["sale"]
        proposal = valid_proposal_dict()
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(scope_data),
        )
        self.assertEqual(result.automated_validation_status, "fail")
        self.assertTrue(any("excluded market rent" in error for error in result.errors))

    def test_mechanism_outside_approved_channel_fails(self):
        proposal = valid_proposal_dict()
        proposal["candidates"][0]["mechanisms"][0]["transaction_channels"] = [
            "hdb_resale"
        ]
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertEqual(result.automated_validation_status, "fail")
        self.assertTrue(any("channels outside" in error for error in result.errors))

    def test_post_as_of_source_must_be_method_design_only(self):
        proposal = valid_proposal_dict()
        source = proposal["candidates"][0]["evidence_sources"][0]
        source["publication_date"] = "2026-07-01"
        source["temporal_role"] = "available_as_of"
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertEqual(result.automated_validation_status, "fail")
        self.assertTrue(any("method_design_only" in error for error in result.errors))

    def test_shared_role_requires_primary_sale_and_rent_mechanisms(self):
        proposal = valid_proposal_dict()
        proposal["candidates"][0]["mechanisms"][1]["relevance"] = "secondary"
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertTrue(any("shared market_role" in error for error in result.errors))

    def test_sale_focused_candidate_does_not_need_a_rent_mechanism(self):
        proposal = valid_proposal_dict()
        item = proposal["candidates"][0]
        item["market_role"] = "sale_focused"
        item["mechanisms"] = [item["mechanisms"][0]]
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        score = next(
            score for score in result.candidate_scores
            if score.predictor_id == item["predictor_id"]
        )
        self.assertEqual(score.hard_gate_status, "pass")
        self.assertEqual(result.automated_validation_status, "pass")

    def test_strong_self_ratings_are_capped_without_independent_evidence(self):
        proposal = valid_proposal_dict()
        for component in proposal["candidates"][0]["research_assessment"].values():
            component["rating"] = "strong"
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        score = next(
            score for score in result.candidate_scores
            if score.predictor_id == proposal["candidates"][0]["predictor_id"]
        )
        self.assertEqual(score.total_score, 82)
        self.assertEqual(len(score.rating_adjustments), 2)

    def test_annual_concept_cannot_be_a_timely_predictor(self):
        proposal = valid_proposal_dict()
        item = proposal["candidates"][0]
        item["data_requirement"]["preferred_frequency"] = "annual"
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertEqual(result.automated_validation_status, "fail")
        self.assertTrue(any("annual preferred frequency" in error for error in result.errors))

    def test_search_schema_contains_no_operational_transformation_fields(self):
        schema_text = json.dumps(ResearchProposal.model_json_schema())
        self.assertNotIn("frequency_handling", schema_text)
        self.assertNotIn("aggregation_method", schema_text)
        self.assertNotIn("missing_value", schema_text)

    def test_unsearched_evidence_url_fails_hard_gate(self):
        proposal = ResearchProposal.model_validate(valid_proposal_dict())
        result = validate_research_proposal(
            proposal,
            ApprovedResearchScope.model_validate(approved_scope()),
            searched_source_urls={"https://different.example/source"},
        )
        self.assertEqual(result.evidence_validation_status, "fail")
        self.assertTrue(any(
            item.hard_gate_status == "fail" for item in result.candidate_scores
        ))

    def test_missing_query_category_is_a_warning_not_a_hard_failure(self):
        proposal_data = valid_proposal_dict()
        proposal_data["search_queries"] = [
            query for query in proposal_data["search_queries"]
            if query["factor_category"] != "financial"
        ]
        result = validate_research_proposal(
            ResearchProposal.model_validate(proposal_data),
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        self.assertEqual(result.automated_validation_status, "pass")
        self.assertEqual(result.evidence_validation_status, "pass")
        self.assertTrue(any("financial" in warning for warning in result.warnings))


class ResearchRenderingTests(unittest.TestCase):
    def test_academic_summary_cites_structured_evidence_and_references(self):
        proposal = ResearchProposal.model_validate(valid_proposal_dict())
        validation = validate_research_proposal(
            proposal,
            ApprovedResearchScope.model_validate(approved_scope()),
        )
        rendered = render_academic_research_summary(proposal, validation)
        self.assertIn("# Predictor Research Synthesis", rendered)
        self.assertIn("## Shared predictors", rendered)
        self.assertIn("## References", rendered)
        for candidate_item in proposal.candidates:
            self.assertIn(candidate_item.name, rendered)
            for source in candidate_item.evidence_sources:
                self.assertIn(source.url, rendered)


class ResearchSearchNodeTests(unittest.TestCase):
    def test_node_applies_compiled_memory_without_requesting_data_operations(self):
        memory_path = Path("config/project_memory.seed.jsonl")
        snapshot, manifest = compile_memory(DecisionLogStore(memory_path).load())
        fake = FakeResearchClient()
        result = make_search_predictors_node(lambda: fake)({
            "user_request": "Research predictors for the approved scope.",
            "approved_scope": snapshot.approved_scope.model_dump(mode="json"),
            "memory_snapshot": snapshot.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
            "research_provider": "gemini",
        })
        self.assertEqual(result["research_personalization"]["memory_status"], "applied")
        self.assertEqual(
            result["research_metadata"]["memory_sha256"], manifest.snapshot_sha256
        )
        prompt = fake.calls[0]["input_text"]
        self.assertIn("CONFIRMED PROJECT MEMORY", prompt)
        self.assertIn("sora_alignment_001", prompt)
        self.assertTrue(
            result["research_personalization"]["operational_recommendations_deferred"]
        )

    def test_node_rejects_scope_that_conflicts_with_memory(self):
        snapshot, manifest = compile_memory(
            DecisionLogStore(Path("config/project_memory.seed.jsonl")).load()
        )
        result = make_search_predictors_node(lambda: FakeResearchClient())({
            "user_request": "Research predictors.",
            "approved_scope": approved_scope(),
            "memory_snapshot": snapshot.model_dump(mode="json"),
            "memory_manifest": manifest.model_dump(mode="json"),
        })
        self.assertEqual(result["research_metadata"]["execution_status"], "fail")
        self.assertTrue(any("does not match" in item for item in result["research_errors"]))

    def test_local_env_is_loaded_without_overriding_shell_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_path = Path(temporary) / ".env"
            env_path.write_text(
                "GEMINI_API_KEY=file-key\nOPENAI_API_KEY=file-openai-key\n",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ", {"GEMINI_API_KEY": "shell-key"}, clear=True
            ):
                load_project_environment(env_path)
                self.assertEqual(os.environ["GEMINI_API_KEY"], "shell-key")
                self.assertEqual(os.environ["OPENAI_API_KEY"], "file-openai-key")

    def test_provider_aliases_and_defaults(self):
        self.assertEqual(canonical_provider("chatgpt"), "openai")
        self.assertEqual(canonical_provider("claude"), "anthropic")
        self.assertEqual(provider_spec("gemini").default_model, "gemini-3.8-flash")
        self.assertEqual(provider_spec("deepseek").additional_key_envs, ("TAVILY_API_KEY",))

    def test_unsupported_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported research provider"):
            canonical_provider("unknown")

    def test_provider_status_never_contains_key_values(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "secret-value"}, clear=True):
            statuses = provider_status()
        self.assertTrue(next(item for item in statuses if item["provider"] == "gemini")["configured"])
        self.assertNotIn("secret-value", json.dumps(statuses))

    def test_node_uses_fake_client_and_persists_review_artifacts(self):
        fake = FakeResearchClient()
        with tempfile.TemporaryDirectory() as temporary:
            result = make_search_predictors_node(lambda: fake)({
                "user_request": "Study private residential sale and rent.",
                "approved_scope": approved_scope(),
                "research_provider": "openai",
                "research_model": "test-model",
                "max_search_tool_calls": 12,
                "research_artifact_dir": temporary,
            })
            self.assertEqual(
                result["research_validation"]["automated_validation_status"], "pass"
            )
            self.assertEqual(
                result["research_validation"]["human_review_status"], "pending"
            )
            self.assertEqual(result["research_errors"], [])
            self.assertEqual(result["research_metadata"]["execution_status"], "success")
            self.assertEqual(
                result["research_metadata"]["prompt_version"],
                "predictor-search-v3-memory-aware",
            )
            self.assertEqual(result["research_metadata"]["requested_provider"], "openai")
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(fake.calls[0]["max_tool_calls"], 12)
            self.assertIn("ORIGINAL USER REQUEST", fake.calls[0]["input_text"])
            self.assertIn(
                "# Predictor Research Synthesis",
                result["research_summary_markdown"],
            )

            artifact_root = Path(temporary)
            for name in (
                "research_request.json",
                "predictor_proposal.json",
                "research_validation.json",
                "research_ranking.json",
                "human_review_template.json",
                "research_metadata.json",
                "research_personalization.json",
                "raw_api_response.json",
                "research_errors.json",
            ):
                self.assertTrue((artifact_root / name).is_file(), name)
            metadata = json.loads((artifact_root / "research_metadata.json").read_text())
            self.assertNotIn("api_key", metadata)
            review = json.loads(
                (artifact_root / "human_review_template.json").read_text()
            )
            self.assertEqual(review["decision"], "pending")
            self.assertEqual(len(review["candidate_reviews"]), 4)

    def test_node_persists_raw_provider_response_after_parse_failure(self):
        class InvalidStructuredClient:
            def search(self, **kwargs):
                raise StructuredOutputError(
                    "invalid structured output",
                    raw_response={"id": "preserved-response", "output_text": "{"},
                    provider_metadata={
                        "provider": "gemini",
                        "interaction_id": "preserved-response",
                    },
                )

        with tempfile.TemporaryDirectory() as temporary:
            result = make_search_predictors_node(InvalidStructuredClient)({
                "user_request": "Study private residential sale and rent.",
                "approved_scope": approved_scope(),
                "research_provider": "gemini",
                "research_artifact_dir": temporary,
            })
            self.assertEqual(result["research_metadata"]["execution_status"], "fail")
            self.assertEqual(
                result["research_raw_response"]["id"], "preserved-response"
            )
            persisted = json.loads(
                (Path(temporary) / "raw_api_response.json").read_text()
            )
            self.assertEqual(persisted["id"], "preserved-response")

    def test_isolated_langgraph_compiles_and_runs(self):
        fake = FakeResearchClient()
        result = build_research_search_graph(lambda: fake).invoke({
            "user_request": "Study private residential sale and rent.",
            "approved_scope": approved_scope(),
        })
        self.assertEqual(
            result["research_validation"]["automated_validation_status"], "pass"
        )
        self.assertEqual(len(result["research_proposal"]["candidates"]), 4)

    def test_invalid_scope_returns_controlled_failure(self):
        result = make_search_predictors_node(lambda: FakeResearchClient())({
            "user_request": "Study housing.",
            "approved_scope": {"geography": "Singapore"},
        })
        self.assertEqual(result["research_metadata"]["execution_status"], "fail")
        self.assertEqual(
            result["research_validation"]["automated_validation_status"], "not_run"
        )
        self.assertTrue(result["research_errors"])

    def test_invalid_search_budget_returns_controlled_failure(self):
        result = make_search_predictors_node(lambda: FakeResearchClient())({
            "user_request": "Study housing.",
            "approved_scope": approved_scope(),
            "max_search_tool_calls": 0,
        })
        self.assertEqual(result["research_metadata"]["execution_status"], "fail")
        self.assertTrue(any("1 to 50" in error for error in result["research_errors"]))

    def test_missing_api_key_is_reported_without_exposing_secrets(self):
        with patch.dict("os.environ", {}, clear=True):
            result = make_search_predictors_node()({
                "user_request": "Study private residential sale and rent.",
                "approved_scope": approved_scope(),
                "research_provider": "gemini",
            })
        self.assertEqual(result["research_metadata"]["execution_status"], "fail")
        self.assertTrue(any("GEMINI_API_KEY" in error for error in result["research_errors"]))

    def test_gemini_client_requires_environment_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                GeminiWebResearchClient()

    def test_openai_client_requires_environment_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                OpenAIWebResearchClient()

    def test_anthropic_client_requires_environment_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
                AnthropicWebResearchClient()

    def test_deepseek_client_requires_both_environment_keys(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
                DeepSeekTavilyResearchClient()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TAVILY_API_KEY"):
                DeepSeekTavilyResearchClient()


if __name__ == "__main__":
    unittest.main()
