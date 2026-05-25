"""MLFeatureBuilder — extrai vetor de features a partir do contexto geológico.

Converte dados do ContextBuilder (ocorrências, geoquímica, gravimetria,
índices Sentinel-2) num vetor de 15 features numéricas para o RandomForest
de prospectividade.

Ref: PRD-002 F8
"""

from __future__ import annotations

import contextlib
import math
import statistics
from typing import Any

# Nomes das 15 features — mesma ordem do modelo treinado
FEATURE_NAMES: list[str] = [
    "occ_density_km2",  # Ocorrências minerais por km²
    "n_distinct_substances",  # Diversidade de substâncias minerais
    "geochem_mean_cf",  # Fator de concentração médio (geoquímica)
    "geochem_max_cf",  # Fator de concentração máximo
    "geochem_n_anomalies",  # Contagem de elementos anômalos (CF > 2)
    "bouguer_mean_gradient",  # Gradiente horizontal Bouguer médio (mGal/km)
    "bouguer_std_gradient",  # Desvio padrão do gradiente
    "bouguer_max_gradient",  # Gradiente máximo (controle estrutural)
    "s2_ndvi_anom_pct",  # Área com NDVI anômalo (%)
    "s2_bsi_anom_pct",  # Área com BSI anômalo (%)
    "s2_clay_anom_pct",  # Área com Clay Index anômalo (%)
    "s2_iron_anom_pct",  # Área com Iron Oxide anômalo (%)
    "n_geochem_samples",  # Volume de amostras geoquímicas
    "n_gravity_stations",  # Volume de estações gravimétricas
    "bbox_area_km2",  # Área da região de análise (km²)
]

_CF_THRESHOLD: float = 2.0
_EARTH_KM_PER_DEG_LAT: float = 111.32


class MLFeatureBuilder:
    """Extrai vetor de 15 features a partir do contexto do ContextBuilder.

    Cada feature fica em 0.0 quando a fonte de dados correspondente não
    está disponível — garantindo que o modelo degrada graciosamente.

    Usage:
        builder = MLFeatureBuilder()
        features = builder.extract(context, bbox)
        if features is not None:
            X = np.array(features).reshape(1, -1)
            prob = model.predict_proba(X)[0][1]
    """

    def extract(
        self,
        context: dict[str, list[dict[str, Any]]],
        bbox_tuple: tuple[float, float, float, float],
    ) -> list[float] | None:
        """Extrai vetor de 15 features a partir do contexto geológico.

        Args:
            context: Dicionário de contexto produzido por ContextBuilder.build().
            bbox_tuple: (lon_min, lat_min, lon_max, lat_max) da região.

        Returns:
            Lista ordenada de 15 floats (ordem de FEATURE_NAMES), ou None se
            não houver dados suficientes para justificar a inferência.
        """
        lon_min, lat_min, lon_max, lat_max = bbox_tuple
        area_km2 = _bbox_area_km2(lon_min, lat_min, lon_max, lat_max)

        # ── Ocorrências ────────────────────────────────────────────────────
        occ_records = context.get("ocorrencias", [])
        occ_count = len(occ_records)
        occ_density = occ_count / area_km2 if area_km2 > 0 else 0.0
        n_substances = float(len(_extract_substances(occ_records)))

        # ── Geoquímica ─────────────────────────────────────────────────────
        geo_records = context.get("geoquimica", [])
        geochem = _extract_geochem_features(geo_records)

        # ── Gravimetria / Bouguer ──────────────────────────────────────────
        bgrid_records = context.get("bouguer_gradient", [])
        bouguer = _extract_bouguer_features(bgrid_records)
        n_grav = float(len(context.get("gravimetria", [])))

        # ── Sentinel-2 ─────────────────────────────────────────────────────
        s2 = _extract_s2_features(context.get("sentinel2_indices", []))

        # ── Validação mínima ───────────────────────────────────────────────
        # Requer ao menos uma fonte quantitativa com dados reais
        has_data = (
            occ_count > 0
            or geochem["n_samples"] > 0
            or bouguer["mean_gradient"] > 0.0
            or s2["ndvi_anom_pct"] > 0.0
        )
        if not has_data:
            return None

        return [
            occ_density,
            n_substances,
            geochem["mean_cf"],
            geochem["max_cf"],
            float(geochem["n_anomalies"]),
            bouguer["mean_gradient"],
            bouguer["std_gradient"],
            bouguer["max_gradient"],
            s2["ndvi_anom_pct"],
            s2["bsi_anom_pct"],
            s2["clay_anom_pct"],
            s2["iron_anom_pct"],
            float(geochem["n_samples"]),
            n_grav,
            area_km2,
        ]


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _bbox_area_km2(
    lon_min: float,
    lat_min: float,
    lon_max: float,
    lat_max: float,
) -> float:
    """Área aproximada do bbox em km² (projeção equiretangular)."""
    mid_lat = (lat_min + lat_max) / 2.0
    km_per_deg_lon = _EARTH_KM_PER_DEG_LAT * math.cos(math.radians(mid_lat))
    width_km = abs(lon_max - lon_min) * km_per_deg_lon
    height_km = abs(lat_max - lat_min) * _EARTH_KM_PER_DEG_LAT
    return width_km * height_km


