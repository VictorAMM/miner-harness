"""ProspectivityMLScorer — score de prospectividade via RandomForest.

Substitui o ProspectivityScorer (weighted overlay) por um modelo ML
pré-treinado que combina 15 features extraídas do contexto geológico
(geoquímica, gravimetria, Sentinel-2, ocorrências) para produzir uma
probabilidade de mineralização (0–100) por região de análise.

Comparação de abordagens:
  - Weighted overlay (F3): regras perito-definidas, pesos fixos
  - RandomForest (F8): pesos aprendidos, não-linear, feature importance

O modelo pré-treinado (rf_prospectivity_v1.joblib) é distribuído com o
pacote. O usuário pode substituí-lo via --rf-model <path> para usar um
modelo treinado com seus próprios dados de campo.

Fallback: se sklearn não estiver instalado ou o modelo falhar ao carregar,
retorna None e o contexto continua sem o bloco ml_prospectivity.

Ref: PRD-002 F8
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from miner_harness.ml.feature_builder import FEATURE_NAMES, MLFeatureBuilder

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL_PATH: Path = Path(__file__).parent / "model" / "rf_prospectivity_v1.joblib"

# Chaves computadas — não são fontes de dados brutas
# (não devem ser contadas como "dados disponíveis" pelo ConfidenceCalibrator)
_LABEL = "ml_prospectivity"


@dataclass
class MLProspectivityResult:
    """Resultado do modelo RF de prospectividade para uma região.

    Attributes:
        rf_probability: Probabilidade de mineralização (0.0–1.0).
        rf_score: rf_probability × 100 (escala 0–100, compatível com ProspectivityGrid).
        features: Dict feature_name → valor usado na predição.
        feature_importance: Dict feature_name → importância relativa (soma ≈ 1.0).
        model_version: Identificador da versão do modelo.
        fallback_used: True se o weighted overlay foi usado como substituto.
    """

    rf_probability: float
    rf_score: float
    features: dict[str, float] = field(default_factory=dict)
    feature_importance: dict[str, float] = field(default_factory=dict)
    model_version: str = "rf_prospectivity_v1"
    fallback_used: bool = False

    def format_for_prompt(self) -> str:
        """Formata o resultado como texto para injeção no prompt do LLM."""
        lines: list[str] = [
            "=== SCORE DE PROSPECTIVIDADE — RandomForest (PRD-002 F8) ===",
            f"Probabilidade de mineralização: {self.rf_probability * 100:.1f}%",
            f"Score prospectividade ML: {self.rf_score:.1f}/100",
        ]

        if self.fallback_used:
            lines.append("⚠ Modelo ML não disponível — score estimado por heurística.")
        else:
            lines.append(f"Modelo: {self.model_version}")

        # Features com valores não-zero
        active_features = {k: v for k, v in self.features.items() if v > 0.0}
        if active_features:
            lines.append(f"\nFeatures ativas ({len(active_features)}/{len(FEATURE_NAMES)}):")
            for name, val in sorted(active_features.items(), key=lambda x: -x[1]):
                lines.append(f"  {name}: {val:.3f}")

        # Top importâncias
        if self.feature_importance:
            top_imp = sorted(self.feature_importance.items(), key=lambda x: -x[1])[:5]
            lines.append("\nTop-5 variáveis preditoras (importância RF):")
            for i, (name, imp) in enumerate(top_imp, 1):
                bar = "█" * max(1, round(imp * 20))
                lines.append(f"  {i}. {name}: {imp:.3f} {bar}")

        # Interpretação
        if self.rf_probability >= 0.70:
            interp = "ALTA — convergência de múltiplos indicadores favoráveis"
        elif self.rf_probability >= 0.45:
            interp = "MODERADA — indicadores parcialmente favoráveis"
        else:
            interp = "BAIXA — poucos indicadores consistentes com mineralização"
        lines.append(f"\nClassificação: {interp}")
        lines.append(
            "NOTA: Score calculado em nível de bbox. "
            "Use em conjunto com a grade de prospectividade espacial."
        )

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict (para armazenar em contexto estruturado)."""
        return {
            "rf_probability": self.rf_probability,
            "rf_score": self.rf_score,
            "features": dict(self.features),
            "feature_importance": dict(self.feature_importance),
            "model_version": self.model_version,
            "fallback_used": self.fallback_used,
        }


