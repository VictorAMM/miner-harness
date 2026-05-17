"""RCA Learner — learns from historical RCA data to improve classification.

Analyzes past RCA JSON reports to identify recurring error patterns
and generate classification hints for the error classifier.

Ref: ASO v3 Phase 11 — Self-Improvement
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TCH003
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RCAPattern:
    """Recurring error pattern identified from RCA history."""

    category: str
    error_type: str
    count: int
    example_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "error_type": self.error_type,
            "count": self.count,
            "example_messages": self.example_messages[:3],
        }


@dataclass
class RCAHistory:
    """Collection of past RCA reports loaded from disk."""

    reports: list[dict[str, Any]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.reports)


def load_rca_history(rca_dir: Path) -> RCAHistory:
    """Load all RCA JSON reports from a directory.

    Silently skips malformed files.

    Args:
        rca_dir: Directory containing ``rca-*.json`` files.

    Returns:
        RCAHistory with all successfully parsed reports.
    """
    history = RCAHistory()

    if not rca_dir.exists():
        logger.warning("rca_dir_not_found", path=str(rca_dir))
        return history

    for json_path in sorted(rca_dir.glob("rca-*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            history.reports.append(data)
        except (json.JSONDecodeError, OSError):
            logger.warning("rca_load_failed", path=str(json_path))

    logger.info("rca_history_loaded", count=history.count, dir=str(rca_dir))
    return history


def extract_patterns(history: RCAHistory) -> list[RCAPattern]:
    """Extract recurring error patterns from RCA history.

    Groups reports by (category, error_type) and counts occurrences.

    Args:
        history: Loaded RCA history.

    Returns:
        List of RCAPattern objects sorted by count descending.
    """
    # (category, error_type) → list of unique messages
    buckets: dict[tuple[str, str], list[str]] = {}

    for report in history.reports:
        error = report.get("classified_error", {})
        category = error.get("category", "UNKNOWN")
        error_type = error.get("error_type", "Unknown")
        message = error.get("message", "")

        key = (category, error_type)
        if key not in buckets:
            buckets[key] = []
        if message and message not in buckets[key]:
            buckets[key].append(message)

    patterns = [
        RCAPattern(
            category=cat,
            error_type=err_type,
            count=len(messages) or 1,
            example_messages=messages,
        )
        for (cat, err_type), messages in buckets.items()
    ]

    patterns.sort(key=lambda p: p.count, reverse=True)

    logger.info("patterns_extracted", count=len(patterns))
    return patterns


def build_classification_hints(patterns: list[RCAPattern]) -> dict[str, list[str]]:
    """Build error-type hints per category from observed patterns.

    Returns a mapping of category → [error_type, ...] for all patterns
    seen in history. This can be used to pre-seed or weight the
    classifier's pattern matching rules.

    Args:
        patterns: Extracted RCA patterns.

    Returns:
        Dict mapping category name to list of observed error types.
    """
    hints: dict[str, list[str]] = {}

    for pattern in patterns:
        cat = pattern.category
        if cat not in hints:
            hints[cat] = []
        if pattern.error_type not in hints[cat]:
            hints[cat].append(pattern.error_type)

    return hints
