"""EvaluatorAgent — Integrador Final (Passo 5).

Recebe resultados dos passos 1-4 e produz análise integrada
com alvos ranqueados. Implementa o Evaluator-Optimizer pattern.

Ref: RFC-002 §4.4, §9.2
"""

from __future__ import annotations

from miner_harness.agents.base import BaseAgent
from miner_harness.core.types import AnalysisStep


class EvaluatorAgent(BaseAgent):
    """Integrador/Avaliador — integra resultados e gera alvos de prospecção."""

    name = "evaluator"
    specialty = "Integração multidisciplinar, validação de hipóteses"
    supported_steps = [
        AnalysisStep.TOTAL_INTEGRATION,
    ]

    def _get_relevant_data_keys(self, step: AnalysisStep) -> list[str]:
        # No passo de integração, todos os dados são relevantes
        return [
            "ocorrencias",
            "gravimetria",
            "geoquimica",
            "geocronologia",
            "litoestratigrafia",
            "aerogeofisica",
        ]
