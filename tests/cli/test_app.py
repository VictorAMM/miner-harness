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

    def test_health_command(self) -> None:
        """main(['health']) delega ao cmd_health assíncrono (linhas 195-196)."""
        from unittest.mock import AsyncMock, patch

        with patch("miner_harness.cli.app.cmd_health", new=AsyncMock(return_value=0)):
            result = main(["health"])
        assert result == 0

    def test_ensure_utf8_streams_wraps_non_utf8(self) -> None:
        """_ensure_utf8_streams substitui streams com encoding != utf-8 (linha 153)."""
        import sys
        from unittest.mock import MagicMock, patch

        from miner_harness.cli.app import _ensure_utf8_streams

        fake_buffer = MagicMock()
        fake_stream = MagicMock()
        fake_stream.encoding = "cp1252"
        fake_stream.buffer = fake_buffer

        with (
            patch.object(sys, "stdout", fake_stream),
            patch.object(sys, "stderr", fake_stream),
            patch("miner_harness.cli.app.io.TextIOWrapper", return_value=MagicMock()) as mock_wrap,
        ):
            _ensure_utf8_streams()

        # Called twice — once for stdout, once for stderr
        assert mock_wrap.call_count == 2
        mock_wrap.assert_called_with(fake_buffer, encoding="utf-8", errors="replace")

    def test_fix_windows_event_loop_win32(self) -> None:
        """_fix_windows_event_loop define WindowsSelectorEventLoopPolicy no win32."""
        import asyncio
        import sys
        from unittest.mock import patch

        from miner_harness.cli.app import _fix_windows_event_loop

        with (
            patch.object(sys, "platform", "win32"),
            patch.object(asyncio, "set_event_loop_policy") as mock_policy,
        ):
            _fix_windows_event_loop()
        mock_policy.assert_called_once()
        assert mock_policy.call_args[0][0].__class__.__name__ == "WindowsSelectorEventLoopPolicy"

    def test_fix_windows_event_loop_non_win32(self) -> None:
        """_fix_windows_event_loop não faz nada em plataformas não-Windows."""
        import asyncio
        import sys
        from unittest.mock import patch

        from miner_harness.cli.app import _fix_windows_event_loop

        with (
            patch.object(sys, "platform", "linux"),
            patch.object(asyncio, "set_event_loop_policy") as mock_policy,
        ):
            _fix_windows_event_loop()
        mock_policy.assert_not_called()
