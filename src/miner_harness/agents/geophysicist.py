"""GeophysicistAgent — Geofísico (Passos 3 e 4).

Ref: RFC-002 §4.4
"""

from __future__ import annotations

from miner_harness.agents.base import BaseAgent
from miner_harness.core.types import AnalysisStep


class GeophysicistAgent(BaseAgent):
    """Geofísico — analisa anomalias gravimétricas e padrões magnéticos."""

    name = "geophysicist"
    specialty = "Magnetometria, gravimetria, IP/Resistividade, anomalias"
    supported_steps = [
        AnalysisStep.MAGMATIC_FERTILITY,
        AnalysisStep.INDIRECT_EVIDENCE,
    ]

    def _get_relevant_data_keys(self, step: AnalysisStep) -> list[str]:
        # aeromag_grid: derivadas TMA do Atlas Aerogeofísico SGB (PRD-003 F10)
        # bouguer_gradient: derivadas gravimétricas (PRD-002 F5)
        # usgs: sismicidade correlaciona com anomalias geofísicas e atividade magmática
        if step == AnalysisStep.MAGMATIC_FERTILITY:
            return [
                "gravimetria",
                "bouguer_gradient",
                "aeromag_grid",
                "aerogeofisica",
                "ocorrencias",
                "usgs",
            ]
        return [
            "gravimetria",
            "bouguer_gradient",
            "aeromag_grid",
            "aerogeofisica",
            "ocorrencias",
            "usgs",
        ]
