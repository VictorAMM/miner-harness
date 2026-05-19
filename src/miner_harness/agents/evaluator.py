"""EvaluatorAgent — Integrador Final (Passo 5).

Recebe resultados dos passos 1-4 e produz análise integrada
com alvos ranqueados. Implementa o Evaluator-Optimizer pattern.

Ref: RFC-002 §4.4, §9.2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from miner_harness.agents.base import BaseAgent
from miner_harness.core.types import AnalysisStep, MineralTarget, StepResult

if TYPE_CHECKING:
    from miner_harness.connectors.ollama.client import ChatResponse

logger = structlog.get_logger(__name__)


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
            "anm",
            "usgs",
        ]

    def parse_response(self, response: ChatResponse, step: AnalysisStep) -> StepResult:
        """Parse LLM response, extracting structured MineralTargets for step 5."""
        result = super().parse_response(response, step)

        if step != AnalysisStep.TOTAL_INTEGRATION:
            return result

        targets: list[MineralTarget] = []
        try:
            parsed = self._extract_json(response.content.strip())
            for raw in parsed.get("targets", []):
                try:
                    targets.append(MineralTarget(**raw))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("target_parse_skip", reason=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.debug("targets_block_parse_skip", reason=str(exc))

        if targets:
            return result.model_copy(update={"targets": targets})
        return result
