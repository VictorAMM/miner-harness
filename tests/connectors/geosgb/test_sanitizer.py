"""Testes do sanitizer — proteção de dados para prompts LLM."""

from __future__ import annotations

from miner_harness.connectors.geosgb.sanitizer import sanitize_for_llm, sanitize_record


class TestSanitizeForLlm:
    """Testes da sanitização de texto."""

    def test_none_returns_empty(self) -> None:
        assert sanitize_for_llm(None) == ""

    def test_normal_text_unchanged(self) -> None:
        assert sanitize_for_llm("Cobre, Ouro") == "Cobre, Ouro"

    def test_removes_control_chars(self) -> None:
        text = "Cobre\x00\x01\x02, Ouro"
        result = sanitize_for_llm(text)
        assert "\x00" not in result
        assert "Cobre" in result
        assert "Ouro" in result

    def test_preserves_newlines_and_tabs(self) -> None:
        text = "Linha1\nLinha2\tColuna"
        result = sanitize_for_llm(text)
        assert "\n" in result
        assert "\t" in result

    def test_truncates_long_text(self) -> None:
        text = "A" * 1000
        result = sanitize_for_llm(text, max_length=100)
        assert len(result) == 103  # 100 + "..."

    def test_escapes_xml_delimiters(self) -> None:
        text = '<script>alert("xss")</script>'
        result = sanitize_for_llm(text)
        assert "<" not in result
        assert ">" not in result
        assert "&lt;" in result
        assert "&gt;" in result

    def test_escapes_ampersand(self) -> None:
        result = sanitize_for_llm("Cu & Au")
        assert "&amp;" in result

    def test_short_text_no_truncation(self) -> None:
        text = "Short"
        result = sanitize_for_llm(text, max_length=500)
        assert result == "Short"


class TestSanitizeRecord:
    """Testes da sanitização de registros."""

    def test_sanitizes_string_fields(self) -> None:
        record: dict[str, object] = {
            "name": "<dangerous>",
            "value": 42,
        }
        result = sanitize_record(record)
        assert result["name"] == "&lt;dangerous&gt;"
        assert result["value"] == 42

    def test_preserves_non_string_types(self) -> None:
        record: dict[str, object] = {
            "count": 10,
            "active": True,
            "ratio": 3.14,
            "items": None,
        }
        result = sanitize_record(record)
        assert result["count"] == 10
        assert result["active"] is True
        assert result["ratio"] == 3.14
        assert result["items"] is None
