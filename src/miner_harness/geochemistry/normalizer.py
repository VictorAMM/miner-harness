"""GeochemistryNormalizer — normalização regional e análise de pathfinders.

Calcula background regional (mediana + MAD), fator de concentração (CF)
por elemento e identifica anomalias e pathfinders por sistema mineral.

O resultado é injetado no contexto do agente geoquímico como texto pré-formatado,
substituindo os valores brutos por métricas interpretáveis.

Ref: PRD-002 F2
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# Elementos pathfinder por sistema mineral (literatura SEG/AusIMM)
_PATHFINDERS: dict[str, list[str]] = {
    "Au orogênico": ["au_ppb", "au_ppm", "as_ppm", "sb_ppm", "bi_ppm", "te_ppm"],
    "Cu pórfiro": ["cu_ppm", "mo_ppm", "au_ppb", "au_ppm", "re_ppm"],
    "IOCG": ["cu_ppm", "co_ppm", "u_ppm", "la_ppm", "ce_ppm", "fe_pct"],
    "Ni-Cu sulfeto": ["ni_ppm", "cr_ppm", "co_ppm", "cu_ppm", "pt_ppb", "pd_ppb"],
    "VMS": ["zn_ppm", "pb_ppm", "cu_ppm", "ag_ppm", "ba_ppm"],
    "Sn-W": ["sn_ppm", "w_ppm", "li_ppm", "rb_ppm", "cs_ppm"],
}

# CF mínimo para classificar como anomalia
_CF_ANOMALY_THRESHOLD = 2.0

# Mínimo de amostras para calcular background confiável
_MIN_SAMPLES_RELIABLE = 5


@dataclass
class ElementStats:
    """Estatísticas de normalização para um elemento."""

    element: str
    n: int
    median: float
    mad: float
    p90: float
    cf_max: float
    n_anomalies: int
    top_objectid: int | None = None
    top_value: float | None = None


@dataclass
class GeochemNormalized:
    """Resultado da normalização geoquímica regional."""

    n_records: int
    elements: dict[str, ElementStats] = field(default_factory=dict)
    anomalous_elements: list[str] = field(default_factory=list)
    pathfinder_hits: dict[str, list[str]] = field(default_factory=dict)

    def format_for_prompt(self) -> str:
        """Formata a análise como texto para injeção no prompt."""
        if not self.elements:
            return f"Geoquímica: {self.n_records} amostras sem valores analíticos."

        lines: list[str] = [
            "=== ANÁLISE GEOQUÍMICA NORMALIZADA ===",
            f"Background calculado de N={self.n_records} amostras.\n",
        ]

        # Anomalias
        anomalous = [self.elements[e] for e in self.anomalous_elements if e in self.elements]
        normal = [
            self.elements[e] for e in sorted(self.elements) if e not in self.anomalous_elements
        ]

        if anomalous:
            lines.append("ELEMENTOS ANÔMALOS (CF > 2.0):")
            for s in sorted(anomalous, key=lambda x: -x.cf_max):
                intensity = (
                    "FORTE" if s.cf_max >= 5.0 else "MODERADA" if s.cf_max >= 3.0 else "FRACA"
                )
                lines.append(
                    f"  {s.element:<12} | mediana={s.median:.2f}"
                    f" | CF_máx={s.cf_max:.1f}"
                    f" | anomalias={s.n_anomalies}/{s.n}"
                    f" → {intensity}"
                )
                if s.top_objectid is not None:
                    lines.append(
                        f"               ↳ objectid={s.top_objectid}, valor={s.top_value:.2f}"
                    )
        else:
            lines.append("Nenhum elemento acima do threshold de anomalia (CF > 2.0).")

        if normal:
            lines.append("\nELEMENTOS ABAIXO DO THRESHOLD:")
            for s in sorted(normal, key=lambda x: -x.cf_max):
                lines.append(
                    f"  {s.element:<12} | mediana={s.median:.2f}"
                    f" | CF_máx={s.cf_max:.1f} | background normal"
                )

        # Pathfinders
        if self.pathfinder_hits:
            lines.append("\nANÁLISE DE PATHFINDERS POR SISTEMA MINERAL:")
            for system, _pf_list in sorted(self.pathfinder_hits.items()):
                all_pf = _PATHFINDERS.get(system, [])
                analyzed = [p for p in all_pf if p in self.elements]
                anomalous_pf = [p for p in analyzed if p in self.anomalous_elements]

                strength = (
                    "SUGESTÃO FORTE"
                    if len(anomalous_pf) >= 2
                    else "SUGESTÃO MODERADA"
                    if len(anomalous_pf) == 1
                    else "SEM ANOMALIA"
                )
                pf_parts = [
                    f"{p} {'✓' if p in self.anomalous_elements else '–'}" for p in analyzed[:5]
                ]
                not_analyzed = [p for p in all_pf if p not in self.elements][:3]
                if not_analyzed:
                    pf_parts.append(f"[não analisado: {', '.join(not_analyzed)}]")
                lines.append(f"  {system}: {', '.join(pf_parts)} → {strength}")
        else:
            lines.append("\nNenhum pathfinder com anomalia detectado nos elementos analisados.")

        return "\n".join(lines)


class GeochemistryNormalizer:
    """Calcula background regional e normaliza valores geoquímicos.

    Extrai os campos `analises` de registros de DadoGeoquimico,
    calcula estatísticas por elemento e identifica anomalias e pathfinders.

    Usage:
        normalizer = GeochemistryNormalizer()
        result = normalizer.normalize(records)
        if result:
            text = result.format_for_prompt()
    """

    def normalize(self, records: list[dict[str, Any]]) -> GeochemNormalized | None:
        """Normaliza registros geoquímicos.

        Args:
            records: Lista de DadoGeoquimico como dicts (com campo `analises`).

        Returns:
            GeochemNormalized ou None se não houver dados analíticos suficientes.
        """
        if not records:
            return None

        # Extrair valores por elemento
        by_element: dict[str, list[tuple[float, int]]] = {}  # element → [(value, objectid)]
        for rec in records:
            analises = rec.get("analises")
            if not isinstance(analises, dict):
                continue
            oid = rec.get("objectid", 0)
            for key, val in analises.items():
                try:
                    fval = float(val)
                except (TypeError, ValueError):
                    continue
                if fval < 0:
                    continue
                by_element.setdefault(key, []).append((fval, oid))

        if not by_element:
            return GeochemNormalized(n_records=len(records))

        elements: dict[str, ElementStats] = {}
        anomalous: list[str] = []

        for elem, pairs in sorted(by_element.items()):
            vals = [v for v, _ in pairs]
            n = len(vals)
            if n < 1:
                continue

            med = statistics.median(vals)
            mad = statistics.median([abs(v - med) for v in vals]) if n > 1 else 0.0
            p90 = _percentile(vals, 0.90)

            # Concentration factor
            if med > 0:
                cfs = [v / med for v in vals]
                cf_max = max(cfs)
                n_anom = sum(1 for cf in cfs if cf >= _CF_ANOMALY_THRESHOLD)
                # Registro mais anômalo
                max_idx = cfs.index(cf_max)
                top_val, top_oid = pairs[max_idx]
            else:
                cf_max = 0.0
                n_anom = 0
                top_val, top_oid = 0.0, None

            stats = ElementStats(
                element=elem,
                n=n,
                median=med,
                mad=mad,
                p90=p90,
                cf_max=cf_max,
                n_anomalies=n_anom,
                top_objectid=top_oid if n_anom > 0 else None,
                top_value=top_val if n_anom > 0 else None,
            )
            elements[elem] = stats

            if n_anom > 0 and n >= 2:
                anomalous.append(elem)

        # Pathfinder hits (apenas sistemas com ao menos 1 pathfinder anômalo)
        pf_hits: dict[str, list[str]] = {}
        for system, pf_list in _PATHFINDERS.items():
            hits = [p for p in pf_list if p in {e: True for e in anomalous}]
            if hits:
                pf_hits[system] = hits

        return GeochemNormalized(
            n_records=len(records),
            elements=elements,
            anomalous_elements=anomalous,
            pathfinder_hits=pf_hits,
        )


def _percentile(values: list[float], fraction: float) -> float:
    """Calcula percentil usando interpolação linear."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = fraction * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])
