"""Testes das exceções de domínio do miner-harness."""

from __future__ import annotations

import pytest

from miner_harness.core.exceptions import (
    GeoSGBQueryError,
    InsufficientDataError,
    MinerHarnessError,
    ModelNotAvailableError,
)


class TestGeoSGBQueryError:
    def test_message_contains_service_and_code(self) -> None:
        exc = GeoSGBQueryError("ocorrencias", 400, "bad request")
        assert "ocorrencias" in str(exc)
        assert "400" in str(exc)
        assert "bad request" in str(exc)

    def test_attributes_set(self) -> None:
        exc = GeoSGBQueryError("geoquimica", 500, "server error")
        assert exc.service == "geoquimica"
        assert exc.error_code == 500

    def test_is_miner_harness_error(self) -> None:
        with pytest.raises(MinerHarnessError):
            raise GeoSGBQueryError("svc", 404, "not found")


class TestModelNotAvailableError:
    def test_message_contains_model_name(self) -> None:
        exc = ModelNotAvailableError("qwen3:8b")
        assert "qwen3:8b" in str(exc)
        assert "ollama pull" in str(exc)

    def test_model_attribute(self) -> None:
        exc = ModelNotAvailableError("llama3:70b")
        assert exc.model == "llama3:70b"


class TestInsufficientDataError:
    def test_message_contains_counts(self) -> None:
        exc = InsufficientDataError(
            "structural_geologist", ["geocronologia"], min_sources=3, active_count=2
        )
        assert "2/3" in str(exc)
        assert "geocronologia" in str(exc)

    def test_hint_present_when_missing(self) -> None:
        exc = InsufficientDataError("agent", ["svcA"], min_sources=3, active_count=2)
        assert "--min-sources" in str(exc)

    def test_no_hint_when_no_missing(self) -> None:
        exc = InsufficientDataError("agent", [], min_sources=3, active_count=3)
        assert "--min-sources" not in str(exc)

    def test_attributes_set(self) -> None:
        exc = InsufficientDataError("geo", ["svc1", "svc2"], min_sources=4, active_count=2)
        assert exc.agent == "geo"
        assert exc.missing == ["svc1", "svc2"]
        assert exc.min_sources == 4
        assert exc.active_count == 2

    def test_lower_bound_clamps_to_one(self) -> None:
        exc = InsufficientDataError("agent", ["svc"], min_sources=1, active_count=0)
        assert "--min-sources 1" in str(exc)
