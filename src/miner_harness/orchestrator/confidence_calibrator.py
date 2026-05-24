"""ConfidenceCalibrator — recalibração de confiança por cobertura de dados.

Ajusta o nível de confiança reportado pelo LLM com base na disponibilidade
real de dados calculados (derivadas gravimétricas, normalização geoquímica)
e no volume de dados brutos disponíveis para o passo.

Critério PRD-002 §v0.7.2:
  `high` nos passos 3–5 (MAGMATIC_FERTILITY, INDIRECT_EVIDENCE,
  TOTAL_INTEGRATION) somente quando geofísica processada
  (bouguer_gradient) E geoquímica normalizada (geoquimica_normalizada)
  estiverem presentes no contexto.

O calibrador nunca eleva a confiança — apenas aplica um teto máximo
calculado objetivamente a partir dos dados presentes no contexto.
"""

from __future__ import annotations

from typing import Any

from miner_harness.core.types import AnalysisStep, Confidence

# Chaves "computadas" — produzidas internamente ou formatadas como meta-registro,
# não contam como fontes de dados brutas para cálculo de volume.
_COMPUTED_KEYS: frozenset[str] = frozenset(
    {
        "geoquimica_normalizada",
        "prospectivity_grid",
        "bouguer_gradient",
        "rag_context",
        "user_drillholes",  # meta-registro formatado (PRD-002 F7)
    }
)

# Passos que exigem dados quantitativos calculados para confiança HIGH.
# Passos 1 e 2 (TECTONIC_HISTORY, STRUCTURAL_ARCHITECTURE) trabalham com
# dados textuais/estratigráficos e não são penalizados pela ausência de
# bouguer_gradient ou geoquimica_normalizada.
_QUANTITATIVE_STEPS: frozenset[AnalysisStep] = frozenset(
    {
        AnalysisStep.MAGMATIC_FERTILITY,
        AnalysisStep.INDIRECT_EVIDENCE,
        AnalysisStep.TOTAL_INTEGRATION,
    }
)

# Limiares de registros brutos
_MIN_RECORDS_FOR_HIGH: int = 10  # ≥10 registros brutos para permitir HIGH
_MIN_RECORDS_FOR_MEDIUM: int = 3  # ≥3 registros para permitir MEDIUM

# Ranking numérico (maior = mais confiante)
_RANK: dict[Confidence, int] = {
    Confidence.INSUFFICIENT: 0,
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
}
_FROM_RANK: dict[int, Confidence] = {v: k for k, v in _RANK.items()}


def _min_confidence(a: Confidence, b: Confidence) -> Confidence:
    """Retorna o nível de confiança mais conservador."""
    return _FROM_RANK[min(_RANK[a], _RANK[b])]


class ConfidenceCalibrator:
    """Recalibra a confiança de um StepResult com base na cobertura real.

    Aplica dois tetos independentes:

    1. **Teto de dados computados** (passos 3–5):
       - bouguer_gradient E geoquimica_normalizada presentes → sem teto
       - apenas um dos dois → teto MEDIUM
       - nenhum dos dois → teto LOW

    2. **Teto de volume** (todos os passos):
       - total de registros brutos ≥ _MIN_RECORDS_FOR_HIGH → sem teto
       - ≥ _MIN_RECORDS_FOR_MEDIUM → teto MEDIUM
       - < _MIN_RECORDS_FOR_MEDIUM → teto LOW

    O teto final é o mais conservador dos dois. A confiança calibrada é
    o mínimo entre a confiança original e o teto calculado.

    Usage:
        calibrator = ConfidenceCalibrator()
        new_conf, note = calibrator.calibrate(step, confidence, geological_data)
    """

    def calibrate(
        self,
        step: AnalysisStep,
        confidence: Confidence,
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> tuple[Confidence, str | None]:
        """Recalibra a confiança e retorna nota explicativa.

        Args:
            step: Passo da análise (determina quais regras se aplicam).
            confidence: Confiança original reportada pelo LLM.
            geological_data: Contexto completo (dados brutos + computados).

        Returns:
            (Confidence calibrada, nota explicativa ou None se não mudou).
        """
        # Confiança insuficiente não pode ser melhorada nem penalizada adicionalmente.
        if confidence == Confidence.INSUFFICIENT:
            return confidence, None

        computed_cap = self._computed_cap(step, geological_data)
        volume_cap = self._volume_cap(geological_data)
        cap = _min_confidence(computed_cap, volume_cap)
        calibrated = _min_confidence(confidence, cap)

        if calibrated == confidence:
            return confidence, None

        note = self._build_note(confidence, calibrated, step, geological_data)
        return calibrated, note

    @staticmethod
    def _computed_cap(
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> Confidence:
        """Teto baseado em dados calculados (bouguer + geochem normalizado)."""
        if step not in _QUANTITATIVE_STEPS:
            return Confidence.HIGH  # passos 1 e 2 sem restrição de dados computados

        has_bouguer = bool(geological_data.get("bouguer_gradient"))
        has_geochem_norm = bool(geological_data.get("geoquimica_normalizada"))

        if has_bouguer and has_geochem_norm:
            return Confidence.HIGH
        if has_bouguer or has_geochem_norm:
            return Confidence.MEDIUM
        return Confidence.LOW

    @staticmethod
    def _volume_cap(
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> Confidence:
        """Teto baseado no volume de dados brutos disponíveis."""
        total = sum(len(v) for k, v in geological_data.items() if k not in _COMPUTED_KEYS)
        if total >= _MIN_RECORDS_FOR_HIGH:
            return Confidence.HIGH
        if total >= _MIN_RECORDS_FOR_MEDIUM:
            return Confidence.MEDIUM
        return Confidence.LOW

    @staticmethod
    def _build_note(
        original: Confidence,
        calibrated: Confidence,
        step: AnalysisStep,
        geological_data: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Constrói nota explicativa sobre o downgrade de confiança."""
        reasons: list[str] = []

        if step in _QUANTITATIVE_STEPS:
            has_bouguer = bool(geological_data.get("bouguer_gradient"))
            has_geochem_norm = bool(geological_data.get("geoquimica_normalizada"))
            if not has_bouguer:
                reasons.append("derivadas gravimétricas Bouguer ausentes")
            if not has_geochem_norm:
                reasons.append("normalização geoquímica regional ausente")

        total = sum(len(v) for k, v in geological_data.items() if k not in _COMPUTED_KEYS)
        if total < _MIN_RECORDS_FOR_HIGH:
            reasons.append(
                f"volume de dados insuficiente"
                f" ({total} registros brutos; mínimo={_MIN_RECORDS_FOR_HIGH} para 'high')"
            )

        reason_str = "; ".join(reasons) if reasons else "cobertura de dados insuficiente"
        return (
            f"Confiança recalibrada de '{original}' para '{calibrated}'"
            f" [{step.value}]: {reason_str}"
        )
