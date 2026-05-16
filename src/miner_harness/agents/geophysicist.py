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
        if step == AnalysisStep.MAGMATIC_FERTILITY:
            return ["gravimetria", "aerogeofisica", "ocorrencias"]
        return ["gravimetria", "aerogeofisica", "ocorrencias"]
