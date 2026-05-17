"""Testes do CLI app.

Ref: ADR-004
"""

from __future__ import annotations

import pytest

from miner_harness.cli.app import main


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
            main(["analyze"])  # Missing region and --bbox

    def test_analyze_bbox_accepts_negative_floats(self) -> None:
        # argparse nargs=4 type=float must handle negative values without error
        from unittest.mock import AsyncMock, patch

        with patch("miner_harness.cli.app.cmd_analyze", new=AsyncMock(return_value=0)):
            result = main(["analyze", "carajas", "--bbox", "-51.5", "-7.0", "-49.0", "-5.0"])
        assert result == 0

    def test_cache_no_subcommand(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Should show help or return error
        with pytest.raises(SystemExit):
            main(["cache"])
