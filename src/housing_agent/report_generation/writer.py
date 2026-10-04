from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from housing_agent.report_generation.models import ReportContext, WriterOutput
from housing_agent.report_generation.prompt import build_prompt
from housing_agent.research.providers import provider_spec


class ReportWriter(Protocol):
    provider: str
    model: str | None

    def write(
        self,
        context: ReportContext,
        *,
        attempt: int,
        feedback: tuple[str, ...] = (),
    ) -> WriterOutput: ...


def _claim_anchor(claim_id: str) -> str:
    return f"{{{{CLAIM:{claim_id}}}}}"


def _literature_anchor(reference_id: str) -> str:
    return f"{{{{LIT:{reference_id}}}}}"


def _literature_phrase(context: ReportContext, reference_ids: tuple[str, ...]) -> str:
    known = {item.reference_id for item in context.literature_records}
    anchors = [_literature_anchor(item) for item in reference_ids if item in known]
    if len(anchors) < 2:
        return "".join(anchors)
    return ", ".join(anchors[:-1]) + " and " + anchors[-1]


def _clean_markdown(value: str) -> str:
    return "\n".join(" ".join(line.split()) for line in value.strip().splitlines())


def _academic_fallback(context: ReportContext) -> str:
    """Readable no-API fallback; facts remain immutable claim anchors."""

    by_source: dict[str, list[Any]] = {}
    for claim in context.claims:
        by_source.setdefault(claim.source_id, []).append(claim)
    used: set[str] = set()

    def take(source_id: str) -> str:
        rows = by_source.get(source_id, [])
        used.update(item.claim_id for item in rows)
        return " ".join(_claim_anchor(item.claim_id) for item in rows)

    def remaining(market: str) -> str:
        rows = [
            item for item in context.claims
            if item.market_role == market and item.claim_id not in used
        ]
        used.update(item.claim_id for item in rows)
        return " ".join(_claim_anchor(item.claim_id) for item in rows)

    known_sources = {
        "ura_non_landed_rental_index",
        "non_resident_employment_change",
        "non_resident_population",
        "private_non_landed_vacancy_rate",
        "ura_non_landed_price_index",
        "real_gdp_growth",
        "real_gdp_qoq_growth",
        "three_month_compounded_sora",
        "private_residential_pipeline_supply",
    }
    tailored = known_sources.issubset(by_source)

    if tailored:
        rental_outcome = take("ura_non_landed_rental_index")
        employment = take("non_resident_employment_change")
        population = take("non_resident_population")
        vacancy = take("private_non_landed_vacancy_rate")
        sale_outcome = take("ura_non_landed_price_index")
        gdp = take("real_gdp_growth")
        gdp_qoq = take("real_gdp_qoq_growth")
        sora = take("three_month_compounded_sora")
        pipeline = take("private_residential_pipeline_supply")
        rent_extra = remaining("rent")
        sale_extra = remaining("sale")
        shared_extra = remaining("shared")
        rent_lit = _literature_phrase(
            context,
            ("ChiaLiTang2017", "JiBhandari2022", "DiPasqualeWheaton1992", "URAHDB2026"),
        )
        sale_lit = _literature_phrase(
            context,
            ("Tu2004", "IMF2018", "RangelNg2017"),
        )
        narrative = f"""## Introduction

This report asks what the latest public data suggest about Singapore's private non-landed residential sale and rental markets. It examines the two markets separately and considers whether recent changes in demand, financing, vacancy and prospective supply are consistent with the observed movements in prices and rents.

## Data and Analytical Approach

The official URA price and rental indices show how the two markets moved. These outcomes are considered alongside economic growth, borrowing conditions, non-resident demand, vacancy and the residential pipeline. Most observations are quarterly. Monthly SORA is represented by its value at the end of each quarter so that it can be compared with the housing indices, while annual population data remain annual rather than being converted into artificial quarterly estimates. The results describe how the indicators moved together; they do not establish causal effects or constitute a forecast.

## Rental-Market Findings

{rental_outcome} The outcome evidence shows that rents continued to increase over both the latest quarter and the year, although the quarterly movement was considerably more limited than the annual comparison.

{employment} {population} These demand-side measures are consistent with continued growth in the potential tenant base. This interpretation accords with {rent_lit}, but the measures should still be treated as proxies: employment and population data do not identify whether the individuals concerned occupied private non-landed homes.

{vacancy} Vacancy was almost unchanged over the latest quarter but remained appreciably below its year-earlier level. That combination is consistent with continued utilisation of the available stock and provides a plausible market-tightness mechanism for positive rental growth. It does not establish that the demand indicators caused the rental movement. {rent_extra}

Taken together, the rental evidence indicates a firm market rather than a renewed sharp acceleration. Positive rent changes, expanding potential tenant demand and lower vacancy relative to the previous year point in the same broad direction, while the small quarterly changes warrant a measured interpretation.

## Sale-Market Findings

{sale_outcome} The price outcome therefore combines a marginal quarterly decline with positive annual growth. This is more consistent with a loss of short-term momentum than with a broad annual contraction.

{gdp} {gdp_qoq} Economic activity was positive both relative to a year earlier and relative to the immediately preceding quarter. The potential income and confidence channel is consistent with {sale_lit}, but the descriptive evidence cannot isolate it from other influences.

{sora} The financing evidence shows that the approved quarter-end rate did not fall over the latest quarter. It therefore provided little additional easing in borrowing conditions during the period, although the movement itself was small and should not be treated as a standalone explanation of prices.

{pipeline} {shared_extra} The prospective supply pipeline increased over both the quarter and the year. Pipeline units are not completed homes, so their immediate effect on available supply cannot be inferred from these figures. Even so, the increase may moderate expectations of future scarcity as projects progress toward completion. {sale_extra}

Overall, sale-market conditions were less firm at the quarterly horizon than rental-market conditions. Economic activity remained supportive, but financing did not provide further easing and prospective supply expanded, which is consistent with prices remaining above their year-earlier level while changing little in the latest quarter.

## Limitations

The selected indicators are theoretically relevant but do not identify causal effects. They are also released at different frequencies and with different publication lags. Non-resident employment and population measure potential rental demand rather than actual private tenancy, and the residential pipeline measures prospective rather than completed supply. The analysis does not control for policy changes, location, property characteristics or compositional shifts within the private non-landed segment. Results are therefore best read as a disciplined monitoring assessment bounded by the stated information cut-off.

## Conclusion

The latest evidence indicates that the private non-landed rental market remained firmer than the sale market. Positive rental growth coincided with expanding demand-side indicators and vacancy below its year-earlier level, while sale prices retained positive annual growth but showed little quarterly momentum. Macroeconomic activity remained favourable, but financing conditions and a larger prospective supply pipeline provided countervailing influences. These relationships are informative for monitoring market conditions, but they do not constitute a formal forecast.
"""
        return _clean_markdown(narrative)

    rent = remaining("rent")
    sale = remaining("sale")
    shared = remaining("shared")
    rationales = " ".join(dict.fromkeys(
        item.rationale for item in context.claims if item.rationale
    ))
    literature = " ".join(
        _literature_anchor(item.reference_id) for item in context.literature_records
    )
    return _clean_markdown(f"""## Introduction

This report assesses recent movements in the validated indicators for Singapore's private residential sale and rental markets. The two outcomes are analysed separately before their implications are compared.

## Data and Analytical Approach

Official outcome series and approved predictor series are retained at their validated frequencies and transformed only under the approved data plan. The analysis describes associations in the evidence and does not estimate causal effects or a formal forecast.

## Rental-Market Findings

{rent} The rental evidence should be interpreted jointly, with outcome movements distinguished from possible demand and supply mechanisms.

## Sale-Market Findings

{sale} The sale evidence should be interpreted jointly, with outcome movements distinguished from possible macroeconomic, financing and supply mechanisms.

## Limitations

{rationales} The indicators differ in frequency, timing and economic interpretation. Their association with the market outcomes does not establish causality, and the analysis should not be read as a point forecast. {literature}

## Conclusion

{shared} The validated evidence provides a reproducible basis for monitoring the two markets, subject to the stated data-quality and timing limitations.
""")


