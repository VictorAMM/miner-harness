"""CLI application entry point.

Implements the command-line interface using argparse (stdlib).
Each subcommand delegates to a handler function.

Usage:
    miner-harness analyze carajas --bbox -51.5 -7.0 -49.5 -5.0
    miner-harness cache stats
    miner-harness cache clear
    miner-harness index stats

Ref: ADR-004
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from miner_harness.cli.commands import (
    cmd_analyze,
    cmd_cache_clear,
    cmd_cache_stats,
    cmd_health,
    cmd_index_stats,
    cmd_install,
    cmd_validate,
)

logger = structlog.get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="miner-harness",
        description="Sistema de prospeccao mineral inteligente com agentes de IA",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- install ---
    install_parser = subparsers.add_parser(
        "install",
        help="Guided installation wizard — set up MINER_HOME and initial config",
    )
    install_parser.add_argument(
        "--miner-home",
        default=None,
        help="Override MINER_HOME path (default: ~/.miner-harness)",
    )
    install_parser.add_argument(
        "--model",
        default="qwen3:8b-q4_K_M",
        help="Default LLM model",
    )
    install_parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL",
    )
    install_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (use defaults / flags)",
    )

    # --- analyze ---
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run mineral prospection analysis on a region",
    )
    analyze_parser.add_argument(
        "region",
        help="Region name (e.g., carajas)",
    )
    analyze_parser.add_argument(
        "--bbox",
        required=True,
        nargs=4,
        type=float,
        metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"),
        help="Bounding box — 4 floats: lon_min lat_min lon_max lat_max",
    )
    analyze_parser.add_argument(
        "--model",
        default=None,
        help="LLM model to use (default: from config)",
    )
    analyze_parser.add_argument(
        "--output",
        default=None,
        help="Output file path for the report (JSON)",
    )

    # --- validate ---
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an existing analysis report",
    )
    validate_parser.add_argument(
        "report_file",
        help="Path to report JSON file",
    )

    # --- cache ---
    cache_parser = subparsers.add_parser(
        "cache",
        help="Cache management commands",
    )
    cache_sub = cache_parser.add_subparsers(dest="cache_command")
    cache_sub.add_parser("stats", help="Show cache statistics")
    cache_sub.add_parser("clear", help="Clear all cache entries")

    # --- index ---
    index_parser = subparsers.add_parser(
        "index",
        help="Vector index management commands",
    )
    index_sub = index_parser.add_subparsers(dest="index_command")
    index_sub.add_parser("stats", help="Show index statistics")

    # --- health ---
    subparsers.add_parser(
        "health",
        help="Run system health checks (Ollama, cache, index, disk)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(0),
        )

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "install":
            from pathlib import Path as _Path  # noqa: PLC0415

            return cmd_install(
                miner_home=_Path(args.miner_home) if args.miner_home else None,
                model=args.model,
                ollama_url=args.ollama_url,
                non_interactive=args.non_interactive,
            )
        if args.command == "analyze":
            return asyncio.run(
                cmd_analyze(
                    region=args.region,
                    bbox=tuple(args.bbox),  # type: ignore[arg-type]
                    model=args.model,
                    output_path=args.output,
                )
            )
        if args.command == "validate":
            return cmd_validate(args.report_file)
        if args.command == "cache":
            if args.cache_command == "stats":
                return cmd_cache_stats()
            if args.cache_command == "clear":
                return cmd_cache_clear()
            parser.parse_args(["cache", "--help"])
            return 1
        if args.command == "index":
            if args.index_command == "stats":
                return cmd_index_stats()
            parser.parse_args(["index", "--help"])
            return 1
        if args.command == "health":
            return asyncio.run(cmd_health())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001
        logger.error("cli_error", error=str(exc), type=type(exc).__name__)
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
