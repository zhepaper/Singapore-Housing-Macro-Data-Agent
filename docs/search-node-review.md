# Predictor SearchNode Review

## Status

This is an isolated research-stage node. It is intentionally not connected to the production retrieval and reporting workflow until its research behaviour is reviewed and approved.

## Purpose

The node uses a user-selected LLM provider with grounded web search to propose predictor concepts for a human-approved Singapore residential-market scope. It does not discover production endpoints, approve predictors, download observations, calculate changes, or modify the production data catalog.

## Inputs

- The user's original research request.
- A human-approved structured scope.
- A compiled project-memory snapshot and checksum manifest.
- The reporting as-of date.
- Requested factor categories.
- A model name and a bounded web-search tool-call budget.
- An optional artifact directory.

The scope keeps three concepts separate:

- Housing segment: private residential or HDB.
- Market outcome: sale or rent.
- Data access: publicly accessible or restricted.

## Research Behaviour

For every requested factor category, the node must propose one or two candidates:

- Macroeconomic.
- Financial.
- Demographic.
- Market-level.

Every candidate must include:

- A concept definition.
- A `shared`, `sale_focused`, or `rent_focused` market role.
- A `timely_predictor` or `structural_context` analytical role.
- Separate mechanisms only for genuinely applicable segments and markets.
- At least one mechanism source.
- A precise statement of what that source supports.
- A data requirement for the later source-discovery stage, not a guessed endpoint.
- Preferred and acceptable native source frequency, preferred unit, likely official agencies, historical coverage, search hints, and frequency rationale.
- Limitations, endogeneity risks, and a six-component research assessment.

The complete English research prompt is defined in `src/housing_agent/research/prompt.py`.

## Source Policy

The prompt prioritises Singapore-specific academic research, official Singapore reports, and Singapore institutional research. International evidence is allowed only when it is clearly labelled and Singapore-specific evidence is unavailable.

A literature source supports the proposed mechanism. This node records the operational data concept required to represent that mechanism, but leaves exact dataset, series, endpoint, and adapter discovery to a later stage. This prevents a model from filling required endpoint fields with plausible but unverified values.

Annual concepts may be retained only as `structural_context`. The SearchNode does not select interpolation, aggregation, lag, or missing-value rules. It asks for higher-frequency alternatives where supported and defers operational choices until verified source structures are available.

## Deterministic Research Score

The LLM supplies evidence-linked ordinal assessments; code, not the model, calculates the numeric score:

| Component | Weight |
|---|---:|
| Literature support | 25 |
| Singapore specificity | 20 |
| Target-market mechanism | 20 |
| Frequency suitability | 15 |
| Non-redundancy | 10 |
| Interpretability after considering endogeneity | 10 |

The rating-to-points mapping is fixed in code. Strong literature or mechanism ratings are capped at medium when fewer than two independent evidence references are supplied, and Singapore-specificity ratings are calibrated against the source metadata. Every adjustment is written to `research_ranking.json`. A high score cannot override a hard-gate failure.

## As-of Policy

The reporting as-of date constrains contemporaneous evidence. A source published after that date may be retained only as `method_design_only`; it cannot be presented as information available at the reporting date.

## Deterministic Validation

After the LLM response is parsed into the typed schema, deterministic validation checks:

- One or two candidates per requested category.
- No candidates outside the approved categories.
- Unique predictor identifiers.
- No mechanisms outside approved housing segments, markets, or channels.
- Coverage of every approved segment/market pair.
- Valid evidence references.
- Consistency between market role and primary sale/rent mechanisms.
- Consistency between analytical role and target frequency.
- Prohibition of labelling an annual concept as a timely predictor.
- Exact agreement between the approved scope and compiled project memory.
- Evidence-backed assessment fields and traceability to returned web-search metadata.
- Search-query coverage for every requested category; incomplete query classification is retained as a warning because the raw provider response preserves the actual search trace.
- Correct treatment of sources published after the as-of date.

Validation reports execution, automated scope/evidence checks, deterministic scores, hard gates, and a separate `human_review_status`. Automated pass never means that a predictor has been approved.

## Outputs

When an artifact directory is supplied, the node writes:

- `research_request.json`.
- `predictor_proposal.json`.
- `research_validation.json`.
- `research_ranking.json`.
- `human_review_template.json`.
- `research_metadata.json`.
- `research_personalization.json`.
- `raw_api_response.json`.
- `research_errors.json`.

No API key is written to these files. Metadata records the memory version and checksum so the result can be tied to the exact confirmed decisions used for the run.

## API Boundary

Live research supports six provider paths. Keys are read from the process environment and are never accepted as command-line arguments.

For local use, the CLI loads a Git-ignored `.env` file from the repository root. Existing shell environment variables take precedence over values in that file. `.env.example` documents the supported variable names without containing secrets.

| Provider | Required keys | Search backend |
|---|---|---|
| Gemini | `GEMINI_API_KEY` | Native Google Search |
| OpenAI / ChatGPT | `OPENAI_API_KEY` | Native OpenAI web search |
| Anthropic / Claude | `ANTHROPIC_API_KEY` | Native Anthropic web search |
| DeepSeek | `DEEPSEEK_API_KEY`, `TAVILY_API_KEY` | Tavily search followed by DeepSeek structured synthesis |
| Groq | `GROQ_API_KEY`, `TAVILY_API_KEY` | Tavily search followed by Groq structured synthesis |
| Ollama | `TAVILY_API_KEY` | Tavily search followed by local Ollama structured synthesis |

Every provider must return the same `ResearchProposal` schema and passes through the same deterministic validation.

Tests inject a fake research client and do not make network calls.

## Isolated Execution

After setting the key required by the selected provider:

```bash
python scripts/run_research_search.py \
  --provider gemini \
  --request "Focus on Singapore private residential sale and rent." \
  --scope config/research_scope.example.json \
  --output outputs/research_search
```

After a human selects predictors, a separate source-discovery stage will locate and test official datasets and produce catalog candidates. Only a later human approval may freeze those candidates into the production catalog.

The `--model` argument is optional. When it is omitted, the adapter uses the default model shown by `--list-providers`; an explicit override is useful when an account has access to a different compatible model.

For Ollama, `OLLAMA_BASE_URL` is optional and defaults to `http://127.0.0.1:11434`. The local adapter disables extended thinking, uses temperature zero, supplies the complete Pydantic JSON schema to Ollama, and still sends the result through the same deterministic validation and human gate as hosted providers.