def _extract_substances(records: list[dict[str, Any]]) -> set[str]:
    """Extrai conjunto de substâncias minerais únicas das ocorrências."""
    substances: set[str] = set()
    for rec in records:
        with contextlib.suppress(KeyError, TypeError):
            sub = rec.get("substancia") or rec.get("substance")
            if isinstance(sub, str) and sub.strip():
                substances.add(sub.strip().lower())
    return substances


def _extract_geochem_features(
    records: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Extrai mean_cf, max_cf, n_anomalies, n_samples da lista geoquímica.

    Estima CF via comparação com a mediana do conjunto:
        CF = valor / mediana_do_elemento
    Amostras com CF > 2.0 são classificadas como anômalas.
    """
    if not records:
        return {"mean_cf": 0.0, "max_cf": 0.0, "n_anomalies": 0, "n_samples": 0}

    # Coletar valores por elemento
    by_element: dict[str, list[float]] = {}
    for rec in records:
        analises = rec.get("analises")
        if not isinstance(analises, dict):
            continue
        for key, val in analises.items():
            with contextlib.suppress(TypeError, ValueError):
                fval = float(val)
                if fval >= 0:
                    by_element.setdefault(key, []).append(fval)

    if not by_element:
        return {"mean_cf": 0.0, "max_cf": 0.0, "n_anomalies": 0, "n_samples": len(records)}

    # Calcular CF por elemento (mediana como background)
    cf_per_element: list[float] = []
    n_anomalous = 0
    for vals in by_element.values():
        if len(vals) < 2:
            continue
        med = statistics.median(vals)
        if med <= 0:
            continue
        cfs = [v / med for v in vals]
        max_cf = max(cfs)
        cf_per_element.append(max_cf)
        if max_cf >= _CF_THRESHOLD:
            n_anomalous += 1

    if not cf_per_element:
        return {"mean_cf": 0.0, "max_cf": 0.0, "n_anomalies": 0, "n_samples": len(records)}

    return {
        "mean_cf": statistics.mean(cf_per_element),
        "max_cf": max(cf_per_element),
        "n_anomalies": n_anomalous,
        "n_samples": len(records),
    }


def _extract_bouguer_features(
    bgrid_records: list[dict[str, Any]],
) -> dict[str, float]:
    """Extrai mean_gradient, std_gradient, max_gradient do contexto bouguer_gradient.

    O contexto armazena GeoJSON com propriedades {"hgm": float, ...} por célula.
    """
    empty: dict[str, float] = {
        "mean_gradient": 0.0,
        "std_gradient": 0.0,
        "max_gradient": 0.0,
    }
    if not bgrid_records:
        return empty

    geojson = bgrid_records[0].get("geojson")
    if not isinstance(geojson, dict):
        return empty

    features = geojson.get("features") or []
    hgm_vals: list[float] = []
    for feat in features:
        with contextlib.suppress(KeyError, TypeError, ValueError):
            hgm = float(feat["properties"]["hgm"])
            hgm_vals.append(hgm)

    if not hgm_vals:
        return empty

    return {
        "mean_gradient": statistics.mean(hgm_vals),
        "std_gradient": statistics.stdev(hgm_vals) if len(hgm_vals) > 1 else 0.0,
        "max_gradient": max(hgm_vals),
    }


def _extract_s2_features(
    s2_records: list[dict[str, Any]],
) -> dict[str, float]:
    """Extrai percentuais de anomalia dos índices Sentinel-2.

    O contexto armazena {"text": ..., "stats": Sentinel2Indices.to_dict()}.
    """
    empty: dict[str, float] = {
        "ndvi_anom_pct": 0.0,
        "bsi_anom_pct": 0.0,
        "clay_anom_pct": 0.0,
        "iron_anom_pct": 0.0,
    }
    if not s2_records:
        return empty

    stats = s2_records[0].get("stats")
    if not isinstance(stats, dict):
        return empty

    result: dict[str, float] = {}
    for index_name, key in (
        ("ndvi", "ndvi_anom_pct"),
        ("bsi", "bsi_anom_pct"),
        ("clay", "clay_anom_pct"),
        ("iron", "iron_anom_pct"),
    ):
        idx_stats = stats.get(index_name)
        if isinstance(idx_stats, dict):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                result[key] = float(idx_stats.get("area_anomalous_pct", 0.0))
        result.setdefault(key, 0.0)

    return result
