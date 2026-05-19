"""RemoteSensingAgent — Sensoriamento Remoto (Passo 4).

Ref: RFC-002 §4.4
"""

from __future__ import annotations

from miner_harness.agents.base import BaseAgent
from miner_harness.core.types import AnalysisStep


class RemoteSensingAgent(BaseAgent):
    """Sensoriamento Remoto — analisa lineamentos e anomalias espectrais."""

    name = "remote_sensing"
    specialty = "Lineamentos, mapeamento espectral, anomalias de vegetação"
    supported_steps = [
        AnalysisStep.INDIRECT_EVIDENCE,
    ]

    def _get_relevant_data_keys(self, step: AnalysisStep) -> list[str]:
        # anm: concessões ativas = proxy para exploração de anomalias espectrais conhecidas
        return ["aerogeofisica", "litoestratigrafia", "ocorrencias", "anm"]
