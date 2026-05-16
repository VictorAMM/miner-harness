"""GeochemistAgent — Geoquímico (Passos 3 e 4).

Ref: RFC-002 §4.4
"""

from __future__ import annotations

from miner_harness.agents.base import BaseAgent
from miner_harness.core.types import AnalysisStep


class GeochemistAgent(BaseAgent):
    """Geoquímico — analisa assinaturas geoquímicas e alteração hidrotermal."""

    name = "geochemist"
    specialty = "Assinaturas geoquímicas, isotopia, alteração hidrotermal"
    supported_steps = [
        AnalysisStep.MAGMATIC_FERTILITY,
        AnalysisStep.INDIRECT_EVIDENCE,
    ]

    def _get_relevant_data_keys(self, step: AnalysisStep) -> list[str]:
        if step == AnalysisStep.MAGMATIC_FERTILITY:
            return ["geoquimica", "ocorrencias", "geocronologia"]
        return ["geoquimica", "ocorrencias"]
