"""Tests for rca.retry module."""

from __future__ import annotations

import pytest

from miner_harness.rca.classifier import ErrorCategory
from miner_harness.rca.retry import RetryPolicy, retry_with_backoff


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""

    def test_default_values(self) -> None:
        policy = RetryPolicy()
        assert policy.max_retries == 3  # noqa: PLR2004
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.exponential_base == 2.0
        assert ErrorCategory.NETWORK in policy.retryable_categories
        assert ErrorCategory.LLM in policy.retryable_categories

    def test_get_delay_exponential(self) -> None:
        policy = RetryPolicy(jitter=False)
        assert policy.get_delay(0) == 1.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(2) == 4.0  # noqa: PLR2004

    def test_get_delay_capped(self) -> None:
        policy = RetryPolicy(max_delay=5.0, jitter=False)
        assert policy.get_delay(10) == 5.0  # noqa: PLR2004

    def test_get_delay_with_jitter(self) -> None:
        policy = RetryPolicy(jitter=True)
        delays = [policy.get_delay(0) for _ in range(10)]
        # With jitter, delays vary between 0.5*base and 1.0*base
        assert all(0.5 <= d <= 1.0 for d in delays)

    def test_should_retry_recoverable_network(self) -> None:
        from miner_harness.rca.classifier import ClassifiedError, ErrorSeverity

        policy = RetryPolicy(max_retries=3)
        classified = ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            error_type="ConnectError",
            message="refused",
            recoverable=True,
        )
        assert policy.should_retry(classified, 0) is True
        assert policy.should_retry(classified, 2) is True
        assert policy.should_retry(classified, 3) is False

    def test_should_retry_non_recoverable(self) -> None:
        from miner_harness.rca.classifier import ClassifiedError, ErrorSeverity

        policy = RetryPolicy()
        classified = ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            error_type="X",
            message="y",
            recoverable=False,
        )
        assert policy.should_retry(classified, 0) is False

    def test_should_retry_wrong_category(self) -> None:
        from miner_harness.rca.classifier import ClassifiedError, ErrorSeverity

        policy = RetryPolicy(retryable_categories=[ErrorCategory.NETWORK])
        classified = ClassifiedError(
            category=ErrorCategory.CONFIG,
            severity=ErrorSeverity.HIGH,
            error_type="X",
            message="y",
            recoverable=True,
        )
        assert policy.should_retry(classified, 0) is False


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_success_first_try(self) -> None:
        async def ok() -> str:
            return "done"

        result = await retry_with_backoff(ok)
        assert result.success is True
        assert result.result == "done"
        assert result.attempts == 1
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_success_after_retries(self) -> None:
        call_count = 0

        class ConnectError(Exception):
            pass

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # noqa: PLR2004
                raise ConnectError("refused")
            return "ok"

        policy = RetryPolicy(base_delay=0.01, max_retries=5)
        result = await retry_with_backoff(flaky, policy=policy)
        assert result.success is True
        assert result.result == "ok"
        assert result.attempts == 3  # noqa: PLR2004
        assert len(result.errors) == 2  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_exhausted_retries(self) -> None:
        class ConnectError(Exception):
            pass

        async def always_fail() -> None:
            raise ConnectError("nope")

        policy = RetryPolicy(base_delay=0.01, max_retries=2)
        result = await retry_with_backoff(always_fail, policy=policy)
        assert result.success is False
        assert result.attempts == 3  # noqa: PLR2004
        assert result.last_error is not None
        assert result.last_error.category == ErrorCategory.NETWORK

    @pytest.mark.asyncio
    async def test_non_retryable_fails_immediately(self) -> None:
        async def config_fail() -> None:
            raise FileNotFoundError("missing.yaml")

        policy = RetryPolicy(base_delay=0.01)
        result = await retry_with_backoff(config_fail, policy=policy)
        assert result.success is False
        assert result.attempts == 1
        assert result.last_error is not None
        assert result.last_error.category == ErrorCategory.CONFIG

    @pytest.mark.asyncio
    async def test_sync_function_support(self) -> None:
        def sync_ok() -> int:
            return 42

        result = await retry_with_backoff(sync_ok)
        assert result.success is True
        assert result.result == 42  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_context_passed_to_classifier(self) -> None:
        async def fail() -> None:
            raise FileNotFoundError("x")

        ctx = {"step": "fetch", "region": "Carajas"}
        policy = RetryPolicy(base_delay=0.01)
        result = await retry_with_backoff(fail, policy=policy, context=ctx)
        assert result.last_error is not None
        assert result.last_error.context == ctx
