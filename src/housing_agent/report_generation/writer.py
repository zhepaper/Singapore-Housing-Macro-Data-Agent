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


def _market_sentence(context: ReportContext, market: str) -> str:
    rows = [item for item in context.claims if item.market_role == market]
    changes = [item for item in rows if item.derivation and "change" in item.derivation.lower()]
    if not rows:
        return "The validated evidence is insufficient for a market-specific interpretation."
    if not changes:
        return (
            "Validated levels are available, but the selected evidence contains no comparable "
            "change signal; interpretation should therefore remain cautious."
        )
    positive = sum(item.value > 0 for item in changes)
    negative = sum(item.value < 0 for item in changes)
    if positive and negative:
        signal = "The validated change signals are mixed and do not support a single directional conclusion."
    elif positive:
        signal = "The validated change signals are positive, although their mechanisms and timing may differ."
    elif negative:
        signal = "The validated change signals are negative, although their mechanisms and timing may differ."
    else:
        signal = "The validated change signals are broadly unchanged."
    return signal + " These descriptive movements should not be interpreted as causal estimates or forecasts."


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
        sale = _market_sentence(context, "sale")
        rent = _market_sentence(context, "rent")
        shared = _market_sentence(context, "shared")
        narrative = "\n\n".join([
            "### Executive Summary\n\n"
            "The validated indicators provide a descriptive view of market conditions. "
            "They should be read as potentially informative signals rather than a causal model or forecast.",
            f"### Sale-Market Interpretation\n\n{sale}",
            f"### Rental-Market Interpretation\n\n{rent}",
            f"### Shared Signals\n\n{shared}",
            "### Cross-Series Interpretation\n\n"
            "Signals across financing, demand, supply, and market outcomes may move at different times. "
            "Agreement can strengthen a descriptive reading, while disagreement should remain visible rather than being forced into one conclusion.",
            "### Conclusion\n\n"
            "The evidence supports continued monitoring, with conclusions bounded by source timing, frequency, and data quality."
        ])
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
