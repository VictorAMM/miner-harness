"""SentinelIndexProcessor — processa resposta da CDSE Statistics API.

Converte a resposta JSON bruta em Sentinel2Indices com estatísticas
interpretáveis (mean, std, max, p90, area_anomalous_pct) por índice:
  - NDVI  = (B08 - B04) / (B08 + B04)
  - BSI   = ((B11+B04) - (B08+B02)) / ((B11+B04) + (B08+B02))
  - Clay  = B11 / B12   (índice de argilominerais SWIR)
  - Iron  = B04 / B02   (índice de óxidos de ferro visível)

Ref: PRD-002 F6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Rótulos legíveis para o LLM
_INDEX_LABELS: dict[str, str] = {
    "ndvi": "NDVI (B08−B04)/(B08+B04) — Índice de Vegetação",
    "bsi": "BSI Bare Soil ((B11+B04)−(B08+B02))/soma — Solo Exposto",
    "clay": "Clay Index B11/B12 — Argilominerais (SWIR)",
    "iron": "Iron Oxide B04/B02 — Óxidos de Ferro (Vis)",
}

# Dicas de interpretação geológica para cada índice
_INTERPRETATION_HINTS: dict[str, str] = {
    "ndvi": (
        "NDVI baixo (<0.2) indica vegetação esparsa/ausente: "
        "possível rocha exposta, latossolo oxidado ou inibição por solos mineralizados"
    ),
    "bsi": (
        "BSI alto (>0.1) indica solo/rocha sem cobertura vegetal: "
        "ideal para mapeamento litológico direto; anomalias coincidem com "
        "alteração hidrotermal que remove vegetação"
    ),
    "clay": (
        "Clay Index alto (>1.5) indica forte absorção em SWIR2: "
        "argilominerais hidratados (caolinita, sericita, alunita) — "
        "alteração sericítica/argílica em sistemas Au-pórfiro e epitermal"
    ),
    "iron": (
        "Iron Oxide alto (>2.0) indica predominância do vermelho sobre azul: "
        "óxidos de ferro (hematita, goethita) — gossã superficial, "
        "cap ferrugíneo sobre sulfetos oxidados; marcador direto de mineralização"
    ),
}


@dataclass
class IndexStats:
    """Estatísticas de um índice espectral calculado por célula de grade."""

    name: str
    mean: float
    std: float
    max: float
    p90: float
    area_anomalous_pct: float  # % pixels com valor anômalo (acima do threshold)
    sample_count: int
    no_data_count: int = 0


@dataclass
class Sentinel2Indices:
    """Índices espectrais Sentinel-2 calculados para um bbox.

    Cada campo é None se o índice não puder ser calculado (ex: bandas ausentes,
    cobertura de nuvem excessiva, ou área fora da cobertura do satélite).
    """

    ndvi: IndexStats | None = None
    bsi: IndexStats | None = None
    clay: IndexStats | None = None
    iron: IndexStats | None = None
    cloud_free_pct: float = 0.0
    date_from: str = ""
    date_to: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def available_indices(self) -> list[IndexStats]:
        """Retorna índices com dados válidos (sample_count > 0)."""
        result = []
        for name in ("ndvi", "bsi", "clay", "iron"):
            idx: IndexStats | None = getattr(self, name)
            if idx is not None and idx.sample_count > 0:
                result.append(idx)
        return result

    def format_for_prompt(self) -> str:
        """Formata os índices como texto para injeção no prompt do agente."""
        indices = self.available_indices
        if not indices:
            return "Sentinel-2: sem dados espectrais válidos para o período/área."

        lines: list[str] = [
            "=== ÍNDICES ESPECTRAIS SENTINEL-2 (CDSE/Copernicus) ===",
            f"Período: {self.date_from} → {self.date_to}",
            f"Pixels livres de nuvem: {self.cloud_free_pct:.1f}%",
            "Resolução: ~60m | Bandas L2A: B02, B04, B08, B11, B12\n",
        ]

        high_anom = [i for i in indices if i.area_anomalous_pct >= 20.0]
        mod_anom = [i for i in indices if 10.0 <= i.area_anomalous_pct < 20.0]
        low_anom = [i for i in indices if i.area_anomalous_pct < 10.0]

        if high_anom:
            lines.append("ANOMALIAS ESPECTRAIS SIGNIFICATIVAS (≥20% da área):")
            for idx in sorted(high_anom, key=lambda x: -x.area_anomalous_pct):
                label = _INDEX_LABELS.get(idx.name, idx.name)
                hint = _INTERPRETATION_HINTS.get(idx.name, "")
                lines.append(
                    f"  ▶ {label}\n"
                    f"    média={idx.mean:.3f} | P90={idx.p90:.3f} | máx={idx.max:.3f}"
                    f" | anomalia={idx.area_anomalous_pct:.1f}%"
                )
                if hint:
                    lines.append(f"    → {hint}")
        else:
            lines.append("Nenhuma anomalia espectral com cobertura ≥20%.")

        if mod_anom:
            lines.append("\nANOMALIAS MODERADAS (10–19% da área):")
            for idx in sorted(mod_anom, key=lambda x: -x.area_anomalous_pct):
                label = _INDEX_LABELS.get(idx.name, idx.name)
                lines.append(
                    f"  ○ {label}: média={idx.mean:.3f} | anomalia={idx.area_anomalous_pct:.1f}%"
                )

        if low_anom:
            lines.append("\nÍNDICES EM NÍVEL NORMAL (<10% anomalia):")
            for idx in sorted(low_anom, key=lambda x: x.name):
                label = _INDEX_LABELS.get(idx.name, idx.name)
                lines.append(f"  – {label}: média={idx.mean:.3f} | P90={idx.p90:.3f}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict (armazenado no CacheManager)."""
        result: dict[str, Any] = {
            "cloud_free_pct": self.cloud_free_pct,
            "date_from": self.date_from,
            "date_to": self.date_to,
        }
        for name in ("ndvi", "bsi", "clay", "iron"):
            idx: IndexStats | None = getattr(self, name)
            if idx is not None:
                result[name] = {
                    "mean": idx.mean,
                    "std": idx.std,
                    "max": idx.max,
                    "p90": idx.p90,
                    "area_anomalous_pct": idx.area_anomalous_pct,
                    "sample_count": idx.sample_count,
                    "no_data_count": idx.no_data_count,
                }
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Sentinel2Indices:
        """Desserializa de dict (recuperado do CacheManager)."""
        kwargs: dict[str, Any] = {
            "cloud_free_pct": float(d.get("cloud_free_pct", 0.0)),
            "date_from": str(d.get("date_from", "")),
            "date_to": str(d.get("date_to", "")),
        }
        for name in ("ndvi", "bsi", "clay", "iron"):
            raw = d.get(name)
            if isinstance(raw, dict):
                kwargs[name] = IndexStats(
                    name=name,
                    mean=float(raw.get("mean", 0.0)),
                    std=float(raw.get("std", 0.0)),
                    max=float(raw.get("max", 0.0)),
                    p90=float(raw.get("p90", 0.0)),
                    area_anomalous_pct=float(raw.get("area_anomalous_pct", 0.0)),
                    sample_count=int(raw.get("sample_count", 0)),
                    no_data_count=int(raw.get("no_data_count", 0)),
                )
        return cls(**kwargs)


