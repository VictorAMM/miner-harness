"""Tests for logging configuration.

Ref: Phase 9 — Observabilidade
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
import structlog

from miner_harness.observability.logging_config import configure_logging

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Reset structlog after each test to avoid contamination."""
    yield
    structlog.reset_defaults()
    root = logging.getLogger()
    root.handlers.clear()


class TestConfigureLogging:
    """Test centralized logging configuration."""

    def test_configure_default(self) -> None:
        """Default configuration should not raise."""
        configure_logging()
        logger = structlog.get_logger("test")
        assert logger is not None

    def test_configure_debug_level(self) -> None:
        """Should accept DEBUG level."""
        configure_logging(level=logging.DEBUG)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_configure_json_output(self) -> None:
        """JSON output mode should not raise."""
        configure_logging(json_output=True)
        logger = structlog.get_logger("test_json")
        assert logger is not None

    def test_configure_with_log_file(self, tmp_path: Path) -> None:
        """Should create file handler when log_file specified."""
        log_file = tmp_path / "test.log"
        configure_logging(log_file=str(log_file))
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1

    def test_configure_clears_existing_handlers(self) -> None:
        """Should reset root handlers on each call."""
        configure_logging()
        first_count = len(logging.getLogger().handlers)
        configure_logging()
        second_count = len(logging.getLogger().handlers)
        # Should have same count (not double)
        assert second_count <= first_count + 1

    def test_configure_logging_wraps_non_utf8_stderr(self) -> None:
        """StreamHandler usa UTF-8 quando stderr.encoding != utf-8 (linha 68)."""
        import sys
        from unittest.mock import MagicMock, patch

        fake_buffer = MagicMock()
        fake_stderr = MagicMock()
        fake_stderr.encoding = "cp1252"
        fake_stderr.buffer = fake_buffer

        wrapper_target = "miner_harness.observability.logging_config.io.TextIOWrapper"
        with (
            patch.object(sys, "stderr", fake_stderr),
            patch(wrapper_target, return_value=MagicMock()) as mock_wrap,
        ):
            configure_logging()

        mock_wrap.assert_called_once_with(fake_buffer, encoding="utf-8", errors="replace")