class ProspectivityMLScorer:
    """Scorer de prospectividade baseado em RandomForest pré-treinado.

    Carrega o modelo .joblib de forma lazy na primeira chamada a score().
    Retorna None graciosamente se sklearn não estiver disponível ou se
    o modelo falhar ao carregar.

    Usage:
        scorer = ProspectivityMLScorer()
        result = scorer.score(context, bbox.as_tuple())
        if result:
            text = result.format_for_prompt()
    """

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._model_path: Path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        self._model: Any = None
        self._importances: dict[str, float] = {}
        self._loaded: bool = False
        self._load_error: str | None = None

    def score(
        self,
        context: dict[str, list[dict[str, Any]]],
        bbox_tuple: tuple[float, float, float, float],
    ) -> MLProspectivityResult | None:
        """Computa score de prospectividade ML para a região.

        Args:
            context: Contexto geológico produzido por ContextBuilder.build().
            bbox_tuple: (lon_min, lat_min, lon_max, lat_max).

        Returns:
            MLProspectivityResult ou None se sem dados ou sklearn indisponível.
        """
        # Extrair features
        builder = MLFeatureBuilder()
        features_list = builder.extract(context, bbox_tuple)
        if features_list is None:
            return None

        features_dict = dict(zip(FEATURE_NAMES, features_list, strict=True))

        # Tentar usar o modelo RF
        self._ensure_loaded()
        if self._model is not None:
            try:
                import warnings  # noqa: PLC0415

                import numpy as np  # noqa: PLC0415

                x_input = np.array(features_list, dtype=float).reshape(1, -1)  # N806
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="X does not have valid feature names",
                        category=UserWarning,
                    )
                    prob = float(self._model.predict_proba(x_input)[0][1])
                score = round(prob * 100.0, 2)
                return MLProspectivityResult(
                    rf_probability=prob,
                    rf_score=score,
                    features=features_dict,
                    feature_importance=self._importances,
                    model_version=self._model_path.stem,
                    fallback_used=False,
                )
            except Exception:
                logger.warning("ml_scorer_predict_failed", exc_info=True)

        # Fallback: heurística baseada nas features disponíveis
        prob_fallback = _heuristic_score(features_dict)
        return MLProspectivityResult(
            rf_probability=prob_fallback,
            rf_score=round(prob_fallback * 100.0, 2),
            features=features_dict,
            feature_importance={},
            model_version="heuristic_fallback",
            fallback_used=True,
        )

    def _ensure_loaded(self) -> None:
        """Carrega o modelo na primeira chamada (lazy loading)."""
        if self._loaded:
            return
        self._loaded = True
        try:
            import joblib  # type: ignore[import-untyped]  # noqa: PLC0415

            if not self._model_path.exists():
                self._load_error = f"Modelo não encontrado: {self._model_path}"
                logger.warning("ml_model_not_found", path=str(self._model_path))
                return

            model = joblib.load(self._model_path)
            # Validar que é um classificador com predict_proba
            if not hasattr(model, "predict_proba"):
                self._load_error = "Objeto carregado não é um classificador sklearn"
                logger.warning("ml_model_invalid", path=str(self._model_path))
                return

            self._model = model

            # Extrair importâncias se disponíveis
            if hasattr(model, "feature_importances_"):
                import numpy as np  # noqa: PLC0415

                imps: Any = model.feature_importances_
                names = (
                    list(model.feature_names_in_)
                    if hasattr(model, "feature_names_in_")
                    else FEATURE_NAMES
                )
                total = float(np.sum(imps))
                if total > 0:
                    self._importances = {
                        str(n): float(v) / total for n, v in zip(names, imps, strict=False)
                    }

            logger.info(
                "ml_model_loaded",
                path=str(self._model_path),
                n_features=len(FEATURE_NAMES),
            )

        except ImportError:
            self._load_error = "scikit-learn/joblib não instalado"
            logger.info("ml_scorer_sklearn_unavailable")
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("ml_model_load_failed", error=str(exc))


def _heuristic_score(features: dict[str, float]) -> float:
    """Estimativa heurística quando o modelo RF não está disponível.

    Combina as features disponíveis com pesos baseados em conhecimento
    geológico de domínio (semelhante ao weighted overlay, mas sem grade).
    """
    score = 0.0

    # Ocorrências (peso 0.35)
    occ = min(features.get("occ_density_km2", 0.0) / 0.01, 1.0)
    score += 0.35 * occ

    # Geoquímica (peso 0.25)
    cf_max = min(features.get("geochem_max_cf", 0.0) / 10.0, 1.0)
    n_anom = min(features.get("geochem_n_anomalies", 0.0) / 5.0, 1.0)
    score += 0.25 * (cf_max * 0.6 + n_anom * 0.4)

    # Gravimetria (peso 0.20)
    grad_max = min(features.get("bouguer_max_gradient", 0.0) / 5.0, 1.0)
    score += 0.20 * grad_max

    # Sentinel-2 (peso 0.20)
    s2_avg = (
        features.get("s2_clay_anom_pct", 0.0) + features.get("s2_iron_anom_pct", 0.0)
    ) / 200.0  # max 100 each → normalize to 0-1
    score += 0.20 * min(s2_avg, 1.0)

    return min(score, 1.0)