class SentinelIndexProcessor:
    """Processa a resposta bruta da CDSE Statistics API em Sentinel2Indices.

    Extrai estatísticas (mean, std, max, p90) de cada índice e calcula
    area_anomalous_pct a partir do output de máscara binária correspondente
    (ndvi_anom, bsi_anom, clay_anom, iron_anom) — cujo mean = fração de pixels
    com valor acima do threshold geológico.

    Usage:
        processor = SentinelIndexProcessor()
        result = processor.process(raw_api_response)
        if result:
            text = result.format_for_prompt()
            cached = result.to_dict()
    """

    def process(self, raw: dict[str, Any]) -> Sentinel2Indices | None:
        """Processa resposta bruta da Statistics API.

        Args:
            raw: Dict retornado por CopernicusConnector.statistics().
                 Esperado: {"data": [{"interval": ..., "outputs": {...}}], ...}

        Returns:
            Sentinel2Indices com estatísticas por índice, ou None se
            a resposta estiver vazia, inválida ou sem outputs calculados.
        """
        if not raw:
            return None

        data_list = raw.get("data") or []
        if not data_list:
            return None

        # Usa o primeiro intervalo (mosaico de todo o período)
        entry = data_list[0]
        interval = entry.get("interval") or {}
        date_from = str(interval.get("from", ""))
        date_to = str(interval.get("to", ""))

        outputs: dict[str, Any] = entry.get("outputs") or {}
        if not outputs:
            return None

        indices: dict[str, IndexStats] = {}
        for name in ("ndvi", "bsi", "clay", "iron"):
            stats = _extract_band_stats(outputs, name)
            anom_pct = _extract_anomaly_pct(outputs, f"{name}_anom")
            if stats is not None:
                indices[name] = IndexStats(
                    name=name,
                    mean=stats["mean"],
                    std=stats["std"],
                    max=stats["max"],
                    p90=stats["p90"],
                    area_anomalous_pct=anom_pct,
                    sample_count=stats["sample_count"],
                    no_data_count=stats["no_data_count"],
                )

        if not indices:
            return None

        # Estima cobertura livre de nuvens usando contagem de pixels do NDVI
        ndvi_b0_stats = outputs.get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})
        sample = int(ndvi_b0_stats.get("sampleCount", 0))
        no_data = int(ndvi_b0_stats.get("noDataCount", 0))
        total = sample + no_data
        cloud_free_pct = (sample / total * 100.0) if total > 0 else 0.0

        return Sentinel2Indices(
            ndvi=indices.get("ndvi"),
            bsi=indices.get("bsi"),
            clay=indices.get("clay"),
            iron=indices.get("iron"),
            cloud_free_pct=cloud_free_pct,
            date_from=date_from,
            date_to=date_to,
        )


