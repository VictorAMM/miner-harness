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

    def test_install_with_miner_home_builds_path(self, tmp_path) -> None:
        """install --miner-home trigga construção de Path (linhas 163-165)."""
        from unittest.mock import patch

        with patch("miner_harness.cli.app.cmd_install", return_value=0) as mock_install:
            result = main(["install", "--miner-home", str(tmp_path), "--non-interactive"])
        assert result == 0
        mock_install.assert_called_once()
        call_kwargs = mock_install.call_args.kwargs
        assert call_kwargs["miner_home"] == tmp_path

    def test_keyboard_interrupt_returns_130(self) -> None:
        """KeyboardInterrupt durante comando retorna 130 (linhas 198-199)."""
        from unittest.mock import patch

        with patch("miner_harness.cli.app.cmd_validate", side_effect=KeyboardInterrupt):
            result = main(["validate", "/nonexistent.json"])
        assert result == 130

    def test_exception_in_command_returns_1(self) -> None:
        """Exceção inesperada durante comando retorna 1 (linhas 201-205)."""
        from unittest.mock import patch

        with patch("miner_harness.cli.app.cmd_validate", side_effect=RuntimeError("boom")):
            result = main(["validate", "/nonexistent.json"])
        assert result == 1
