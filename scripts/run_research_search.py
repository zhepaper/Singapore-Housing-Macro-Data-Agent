#!/usr/bin/env python3
"""Run the isolated LLM predictor SearchNode for an approved scope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from housing_agent.research.search_node import build_research_search_graph  # noqa: E402
from housing_agent.research.providers import provider_status  # noqa: E402
from housing_agent.memory.compiler import compile_memory, persist_memory_snapshot  # noqa: E402
from housing_agent.memory.store import DecisionLogStore  # noqa: E402


def load_project_environment(env_path: Path | None = None) -> None:
    """Load local secrets without overriding variables set by the caller."""
    load_dotenv(env_path or PROJECT_ROOT / ".env", override=False)


def main() -> int:
    load_project_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", help="The user's original research request.")
    parser.add_argument(
        "--provider",
        choices=("gemini", "openai", "chatgpt", "anthropic", "claude", "deepseek"),
        default="gemini",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="Show available providers, required keys, and configuration status.",
    )
    parser.add_argument(
        "--scope",
        type=Path,
        default=PROJECT_ROOT / "config/research_scope.example.json",
        help="Path to a human-approved research-scope JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/research_search",
        help="Directory for reviewable SearchNode artifacts.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override. By default, the selected provider's model is used.",
    )
    parser.add_argument("--max-search-tool-calls", type=int, default=20)
    parser.add_argument(
        "--memory-decision-log",
        type=Path,
        default=PROJECT_ROOT / "config/project_memory.seed.jsonl",
        help="Append-only project decision log used to personalise research.",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print the citation-rich academic synthesis after a successful run.",
    )
    args = parser.parse_args()

    if args.list_providers:
        for item in provider_status():
            key_names = ", ".join(item["required_key_envs"])
            status = "configured" if item["configured"] else "missing key"
            print(
                f"{item['provider']:<10} {status:<12} "
                f"model={item['default_model']} search={item['search_backend']} "
                f"keys={key_names}"
            )
        return 0
    if not args.request:
        parser.error("--request is required unless --list-providers is used")

    scope_path = args.scope if args.scope.is_absolute() else PROJECT_ROOT / args.scope
    output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    memory_path = (
        args.memory_decision_log
        if args.memory_decision_log.is_absolute()
        else PROJECT_ROOT / args.memory_decision_log
    )
    memory_snapshot, memory_manifest = compile_memory(
        DecisionLogStore(memory_path).load()
    )
    memory_manifest = persist_memory_snapshot(
        memory_snapshot, memory_manifest, output_path / "project_memory"
    )

    result = build_research_search_graph().invoke({
        "user_request": args.request,
        "approved_scope": scope,
        "research_provider": args.provider,
        "research_model": args.model,
        "max_search_tool_calls": args.max_search_tool_calls,
        "research_artifact_dir": str(output_path),
        "memory_snapshot": memory_snapshot.model_dump(mode="json"),
        "memory_manifest": memory_manifest.model_dump(mode="json"),
    })
    validation = result["research_validation"]
    print(
        "SearchNode execution: "
        f"{result['research_metadata']['execution_status']}"
    )
    print(
        "Automated validation: "
        f"{validation['automated_validation_status']}"
    )
    print(f"Human review: {validation['human_review_status']}")
    print(f"Review artifacts: {output_path}")
    print(
        f"Project memory: v{memory_snapshot.memory_version} "
        f"sha256={memory_manifest.snapshot_sha256[:12]}"
    )
    for warning in validation.get("warnings", []):
        print(f"VALIDATION WARNING: {warning}", file=sys.stderr)
    if result.get("research_errors"):
        for error in result["research_errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if validation["automated_validation_status"] != "pass":
        for error in validation["errors"]:
            print(f"VALIDATION ERROR: {error}", file=sys.stderr)
        return 2
    if args.print_summary:
        print()
        print(result["research_summary_markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
