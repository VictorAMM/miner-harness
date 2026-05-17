"""Error classifier — categorizes errors by type and severity.

Classifies exceptions from the pipeline into actionable categories:
- NETWORK: connectivity issues (GeoSGB, Ollama)
- DATA: invalid/missing data from external sources
- LLM: model errors, timeouts, malformed responses
- STORAGE: cache/index corruption or disk issues
- CONFIG: misconfiguration
- UNKNOWN: unclassified errors

Ref: ASO v3 Phase 10 — RCA Autonomo
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone  # noqa: UP017
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ErrorCategory(Enum):
    """Error category for classification."""

    NETWORK = "network"
    DATA = "data"
    LLM = "llm"
    STORAGE = "storage"
    CONFIG = "config"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Error severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ClassifiedError:
    """A classified error with context."""

    category: ErrorCategory
    severity: ErrorSeverity
    error_type: str
    message: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc),  # noqa: UP017
    )
    context: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "error_type": self.error_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "recoverable": self.recoverable,
            "suggested_action": self.suggested_action,
        }


# Classification rules: (exception_pattern, category, severity, recoverable, action)
_CLASSIFICATION_RULES: list[
    tuple[str, ErrorCategory, ErrorSeverity, bool, str]
] = [
    # Network errors
    ("ConnectError", ErrorCategory.NETWORK, ErrorSeverity.HIGH,
     True, "Retry with backoff"),
    ("TimeoutException", ErrorCategory.NETWORK, ErrorSeverity.HIGH,
     True, "Retry with backoff"),
    ("HTTPStatusError", ErrorCategory.NETWORK, ErrorSeverity.MEDIUM,
     True, "Check service status"),
    ("ConnectionRefused", ErrorCategory.NETWORK, ErrorSeverity.HIGH,
     True, "Verify service is running"),
    # LLM errors
    ("OllamaError", ErrorCategory.LLM, ErrorSeverity.HIGH,
     True, "Retry or switch model"),
    ("ResponseError", ErrorCategory.LLM, ErrorSeverity.MEDIUM,
     True, "Retry with different prompt"),
    ("JSONDecodeError", ErrorCategory.LLM, ErrorSeverity.MEDIUM,
     True, "Retry — malformed LLM output"),
    # Storage errors
    ("OperationalError", ErrorCategory.STORAGE, ErrorSeverity.HIGH,
     True, "Check disk space and permissions"),
    ("DatabaseError", ErrorCategory.STORAGE, ErrorSeverity.CRITICAL,
     False, "Database corruption — rebuild"),
    ("IntegrityError", ErrorCategory.STORAGE, ErrorSeverity.MEDIUM,
     True, "Duplicate entry — skip"),
    # Data errors
    ("ValidationError", ErrorCategory.DATA, ErrorSeverity.MEDIUM,
     True, "Validate input data"),
    ("InsufficientDataError", ErrorCategory.DATA, ErrorSeverity.MEDIUM,
     False, "Expand search area"),
    ("KeyError", ErrorCategory.DATA, ErrorSeverity.LOW,
     True, "Missing field in response"),
    # Config errors
    ("FileNotFoundError", ErrorCategory.CONFIG, ErrorSeverity.HIGH,
     False, "Check file paths"),
    ("PermissionError", ErrorCategory.CONFIG, ErrorSeverity.HIGH,
     False, "Check file permissions"),
]


def classify_error(
    exc: BaseException,
    context: dict[str, Any] | None = None,
) -> ClassifiedError:
    """Classify an exception into a category with severity.

    Args:
        exc: The exception to classify.
        context: Optional context dict (region, step, service, etc).

    Returns:
        ClassifiedError with category, severity, and suggested action.
    """
    exc_type = type(exc).__name__
    exc_msg = str(exc)

    for pattern, category, severity, recoverable, action in _CLASSIFICATION_RULES:
        if pattern in exc_type or pattern in exc_msg:
            classified = ClassifiedError(
                category=category,
                severity=severity,
                error_type=exc_type,
                message=exc_msg[:500],
                context=context or {},
                recoverable=recoverable,
                suggested_action=action,
            )
            logger.warning(
                "error_classified",
                category=category.value,
                severity=severity.value,
                error_type=exc_type,
                recoverable=recoverable,
            )
            return classified

    # Unknown error
    classified = ClassifiedError(
        category=ErrorCategory.UNKNOWN,
        severity=ErrorSeverity.MEDIUM,
        error_type=exc_type,
        message=exc_msg[:500],
        context=context or {},
        recoverable=False,
        suggested_action="Investigate manually",
    )
    logger.error(
        "error_unclassified",
        error_type=exc_type,
        message=exc_msg[:200],
    )
    return classified
