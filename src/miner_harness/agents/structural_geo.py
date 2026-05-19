"""StructuralGeoAgent — Geólogo Estrutural (Passos 1 e 2).

Ref: RFC-002 §4.4
"""

from __future__ import annotations

from miner_harness.agents.base import BaseAgent
from miner_harness.core.types import AnalysisStep


class StructuralGeoAgent(BaseAgent):
    """Geólogo Estrutural — analisa história tectônica e arquitetura estrutural."""

    name = "structural_geologist"
    specialty = "Geologia estrutural, tectônica, reconstrução crustal"
    supported_steps = [
        AnalysisStep.TECTONIC_HISTORY,
        AnalysisStep.STRUCTURAL_ARCHITECTURE,
    ]

    def _get_relevant_data_keys(self, step: AnalysisStep) -> list[str]:
        if step == AnalysisStep.TECTONIC_HISTORY:
            # usgs: sismicidade revela falhas ativas e estruturas tectônicas
            return ["litoestratigrafia", "geocronologia", "ocorrencias", "usgs"]
        return ["litoestratigrafia", "ocorrencias", "aerogeofisica", "usgs"]
