"""Tests for rca.classifier module."""

from __future__ import annotations

from miner_harness.rca.classifier import (
    ClassifiedError,
    ErrorCategory,
    ErrorSeverity,
    classify_error,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_all_categories_exist(self) -> None:
        assert len(ErrorCategory) == 6  # noqa: PLR2004
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.UNKNOWN.value == "unknown"

    def test_severity_levels(self) -> None:
        assert len(ErrorSeverity) == 4  # noqa: PLR2004
        assert ErrorSeverity.CRITICAL.value == "critical"
        assert ErrorSeverity.LOW.value == "low"


class TestClassifiedError:
    """Tests for ClassifiedError dataclass."""

    def test_to_dict(self) -> None:
        err = ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            error_type="ConnectError",
            message="Connection refused",
            context={"service": "ollama"},
            recoverable=True,
            suggested_action="Retry",
        )
        d = err.to_dict()
        assert d["category"] == "network"
        assert d["severity"] == "high"
        assert d["error_type"] == "ConnectError"
        assert d["context"]["service"] == "ollama"
        assert d["recoverable"] is True

    def test_default_values(self) -> None:
        err = ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.LOW,
            error_type="X",
            message="y",
        )
        assert err.context == {}
        assert err.recoverable is True
        assert err.timestamp is not None


class TestClassifyError:
    """Tests for classify_error function."""

    def test_network_connect_error(self) -> None:
        class ConnectError(Exception):
            pass

        result = classify_error(ConnectError("refused"))
        assert result.category == ErrorCategory.NETWORK
        assert result.severity == ErrorSeverity.HIGH
        assert result.recoverable is True

    def test_llm_json_decode_error(self) -> None:
        import json

        exc = json.JSONDecodeError("bad", "", 0)
        result = classify_error(exc)
        assert result.category == ErrorCategory.LLM
        assert result.recoverable is True

    def test_storage_operational_error(self) -> None:
        class OperationalError(Exception):
            pass

        result = classify_error(OperationalError("disk full"))
        assert result.category == ErrorCategory.STORAGE
        assert result.severity == ErrorSeverity.HIGH

    def test_config_file_not_found(self) -> None:
        exc = FileNotFoundError("config.yaml")
        result = classify_error(exc)
        assert result.category == ErrorCategory.CONFIG
        assert result.recoverable is False

    def test_unknown_error(self) -> None:
        class WeirdError(Exception):
            pass

        result = classify_error(WeirdError("???"))
        assert result.category == ErrorCategory.UNKNOWN
        assert result.recoverable is False

    def test_context_passed_through(self) -> None:
        ctx = {"region": "Carajas", "step": "fetch"}
        result = classify_error(ValueError("bad"), context=ctx)
        assert result.context == ctx

    def test_message_truncated(self) -> None:
        long_msg = "x" * 1000
        result = classify_error(RuntimeError(long_msg))
        assert len(result.message) == 500  # noqa: PLR2004

    def test_data_validation_error(self) -> None:
        class ValidationError(Exception):
            pass

        result = classify_error(ValidationError("invalid input"))
        assert result.category == ErrorCategory.DATA
        assert result.severity == ErrorSeverity.MEDIUM
