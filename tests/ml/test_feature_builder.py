"""Testes para MLFeatureBuilder — extração de features do contexto geológico."""

from __future__ import annotations

from typing import Any

import pytest

from miner_harness.ml.feature_builder import (
    FEATURE_NAMES,
    MLFeatureBuilder,
    _bbox_area_km2,
    _extract_bouguer_features,
    _extract_geochem_features,
    _extract_s2_features,
    _extract_substances,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BBOX_CARAJAS = (-51.0, -6.5, -50.0, -5.5)  # ~11_000 km²


def _make_occ_records(n: int = 3) -> list[dict[str, Any]]:
    """Gera registros de ocorrências com coordenadas e substâncias."""
    records = []
    for i in range(n):
        records.append(
            {
                "objectid": i + 1,
                "substancia": ["OURO", "COBRE", "FERRO"][i % 3],
                "coordenada": {"longitude": -50.5 + i * 0.1, "latitude": -6.0},
            }
        )
    return records


def _make_geo_records(n: int = 5) -> list[dict[str, Any]]:
    """Gera registros geoquímicos com valores anômalos."""
    records = []
    for i in range(n):
        # Au com CF ~5 nos primeiros, ~1 nos últimos
        au_val = 50.0 if i < 3 else 8.0
        records.append(
            {
                "objectid": i + 1,
                "coordenada": {"longitude": -50.5, "latitude": -6.0},
                "analises": {"au_ppb": au_val, "cu_ppm": 200.0 if i < 2 else 50.0},
            }
        )
    return records


def _make_bouguer_geojson(hgm_vals: list[float]) -> dict[str, Any]:
    """Cria um GeoJSON de grade bouguer com HGM fornecidos."""
    features = []
    for _i, hgm in enumerate(hgm_vals):
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {"bouguer": -20.0, "hgm": hgm, "is_lineament": hgm > 2.0},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _make_s2_stats(
    ndvi_anom: float = 30.0,
    bsi_anom: float = 20.0,
    clay_anom: float = 40.0,
    iron_anom: float = 25.0,
) -> dict[str, Any]:
    """Cria stats Sentinel-2 para contexto."""
    return {
        "ndvi": {"area_anomalous_pct": ndvi_anom, "mean": 0.15, "sample_count": 100},
        "bsi": {"area_anomalous_pct": bsi_anom, "mean": 0.12, "sample_count": 100},
        "clay": {"area_anomalous_pct": clay_anom, "mean": 1.6, "sample_count": 100},
        "iron": {"area_anomalous_pct": iron_anom, "mean": 2.1, "sample_count": 100},
    }


# ---------------------------------------------------------------------------
# Testes de _bbox_area_km2
# ---------------------------------------------------------------------------


class TestBboxAreaKm2:
    def test_carajas_approximate(self) -> None:
        area = _bbox_area_km2(*BBOX_CARAJAS)
        # 1° × 1° próximo à equatorial ≈ 12_000 km²; aceitar 8k–16k
        assert 8_000 < area < 16_000

    def test_zero_width(self) -> None:
        area = _bbox_area_km2(-50.0, -6.0, -50.0, -5.0)
        assert area == 0.0

    def test_zero_height(self) -> None:
        area = _bbox_area_km2(-51.0, -6.0, -50.0, -6.0)
        assert area == 0.0

    def test_large_bbox(self) -> None:
        area = _bbox_area_km2(-60.0, -15.0, -40.0, 0.0)
        assert area > 1_000_000  # 20° × 15° = vários milhões km²


# ---------------------------------------------------------------------------
# Testes de _extract_substances
# ---------------------------------------------------------------------------


class TestExtractSubstances:
    def test_distinct_substances(self) -> None:
        records = _make_occ_records(6)
        subs = _extract_substances(records)
        assert "ouro" in subs
        assert "cobre" in subs
        assert "ferro" in subs

    def test_empty_records(self) -> None:
        assert _extract_substances([]) == set()

    def test_missing_substancia_key(self) -> None:
        records = [{"objectid": 1, "coordenada": {}}]
        subs = _extract_substances(records)
        assert len(subs) == 0

    def test_deduplication(self) -> None:
        records = [{"substancia": "OURO"}, {"substancia": "ouro"}]
        subs = _extract_substances(records)
        assert len(subs) == 1


# ---------------------------------------------------------------------------
# Testes de _extract_geochem_features
# ---------------------------------------------------------------------------


class TestExtractGeochemFeatures:
    def test_anomalous_au(self) -> None:
        records = _make_geo_records(5)
        result = _extract_geochem_features(records)
        assert result["n_samples"] == 5
        assert result["max_cf"] > 2.0
        assert result["n_anomalies"] >= 1

    def test_empty_records(self) -> None:
        result = _extract_geochem_features([])
        assert result["mean_cf"] == 0.0
        assert result["max_cf"] == 0.0
        assert result["n_anomalies"] == 0
        assert result["n_samples"] == 0

    def test_records_without_analises(self) -> None:
        records = [{"objectid": 1, "coordenada": {"longitude": -50.0, "latitude": -6.0}}]
        result = _extract_geochem_features(records)
        assert result["mean_cf"] == 0.0
        assert result["n_samples"] == 1

    def test_insufficient_samples_per_element(self) -> None:
        # Somente 1 amostra → mediana não confiável → CF ignorado
        records = [{"analises": {"au_ppb": 100.0}}]
        result = _extract_geochem_features(records)
        assert result["mean_cf"] == 0.0

    def test_negative_values_ignored(self) -> None:
        records = [
            {"analises": {"au_ppb": -9.0}},
            {"analises": {"au_ppb": -99.0}},
        ]
        result = _extract_geochem_features(records)
        assert result["mean_cf"] == 0.0


# ---------------------------------------------------------------------------
# Testes de _extract_bouguer_features
# ---------------------------------------------------------------------------


class TestExtractBouguerFeatures:
    def test_with_valid_geojson(self) -> None:
        hgm_vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        geojson = _make_bouguer_geojson(hgm_vals)
        records = [{"text": "...", "geojson": geojson}]
        result = _extract_bouguer_features(records)
        assert result["mean_gradient"] == pytest.approx(3.0)
        assert result["max_gradient"] == pytest.approx(5.0)
        assert result["std_gradient"] > 0

    def test_empty_records(self) -> None:
        result = _extract_bouguer_features([])
        assert result["mean_gradient"] == 0.0
        assert result["max_gradient"] == 0.0

    def test_no_geojson_key(self) -> None:
        result = _extract_bouguer_features([{"text": "only text"}])
        assert result["mean_gradient"] == 0.0

    def test_single_cell(self) -> None:
        geojson = _make_bouguer_geojson([2.5])
        records = [{"geojson": geojson}]
        result = _extract_bouguer_features(records)
        assert result["mean_gradient"] == pytest.approx(2.5)
        assert result["std_gradient"] == 0.0  # stdev de 1 elemento


# ---------------------------------------------------------------------------
# Testes de _extract_s2_features
# ---------------------------------------------------------------------------


class TestExtractS2Features:
    def test_full_stats(self) -> None:
        stats = _make_s2_stats(ndvi_anom=30.0, bsi_anom=20.0, clay_anom=40.0, iron_anom=25.0)
        records = [{"text": "...", "stats": stats}]
        result = _extract_s2_features(records)
        assert result["ndvi_anom_pct"] == pytest.approx(30.0)
        assert result["clay_anom_pct"] == pytest.approx(40.0)
        assert result["iron_anom_pct"] == pytest.approx(25.0)

    def test_empty_records(self) -> None:
        result = _extract_s2_features([])
        assert result["ndvi_anom_pct"] == 0.0
        assert result["clay_anom_pct"] == 0.0

    def test_no_stats_key(self) -> None:
        result = _extract_s2_features([{"text": "no stats"}])
        assert result["bsi_anom_pct"] == 0.0

    def test_partial_indices(self) -> None:
        # Somente NDVI disponível
        stats = {"ndvi": {"area_anomalous_pct": 45.0, "sample_count": 50}}
        result = _extract_s2_features([{"stats": stats}])
        assert result["ndvi_anom_pct"] == pytest.approx(45.0)
        assert result["clay_anom_pct"] == 0.0


# ---------------------------------------------------------------------------
# Testes de MLFeatureBuilder.extract
# ---------------------------------------------------------------------------


class TestMLFeatureBuilderExtract:
    def _full_context(self) -> dict[str, Any]:
        """Contexto completo com todos os dados disponíveis."""
        return {
            "ocorrencias": _make_occ_records(5),
            "geoquimica": _make_geo_records(5),
            "gravimetria": [{}] * 10,
            "bouguer_gradient": [{"geojson": _make_bouguer_geojson([1.0, 2.0, 3.0, 4.0, 5.0])}],
            "sentinel2_indices": [{"stats": _make_s2_stats()}],
        }

    def test_returns_15_features(self) -> None:
        builder = MLFeatureBuilder()
        features = builder.extract(self._full_context(), BBOX_CARAJAS)
        assert features is not None
        assert len(features) == len(FEATURE_NAMES)

    def test_all_features_non_negative(self) -> None:
        builder = MLFeatureBuilder()
        features = builder.extract(self._full_context(), BBOX_CARAJAS)
        assert features is not None
        assert all(f >= 0.0 for f in features), "Todas as features devem ser >= 0"

    def test_occ_density_positive(self) -> None:
        builder = MLFeatureBuilder()
        features = builder.extract(self._full_context(), BBOX_CARAJAS)
        assert features is not None
        idx = FEATURE_NAMES.index("occ_density_km2")
        assert features[idx] > 0.0

    def test_s2_features_populated(self) -> None:
        builder = MLFeatureBuilder()
        features = builder.extract(self._full_context(), BBOX_CARAJAS)
        assert features is not None
        clay_idx = FEATURE_NAMES.index("s2_clay_anom_pct")
        assert features[clay_idx] == pytest.approx(40.0)

    def test_returns_none_when_no_data(self) -> None:
        builder = MLFeatureBuilder()
        empty_context: dict[str, Any] = {}
        result = builder.extract(empty_context, BBOX_CARAJAS)
        assert result is None

    def test_returns_none_only_rag_context(self) -> None:
        """Somente rag_context não deve ser suficiente para inferência."""
        builder = MLFeatureBuilder()
        context = {"rag_context": [{"text": "algum contexto RAG"}]}
        result = builder.extract(context, BBOX_CARAJAS)
        assert result is None

    def test_with_only_occurrences(self) -> None:
        """Apenas ocorrências devem ser suficientes (occ_count > 0)."""
        builder = MLFeatureBuilder()
        context: dict[str, Any] = {"ocorrencias": _make_occ_records(2)}
        features = builder.extract(context, BBOX_CARAJAS)
        assert features is not None

    def test_bbox_area_feature(self) -> None:
        builder = MLFeatureBuilder()
        features = builder.extract(self._full_context(), BBOX_CARAJAS)
        assert features is not None
        area_idx = FEATURE_NAMES.index("bbox_area_km2")
        area = features[area_idx]
        assert 8_000 < area < 16_000

    def test_feature_names_length(self) -> None:
        assert len(FEATURE_NAMES) == 15

    def test_geochem_features_zero_without_data(self) -> None:
        builder = MLFeatureBuilder()
        context: dict[str, Any] = {"ocorrencias": _make_occ_records(1)}
        features = builder.extract(context, BBOX_CARAJAS)
        assert features is not None
        idx_mean = FEATURE_NAMES.index("geochem_mean_cf")
        assert features[idx_mean] == 0.0


# ---------------------------------------------------------------------------
# Testes de branches de exceção em funções auxiliares (linhas 185, 230)
# ---------------------------------------------------------------------------


class TestExtractGeochemMedZero:
    """Linha 185: if med <= 0: continue — elemento com mediana zero."""

    def test_zero_median_element_skipped(self) -> None:
        """Todos os valores do elemento são 0 → median=0 → continue (linha 185)."""
        # Elemento "cu_ppm" com todos os valores = 0 → mediana = 0 → skipped
        records = [
            {
                "coordenada": {"longitude": -50.0, "latitude": -6.0},
                "analises": {"cu_ppm": 0.0},
            },
            {
                "coordenada": {"longitude": -50.1, "latitude": -6.0},
                "analises": {"cu_ppm": 0.0},
            },
        ]
        result = _extract_geochem_features(records)
        # Sem elementos com mediana > 0 → mean_cf = 0.0, max_cf = 0.0
        assert result["mean_cf"] == 0.0
        assert result["max_cf"] == 0.0


class TestExtractBouguerFeaturesEmptyHgm:
    """Linha 230: if not hgm_vals: return empty — features sem hgm válido."""

    def test_no_hgm_values_returns_empty(self) -> None:
        """Features sem propriedade 'hgm' → hgm_vals=[] → retorna empty (linha 230)."""
        bgrid_records = [
            {
                "geojson": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {},
                            # sem 'hgm' nas properties
                            "properties": {"is_lineament": False},
                        }
                    ],
                }
            }
        ]
        result = _extract_bouguer_features(bgrid_records)
        assert result["mean_gradient"] == 0.0
        assert result["std_gradient"] == 0.0
        assert result["max_gradient"] == 0.0
