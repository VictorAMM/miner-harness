"""Testes do SentinelIndexProcessor — parse da Statistics API e cálculos."""

from __future__ import annotations

import pytest

from miner_harness.connectors.sentinel2.processor import (
    IndexStats,
    Sentinel2Indices,
    SentinelIndexProcessor,
    _extract_anomaly_pct,
    _extract_band_stats,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_band_stats(
    mean: float = 0.4,
    std: float = 0.1,
    max_: float = 0.9,
    p90: float = 0.7,
    sample_count: int = 1000,
    no_data_count: int = 100,
) -> dict:
    return {
        "stats": {
            "mean": mean,
            "stDev": std,
            "max": max_,
            "sampleCount": sample_count,
            "noDataCount": no_data_count,
            "percentileValues": {"90.0": p90},
        }
    }


def _make_anom_band_stats(mean_frac: float = 0.25) -> dict:
    """mean_frac = fraction of anomalous pixels (0–1)."""
    return {
        "stats": {
            "mean": mean_frac,
            "stDev": 0.43,
            "max": 1.0,
            "sampleCount": 1000,
            "noDataCount": 0,
            "percentileValues": {"90.0": 1.0},
        }
    }


def _make_full_response(
    ndvi_mean: float = 0.4,
    bsi_mean: float = 0.05,
    clay_mean: float = 1.2,
    iron_mean: float = 1.8,
    ndvi_anom_frac: float = 0.1,
    bsi_anom_frac: float = 0.05,
    clay_anom_frac: float = 0.03,
    iron_anom_frac: float = 0.02,
    date_from: str = "2024-01-01T00:00:00Z",
    date_to: str = "2024-04-01T00:00:00Z",
) -> dict:
    return {
        "data": [
            {
                "interval": {"from": date_from, "to": date_to},
                "outputs": {
                    "ndvi": {"bands": {"B0": _make_band_stats(mean=ndvi_mean)}},
                    "bsi": {"bands": {"B0": _make_band_stats(mean=bsi_mean)}},
                    "clay": {"bands": {"B0": _make_band_stats(mean=clay_mean)}},
                    "iron": {"bands": {"B0": _make_band_stats(mean=iron_mean)}},
                    "ndvi_anom": {"bands": {"B0": _make_anom_band_stats(ndvi_anom_frac)}},
                    "bsi_anom": {"bands": {"B0": _make_anom_band_stats(bsi_anom_frac)}},
                    "clay_anom": {"bands": {"B0": _make_anom_band_stats(clay_anom_frac)}},
                    "iron_anom": {"bands": {"B0": _make_anom_band_stats(iron_anom_frac)}},
                },
            }
        ],
        "status": "OK",
    }


# ---------------------------------------------------------------------------
# TestExtractBandStats
# ---------------------------------------------------------------------------


class TestExtractBandStats:
    def test_extracts_all_fields(self) -> None:
        outputs = {"ndvi": {"bands": {"B0": _make_band_stats(mean=0.5, p90=0.75)}}}
        result = _extract_band_stats(outputs, "ndvi")
        assert result is not None
        assert result["mean"] == pytest.approx(0.5)
        assert result["p90"] == pytest.approx(0.75)
        assert result["sample_count"] == 1000

    def test_missing_output_returns_none(self) -> None:
        assert _extract_band_stats({}, "ndvi") is None

    def test_missing_mean_returns_none(self) -> None:
        outputs = {"ndvi": {"bands": {"B0": {"stats": {}}}}}
        assert _extract_band_stats(outputs, "ndvi") is None

    def test_present_stats_without_mean_returns_none(self) -> None:
        """Linha 277-278: band_stats não-vazio mas sem 'mean' → return None."""
        outputs = {"ndvi": {"bands": {"B0": {"stats": {"stDev": 0.1, "max": 0.8}}}}}
        assert _extract_band_stats(outputs, "ndvi") is None

    def test_percentile_int_key_fallback(self) -> None:
        """Aceita chave inteira 90 além de string '90.0'."""
        outputs = {
            "ndvi": {
                "bands": {
                    "B0": {
                        "stats": {
                            "mean": 0.3,
                            "stDev": 0.1,
                            "max": 0.8,
                            "sampleCount": 500,
                            "noDataCount": 50,
                            "percentileValues": {90: 0.65},
                        }
                    }
                }
            }
        }
        result = _extract_band_stats(outputs, "ndvi")
        assert result is not None
        assert result["p90"] == pytest.approx(0.65)

    def test_no_percentiles_uses_max(self) -> None:
        outputs = {
            "ndvi": {
                "bands": {
                    "B0": {
                        "stats": {
                            "mean": 0.3,
                            "max": 0.8,
                            "sampleCount": 100,
                            "noDataCount": 0,
                        }
                    }
                }
            }
        }
        result = _extract_band_stats(outputs, "ndvi")
        assert result is not None
        assert result["p90"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# TestExtractAnomalyPct
# ---------------------------------------------------------------------------


class TestExtractAnomalyPct:
    def test_converts_fraction_to_pct(self) -> None:
        outputs = {"ndvi_anom": {"bands": {"B0": _make_anom_band_stats(0.23)}}}
        pct = _extract_anomaly_pct(outputs, "ndvi_anom")
        assert pct == pytest.approx(23.0)

    def test_missing_key_returns_zero(self) -> None:
        assert _extract_anomaly_pct({}, "ndvi_anom") == pytest.approx(0.0)

    def test_missing_mean_returns_zero(self) -> None:
        outputs = {"ndvi_anom": {"bands": {"B0": {"stats": {}}}}}
        assert _extract_anomaly_pct(outputs, "ndvi_anom") == pytest.approx(0.0)

    def test_zero_fraction(self) -> None:
        outputs = {"ndvi_anom": {"bands": {"B0": _make_anom_band_stats(0.0)}}}
        assert _extract_anomaly_pct(outputs, "ndvi_anom") == pytest.approx(0.0)

    def test_full_anomaly(self) -> None:
        outputs = {"ndvi_anom": {"bands": {"B0": _make_anom_band_stats(1.0)}}}
        assert _extract_anomaly_pct(outputs, "ndvi_anom") == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# TestSentinelIndexProcessorProcess
# ---------------------------------------------------------------------------


class TestSentinelIndexProcessorProcess:
    def setup_method(self) -> None:
        self.proc = SentinelIndexProcessor()

    def test_returns_none_for_empty_input(self) -> None:
        assert self.proc.process({}) is None

    def test_returns_none_for_missing_data_key(self) -> None:
        assert self.proc.process({"status": "OK"}) is None

    def test_returns_none_for_empty_data_list(self) -> None:
        assert self.proc.process({"data": []}) is None

    def test_returns_none_for_missing_outputs(self) -> None:
        result = self.proc.process({"data": [{"interval": {}, "outputs": {}}]})
        assert result is None

    def test_returns_none_when_no_valid_band_outputs(self) -> None:
        """Linha 244-245: outputs não-vazio mas sem ndvi/bsi/clay/iron → indices={} → None."""
        raw = {
            "data": [
                {
                    "interval": {"from": "2024-01-01", "to": "2024-04-01"},
                    "outputs": {
                        # Banda desconhecida — não é ndvi/bsi/clay/iron
                        "unknown_band": {"bands": {"B0": {"stats": {"mean": 0.5}}}},
                    },
                }
            ]
        }
        result = self.proc.process(raw)
        assert result is None

    def test_basic_parse(self) -> None:
        raw = _make_full_response(ndvi_mean=0.35, bsi_mean=0.15)
        result = self.proc.process(raw)
        assert result is not None
        assert result.ndvi is not None
        assert result.ndvi.mean == pytest.approx(0.35)
        assert result.bsi is not None
        assert result.bsi.mean == pytest.approx(0.15)
        assert result.clay is not None
        assert result.iron is not None

    def test_date_range_parsed(self) -> None:
        raw = _make_full_response(date_from="2024-01-01T00:00:00Z", date_to="2024-04-01T00:00:00Z")
        result = self.proc.process(raw)
        assert result is not None
        assert result.date_from == "2024-01-01T00:00:00Z"
        assert result.date_to == "2024-04-01T00:00:00Z"

    def test_area_anomalous_pct_computed(self) -> None:
        raw = _make_full_response(ndvi_anom_frac=0.25, clay_anom_frac=0.30)
        result = self.proc.process(raw)
        assert result is not None
        assert result.ndvi is not None
        assert result.ndvi.area_anomalous_pct == pytest.approx(25.0)
        assert result.clay is not None
        assert result.clay.area_anomalous_pct == pytest.approx(30.0)

    def test_cloud_free_pct_calculated(self) -> None:
        raw = _make_full_response()
        result = self.proc.process(raw)
        assert result is not None
        # sample_count=1000, no_data_count=100 → 1000/1100 ≈ 90.9%
        assert result.cloud_free_pct == pytest.approx(1000 / 1100 * 100.0, abs=0.1)

    def test_available_indices_excludes_zero_samples(self) -> None:
        raw = _make_full_response()
        # Corrupt clay to zero sampleCount
        raw["data"][0]["outputs"]["clay"]["bands"]["B0"]["stats"]["sampleCount"] = 0
        result = self.proc.process(raw)
        assert result is not None
        names = [i.name for i in result.available_indices]
        assert "clay" not in names
        assert "ndvi" in names


# ---------------------------------------------------------------------------
# TestSentinel2IndicesFormatForPrompt
# ---------------------------------------------------------------------------


class TestSentinel2IndicesFormatForPrompt:
    def test_no_indices_returns_fallback(self) -> None:
        s2 = Sentinel2Indices()
        text = s2.format_for_prompt()
        assert "sem dados espectrais" in text

    def test_high_anomaly_section_shown(self) -> None:
        s2 = Sentinel2Indices(
            ndvi=IndexStats(
                name="ndvi",
                mean=0.1,
                std=0.05,
                max=0.4,
                p90=0.25,
                area_anomalous_pct=35.0,
                sample_count=500,
            )
        )
        text = s2.format_for_prompt()
        assert "ANOMALIAS ESPECTRAIS SIGNIFICATIVAS" in text
        assert "35.0%" in text

    def test_moderate_anomaly_section_shown(self) -> None:
        s2 = Sentinel2Indices(
            bsi=IndexStats(
                name="bsi",
                mean=0.12,
                std=0.04,
                max=0.5,
                p90=0.3,
                area_anomalous_pct=15.0,
                sample_count=400,
            )
        )
        text = s2.format_for_prompt()
        assert "ANOMALIAS MODERADAS" in text
        assert "15.0%" in text

    def test_normal_section_shown(self) -> None:
        s2 = Sentinel2Indices(
            iron=IndexStats(
                name="iron",
                mean=1.5,
                std=0.3,
                max=2.5,
                p90=1.9,
                area_anomalous_pct=5.0,
                sample_count=600,
            )
        )
        text = s2.format_for_prompt()
        assert "NÍVEL NORMAL" in text

    def test_interpretation_hints_shown_for_high_anomaly(self) -> None:
        s2 = Sentinel2Indices(
            clay=IndexStats(
                name="clay",
                mean=2.0,
                std=0.5,
                max=3.5,
                p90=2.8,
                area_anomalous_pct=25.0,
                sample_count=800,
            )
        )
        text = s2.format_for_prompt()
        assert "argilominerais" in text.lower() or "argílica" in text.lower()

    def test_header_includes_period(self) -> None:
        s2 = Sentinel2Indices(
            date_from="2024-01-01T00:00:00Z",
            date_to="2024-04-01T00:00:00Z",
            ndvi=IndexStats(
                name="ndvi",
                mean=0.4,
                std=0.1,
                max=0.8,
                p90=0.6,
                area_anomalous_pct=8.0,
                sample_count=1000,
            ),
        )
        text = s2.format_for_prompt()
        assert "2024-01-01" in text
        assert "2024-04-01" in text


# ---------------------------------------------------------------------------
# TestSentinel2IndicesSerializationRoundtrip
# ---------------------------------------------------------------------------


class TestSentinel2IndicesSerializationRoundtrip:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        original = Sentinel2Indices(
            ndvi=IndexStats(
                name="ndvi",
                mean=0.4,
                std=0.1,
                max=0.9,
                p90=0.7,
                area_anomalous_pct=12.0,
                sample_count=1000,
                no_data_count=50,
            ),
            bsi=IndexStats(
                name="bsi",
                mean=0.08,
                std=0.03,
                max=0.4,
                p90=0.2,
                area_anomalous_pct=5.0,
                sample_count=1000,
                no_data_count=50,
            ),
            cloud_free_pct=85.0,
            date_from="2024-01-01T00:00:00Z",
            date_to="2024-04-01T00:00:00Z",
        )
        serialized = original.to_dict()
        restored = Sentinel2Indices.from_dict(serialized)

        assert restored.cloud_free_pct == pytest.approx(85.0)
        assert restored.date_from == "2024-01-01T00:00:00Z"
        assert restored.ndvi is not None
        assert restored.ndvi.mean == pytest.approx(0.4)
        assert restored.ndvi.area_anomalous_pct == pytest.approx(12.0)
        assert restored.ndvi.no_data_count == 50
        assert restored.bsi is not None
        assert restored.bsi.mean == pytest.approx(0.08)
        # clay and iron are None
        assert restored.clay is None
        assert restored.iron is None

    def test_from_dict_empty_dict(self) -> None:
        s2 = Sentinel2Indices.from_dict({})
        assert s2.ndvi is None
        assert s2.cloud_free_pct == pytest.approx(0.0)

    def test_from_dict_ignores_invalid_index_types(self) -> None:
        d = {"ndvi": "not_a_dict", "cloud_free_pct": 70.0}
        s2 = Sentinel2Indices.from_dict(d)
        assert s2.ndvi is None
        assert s2.cloud_free_pct == pytest.approx(70.0)
