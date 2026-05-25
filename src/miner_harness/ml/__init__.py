"""miner_harness.ml — módulo de Machine Learning para prospectividade mineral.

Implementa o RandomForest de prospectividade (PRD-002 F8):
  - MLFeatureBuilder: extração de features do contexto geológico
  - ProspectivityMLScorer: inferência com modelo pré-treinado
  - MLProspectivityResult: resultado estruturado com feature importance

Ref: PRD-002 F8
"""

from miner_harness.ml.feature_builder import FEATURE_NAMES, MLFeatureBuilder
from miner_harness.ml.scorer import MLProspectivityResult, ProspectivityMLScorer

__all__ = [
    "FEATURE_NAMES",
    "MLFeatureBuilder",
    "MLProspectivityResult",
    "ProspectivityMLScorer",
]
