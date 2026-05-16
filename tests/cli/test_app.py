"""Testes do CLI app.

Ref: ADR-004
"""

from __future__ import annotations

import pytest

from miner_harness.cli.app import _parse_bbox, main


class TestParseBbox:
    """Testes do parser de bbox."""

    def test_valid_bbox(self) -> None:
        result = _parse_bbox("-51.5,-7.0,-49.5,-5.0")
        assert result == (-51.5, -7.0, -49.5, -5.0)

    def test_bbox_with_spaces(self) -> None:
        result = _parse_bbox(" -51.5 , -7.0 , -49.5 , -5.0 ")
        assert result == (-51.5, -7.0, -49.5, -5.0)

    def test_bbox_too_few_values(self) -> None:
        import argparse

        with pytest.raises(argparse.ArgumentTypeError, match="4 values"):
            _parse_bbox("-51.5,-7.0,-49.5")

    def test_bbox_non_numeric(self) -> None:
        import argparse

        with pytest.raises(argparse.ArgumentTypeError, match="numbers"):
            _parse_bbox("a,b,c,d")


class TestMainCLI:
    """Testes do main CLI."""

    def test_no_args_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "miner-harness" in captured.out

    def test_unknown_command(self) -> None:
        with pytest.raises(SystemExit):
            main(["nonexistent"])

    def test_analyze_missing_required(self) -> None:
        with pytest.raises(SystemExit):
            main(["analyze"])  # Missing --region and --bbox

    def test_cache_no_subcommand(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Should show help or return error
        with pytest.raises(SystemExit):
            main(["cache"])
