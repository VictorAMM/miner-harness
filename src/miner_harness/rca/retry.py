"""Retry module — backoff strategies and retry policies.

Provides configurable retry with exponential backoff for recoverable errors.

Ref: ASO v3 Phase 10 — RCA Autonomo
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import structlog

from miner_harness.rca.classifier import ClassifiedError, ErrorCategory, classify_error

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable_categories: list[ErrorCategory] = field(
        default_factory=lambda: [
            ErrorCategory.NETWORK,
            ErrorCategory.LLM,
        ],
    )
    jitter: bool = True

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            import random  # noqa: S311

            delay = delay * (0.5 + random.random() * 0.5)  # noqa: S311
        return delay

    def should_retry(self, classified: ClassifiedError, attempt: int) -> bool:
        """Determine if an error should be retried."""
        if attempt >= self.max_retries:
            return False
        if not classified.recoverable:
            return False
        return classified.category in self.retryable_categories


@dataclass
class RetryResult:
    """Result of a retry operation."""

    success: bool
    result: Any = None
    attempts: int = 0
    last_error: ClassifiedError | None = None
    errors: list[ClassifiedError] = field(default_factory=list)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    policy: RetryPolicy | None = None,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> RetryResult:
    """Execute a function with retry and exponential backoff.

    Args:
        func: Async or sync callable to execute.
        *args: Positional arguments for func.
        policy: RetryPolicy configuration. Uses defaults if None.
        context: Context dict for error classification.
        **kwargs: Keyword arguments for func.

    Returns:
        RetryResult with success status, result, and error history.
    """
    if policy is None:
        policy = RetryPolicy()

    errors: list[ClassifiedError] = []
    attempt = 0

    while True:
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            if errors:
                logger.info(
                    "retry_succeeded",
                    attempt=attempt,
                    total_errors=len(errors),
                )

            return RetryResult(
                success=True,
                result=result,
                attempts=attempt + 1,
                errors=errors,
            )

        except Exception as exc:  # noqa: BLE001
            classified = classify_error(exc, context=context)
            errors.append(classified)

            if not policy.should_retry(classified, attempt):
                logger.error(
                    "retry_exhausted",
                    attempt=attempt,
                    category=classified.category.value,
                    recoverable=classified.recoverable,
                    error_type=classified.error_type,
                )
                return RetryResult(
                    success=False,
                    attempts=attempt + 1,
                    last_error=classified,
                    errors=errors,
                )

            delay = policy.get_delay(attempt)
            logger.warning(
                "retry_attempt",
                attempt=attempt + 1,
                max_retries=policy.max_retries,
                delay_seconds=round(delay, 2),
                error_type=classified.error_type,
            )
            await asyncio.sleep(delay)
            attempt += 1