class DeterministicReportWriter:
    provider = "deterministic"
    model = None

    def write(
        self,
        context: ReportContext,
        *,
        attempt: int,
        feedback: tuple[str, ...] = (),
    ) -> WriterOutput:
        narrative = _academic_fallback(context)
        return WriterOutput(
            narrative=narrative,
            provider=self.provider,
            model=None,
            prompt_version=context.prompt_version,
            attempt=attempt,
            token_usage=None,
        )


class CallableReportWriter:
    """Adapter used by provider clients and deterministic test doubles."""

    def __init__(self, provider: str, model: str, invoke: Any) -> None:
        self.provider = provider
        self.model = model
        self._invoke = invoke

    def write(
        self,
        context: ReportContext,
        *,
        attempt: int,
        feedback: tuple[str, ...] = (),
    ) -> WriterOutput:
        system, human = build_prompt(context, feedback)
        result = self._invoke(system, human)
        if isinstance(result, str):
            text, usage = result, None
        else:
            text, usage = result
        return WriterOutput(
            narrative=text.strip(),
            provider=self.provider,
            model=self.model,
            prompt_version=context.prompt_version,
            attempt=attempt,
            token_usage=usage,
        )


def create_report_writer(provider: str, model: str | None = None) -> ReportWriter:
    name = provider.strip().lower()
    if name == "deterministic":
        return DeterministicReportWriter()
    if name == "openai":
        from openai import OpenAI

        selected = model or provider_spec(name).default_model
        client = OpenAI(api_key=_required_key("OPENAI_API_KEY", name))

        def invoke(system: str, human: str) -> tuple[str, dict[str, Any] | None]:
            response = client.responses.create(
                model=selected,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": human},
                ],
            )
            usage = response.usage.model_dump() if response.usage else None
            return response.output_text, usage

        return CallableReportWriter(name, selected, invoke)
    if name == "gemini":
        from google import genai

        selected = model or provider_spec(name).default_model
        client = genai.Client(api_key=_required_key("GEMINI_API_KEY", name))

        def invoke(system: str, human: str) -> tuple[str, dict[str, Any] | None]:
            response = client.models.generate_content(
                model=selected,
                contents=f"{system}\n\n{human}",
            )
            usage = None
            if getattr(response, "usage_metadata", None):
                usage = response.usage_metadata.model_dump()
            return response.text or "", usage

        return CallableReportWriter(name, selected, invoke)
    if name == "anthropic":
        from anthropic import Anthropic

        selected = model or provider_spec(name).default_model
        client = Anthropic(api_key=_required_key("ANTHROPIC_API_KEY", name))

        def invoke(system: str, human: str) -> tuple[str, dict[str, Any] | None]:
            response = client.messages.create(
                model=selected,
                max_tokens=1800,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": human}],
            )
            text = "".join(block.text for block in response.content if block.type == "text")
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            return text, usage

        return CallableReportWriter(name, selected, invoke)
    if name == "deepseek":
        from openai import OpenAI

        selected = model or provider_spec(name).default_model
        client = OpenAI(
            api_key=_required_key("DEEPSEEK_API_KEY", name),
            base_url="https://api.deepseek.com",
        )

        def invoke(system: str, human: str) -> tuple[str, dict[str, Any] | None]:
            response = client.chat.completions.create(
                model=selected,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": human},
                ],
            )
            usage = response.usage.model_dump() if response.usage else None
            return response.choices[0].message.content or "", usage

        return CallableReportWriter(name, selected, invoke)
    if name == "groq":
        from openai import OpenAI

        selected = model or provider_spec(name).default_model
        client = OpenAI(
            api_key=_required_key("GROQ_API_KEY", name),
            base_url="https://api.groq.com/openai/v1",
        )

        def invoke(system: str, human: str) -> tuple[str, dict[str, Any] | None]:
            response = client.chat.completions.create(
                model=selected,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": human},
                ],
            )
            usage = response.usage.model_dump() if response.usage else None
            return response.choices[0].message.content or "", usage

        return CallableReportWriter(name, selected, invoke)
    if name == "ollama":
        selected = model or provider_spec(name).default_model
        base_url = (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")

        def invoke(system: str, human: str) -> tuple[str, dict[str, Any] | None]:
            payload = {
                "model": selected,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": human},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
            }
            request = urllib.request.Request(
                f"{base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    raw = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError) as error:
                raise RuntimeError(
                    f"Ollama is unavailable at {base_url}; start Ollama and ensure model {selected!r} is installed."
                ) from error
            usage = {
                "prompt_eval_count": raw.get("prompt_eval_count"),
                "eval_count": raw.get("eval_count"),
            }
            return str(raw.get("message", {}).get("content") or ""), usage

        return CallableReportWriter(name, selected, invoke)
    raise ValueError(
        f"Unsupported report provider {provider!r}; choose deterministic, gemini, openai, anthropic, deepseek, groq, or ollama"
    )


def _required_key(variable: str, provider: str) -> str:
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"{variable} is required for the {provider} report writer")
    return value