def _extract_band_stats(
    outputs: dict[str, Any],
    name: str,
) -> dict[str, Any] | None:
    """Extrai estatísticas da banda B0 de um output."""
    band_stats: dict[str, Any] = (
        outputs.get(name, {}).get("bands", {}).get("B0", {}).get("stats", {})
    )
    if not band_stats:
        return None

    mean = band_stats.get("mean")
    if mean is None:
        return None

    # p_vals typed as Any to allow both string "90.0" and integer 90 keys
    # (CDSE uses "90.0", but some mock/test responses may use integer keys)
    p_vals: Any = band_stats.get("percentileValues") or {}
    p90_raw = p_vals.get("90.0") or p_vals.get(90)
    p90 = float(p90_raw) if p90_raw is not None else float(band_stats.get("max", mean))

    return {
        "mean": float(mean),
        "std": float(band_stats.get("stDev", 0.0)),
        "max": float(band_stats.get("max", mean)),
        "p90": p90,
        "sample_count": int(band_stats.get("sampleCount", 0)),
        "no_data_count": int(band_stats.get("noDataCount", 0)),
    }


def _extract_anomaly_pct(
    outputs: dict[str, Any],
    anom_key: str,
) -> float:
    """Extrai percentual de pixels anômalos do output de máscara binária.

    O mean da máscara binária (0.0/1.0) representa a fração de pixels válidos
    onde a condição de anomalia é verdadeira. Multiplicado por 100 → porcentagem.
    """
    band_stats: dict[str, Any] = (
        outputs.get(anom_key, {}).get("bands", {}).get("B0", {}).get("stats", {})
    )
    mean = band_stats.get("mean")
    if mean is None:
        return 0.0
    return float(mean) * 100.0
