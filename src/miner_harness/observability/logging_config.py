"""Centralized structlog configuration.

Configures structured logging with context processors for:
- Timestamp (ISO 8601)
- Log level
- Module/function context

Ref: ASO v3 Phase 9 — Observabilidade
"""

from __future__ import annotations

import io
import logging
import sys
from typing import Any

import structlog


def configure_logging(
    *,
    level: int = logging.INFO,
    json_output: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure structlog for the entire application.

    Args:
        level: Minimum log level (default: INFO).
        json_output: If True, output JSON lines (for machine consumption).
        log_file: Optional path to write logs to a file.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to route through structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    stderr = sys.stderr
    if hasattr(stderr, "buffer") and getattr(stderr, "encoding", "utf-8").lower() != "utf-8":
        stderr = io.TextIOWrapper(stderr.buffer, encoding="utf-8", errors="replace")
    handler = logging.StreamHandler(stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_json_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler.setFormatter(file_json_formatter)
        root.addHandler(file_handler)
