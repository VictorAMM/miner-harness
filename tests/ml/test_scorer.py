"""Testes para ProspectivityMLScorer e MLProspectivityResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from miner_harness.ml.feature_builder import FEATURE_NAMES
from miner_harness.ml.scorer import (
    MLProspectivityResult,
    ProspectivityMLScorer,
    _heuristic_score,
)

BBOX_CARAJAS = (-51.0, -6.5, -50.0, -5.5)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_full_context() -> dict[str, Any]:
    """Contexto com dados suficientes para extração de features."""
    return {
        "ocorrencias": [
            {
                "substancia": "OURO",
                "coordenada": {"longitude": -50.5, "latitude": -6.0},
            }
            for _ in range(5)
        ],
        "geoquimica": [
            {
                "coordenada": {"longitude": -50.5, "latitude": -6.0},
                "analises": {"au_ppb": 100.0 if i < 3 else 10.0},
            }
            for i in range(5)
        ],
        "gravimetria": [{}] * 8,
        "bouguer_gradient": [
            {
                "geojson": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {},
                            "properties": {"hgm": float(v), "is_lineament": False},
                        }
                        for v in [1.0, 2.0, 3.0]
                    ],
                }
            }
        ],
    }


def _make_result(rf_prob: float = 0.75) -> MLProspectivityResult:
    return MLProspectivityResult(
        rf_probability=rf_prob,
        rf_score=rf_prob * 100,
        features={"occ_density_km2": 0.001},
        feature_importance={"occ_density_km2": 0.35, "geochem_max_cf": 0.20},
    )


# ---------------------------------------------------------------------------
# Testes de MLProspectivityResult
# ---------------------------------------------------------------------------


class TestMLProspectivityResult:
    def test_to_dict_round_trip(self) -> None:
        result = _make_result(0.80)
        d = result.to_dict()
        assert d["rf_probability"] == pytest.approx(0.80)
        assert d["rf_score"] == pytest.approx(80.0)
        assert isinstance(d["features"], dict)
        assert isinstance(d["feature_importance"], dict)
        assert d["fallback_used"] is False

    def test_format_for_prompt_high_prob(self) -> None:
        result = _make_result(0.82)
        text = result.format_for_prompt()
        assert "82.0%" in text
        assert "ALTA" in text

    def test_format_for_prompt_moderate_prob(self) -> None:
        result = _make_result(0.55)
        text = result.format_for_prompt()
        assert "MODERADA" in text

    def test_format_for_prompt_low_prob(self) -> None:
        result = _make_result(0.30)
        text = result.format_for_prompt()
        assert "BAIXA" in text

    def test_format_for_prompt_fallback_warning(self) -> None:
        result = MLProspectivityResult(
            rf_probability=0.5,
            rf_score=50.0,
            fallback_used=True,
        )
        text = result.format_for_prompt()
        assert "Modelo ML não disponível" in text

    def test_format_includes_top5_importances(self) -> None:
        importance = {f: 0.1 for f in FEATURE_NAMES[:5]}
        result = MLProspectivityResult(
            rf_probability=0.6,
            rf_score=60.0,
            feature_importance=importance,
        )
        text = result.format_for_prompt()
        assert "Top-5" in text

    def test_format_shows_active_features(self) -> None:
        result = MLProspectivityResult(
            rf_probability=0.7,
            rf_score=70.0,
            features={"occ_density_km2": 0.002, "geochem_max_cf": 0.0},
        )
        text = result.format_for_prompt()
        # Somente features não-zero aparecem
        assert "occ_density_km2" in text

    def test_model_version_in_dict(self) -> None:
        result = _make_result()
        d = result.to_dict()
        assert d["model_version"] == "rf_prospectivity_v1"


# ---------------------------------------------------------------------------
# Testes de _heuristic_score
# ---------------------------------------------------------------------------


class TestHeuristicScore:
    def test_zero_features_returns_zero(self) -> None:
        score = _heuristic_score({f: 0.0 for f in FEATURE_NAMES})
        assert score == pytest.approx(0.0)

    def test_high_occurrences_raises_score(self) -> None:
        features = {f: 0.0 for f in FEATURE_NAMES}
        features["occ_density_km2"] = 0.05  # muito alto
        score = _heuristic_score(features)
        assert score > 0.30

    def test_max_features_gives_high_score(self) -> None:
        features = {
            "occ_density_km2": 1.0,
            "geochem_max_cf": 100.0,
            "geochem_n_anomalies": 10.0,
            "bouguer_max_gradient": 50.0,
            "s2_clay_anom_pct": 100.0,
            "s2_iron_anom_pct": 100.0,
        }
        for f in FEATURE_NAMES:
            features.setdefault(f, 0.0)
        score = _heuristic_score(features)
        assert score >= 0.90  # score máximo ≈ 1.0

    def test_score_capped_at_1(self) -> None:
        features = {f: 9999.0 for f in FEATURE_NAMES}
        score = _heuristic_score(features)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# Testes de ProspectivityMLScorer — sem modelo real
# ---------------------------------------------------------------------------


class TestProspectivityMLScorerFallback:
    def test_returns_none_when_no_data(self) -> None:
        scorer = ProspectivityMLScorer(model_path="/nonexistent/model.joblib")
        result = scorer.score({}, BBOX_CARAJAS)
        assert result is None

    def test_returns_fallback_when_model_missing(self) -> None:
        scorer = ProspectivityMLScorer(model_path="/nonexistent/model.joblib")
        context = _make_full_context()
        result = scorer.score(context, BBOX_CARAJAS)
        assert result is not None
        assert result.fallback_used is True
        assert 0.0 <= result.rf_probability <= 1.0
        assert 0.0 <= result.rf_score <= 100.0

    def test_fallback_result_has_features(self) -> None:
        scorer = ProspectivityMLScorer(model_path="/nonexistent/model.joblib")
        context = _make_full_context()
        result = scorer.score(context, BBOX_CARAJAS)
        assert result is not None
        assert len(result.features) == len(FEATURE_NAMES)

    def test_load_error_stored(self) -> None:
        scorer = ProspectivityMLScorer(model_path="/nonexistent/model.joblib")
        scorer._ensure_loaded()
        assert scorer._model is None
        assert scorer._load_error is not None

    def test_lazy_loading(self) -> None:
        """O modelo não deve ser carregado no __init__."""
        scorer = ProspectivityMLScorer(model_path="/nonexistent.joblib")
        assert not scorer._loaded
        assert scorer._model is None


# ---------------------------------------------------------------------------
# Testes de ProspectivityMLScorer — com modelo real
# ---------------------------------------------------------------------------


class TestProspectivityMLScorerWithModel:
    @pytest.fixture
    def scorer_with_model(self) -> ProspectivityMLScorer:
        """Scorer com o modelo semente pré-treinado."""
        model_path = (
            Path(__file__).parent.parent.parent
            / "src/miner_harness/ml/model/rf_prospectivity_v1.joblib"
        )
        if not model_path.exists():
            pytest.skip("Modelo RF não encontrado — execute scripts/train_rf_seed.py")
        return ProspectivityMLScorer(model_path=model_path)

    def test_returns_result_with_data(self, scorer_with_model: ProspectivityMLScorer) -> None:
        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        assert not result.fallback_used

    def test_probability_in_range(self, scorer_with_model: ProspectivityMLScorer) -> None:
        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        assert 0.0 <= result.rf_probability <= 1.0

    def test_score_matches_probability(self, scorer_with_model: ProspectivityMLScorer) -> None:
        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        assert result.rf_score == pytest.approx(result.rf_probability * 100, abs=0.1)

    def test_feature_importance_available(self, scorer_with_model: ProspectivityMLScorer) -> None:
        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        assert len(result.feature_importance) > 0
        total = sum(result.feature_importance.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_model_version_set(self, scorer_with_model: ProspectivityMLScorer) -> None:
        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        assert "rf_prospectivity" in result.model_version

    def test_format_for_prompt_contains_score(
        self, scorer_with_model: ProspectivityMLScorer
    ) -> None:
        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        text = result.format_for_prompt()
        assert "RandomForest" in text
        assert "Score prospectividade ML" in text

    def test_to_dict_serializable(self, scorer_with_model: ProspectivityMLScorer) -> None:
        """to_dict() deve retornar apenas tipos JSON-serializáveis."""
        import json

        context = _make_full_context()
        result = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result is not None
        d = result.to_dict()
        # Deve serializar sem erros
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_second_call_uses_cached_model(self, scorer_with_model: ProspectivityMLScorer) -> None:
        context = _make_full_context()
        scorer_with_model.score(context, BBOX_CARAJAS)
        assert scorer_with_model._loaded
        # Segunda chamada — model já carregado
        result2 = scorer_with_model.score(context, BBOX_CARAJAS)
        assert result2 is not None


# ---------------------------------------------------------------------------
# Testes de integração: scorer + context_builder key
# ---------------------------------------------------------------------------


class TestMLScorerContextKey:
    def test_result_can_be_stored_as_context_record(self) -> None:
        """Verifica que o resultado pode ser armazenado no contexto ContextBuilder."""
        scorer = ProspectivityMLScorer(model_path="/nonexistent.joblib")
        context = _make_full_context()
        result = scorer.score(context, BBOX_CARAJAS)
        assert result is not None

        # Simular como o ContextBuilder armazena o resultado
        context["ml_prospectivity"] = [
            {"text": result.format_for_prompt(), "stats": result.to_dict()}
        ]
        ml_records = context["ml_prospectivity"]
        assert len(ml_records) == 1
        assert "RandomForest" in ml_records[0]["text"]
        assert "rf_score" in ml_records[0]["stats"]


# ---------------------------------------------------------------------------
# Testes de _ensure_loaded — branches de erro (linhas 184-185, 214-216, 242-247)
# ---------------------------------------------------------------------------


class TestEnsureLoadedErrorBranches:
    """Cobre handlers de erro dentro de _ensure_loaded."""

    def test_predict_exception_falls_back(self) -> None:
        """Linha 184-185: exceção em predict_proba → except → fallback heurístico."""
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.predict_proba.side_effect = RuntimeError("GPU OOM")
        mock_model.feature_importances_ = []
        scorer = ProspectivityMLScorer(model_path="/nonexistent.joblib")
        # Injetar modelo diretamente para pular _ensure_loaded
        scorer._model = mock_model
        scorer._loaded = True

        context = _make_full_context()
        result = scorer.score(context, BBOX_CARAJAS)
        assert result is not None
        assert result.fallback_used is True  # fallback heurístico ativado

    def test_model_invalid_no_predict_proba(self, tmp_path: Path) -> None:
        """Linhas 214-216: modelo carregado sem predict_proba → _load_error."""
        import joblib

        model_file = tmp_path / "bad_model.joblib"
        joblib.dump({"not": "a classifier"}, model_file)
        scorer = ProspectivityMLScorer(model_path=str(model_file))
        scorer._ensure_loaded()
        assert scorer._model is None
        assert scorer._load_error is not None
        assert "classificador" in scorer._load_error.lower()

    def test_import_error_when_joblib_missing(self) -> None:
        """Linhas 242-244: ImportError → _load_error = 'scikit-learn/joblib não instalado'."""
        import sys
        from unittest.mock import patch

        scorer = ProspectivityMLScorer(model_path="/nonexistent.joblib")
        # Remover joblib de sys.modules para forçar ImportError no próximo import
        with patch.dict(sys.modules, {"joblib": None}):
            scorer._ensure_loaded()
        assert scorer._load_error == "scikit-learn/joblib não instalado"

    def test_generic_exception_in_load(self, tmp_path: Path) -> None:
        """Linhas 245-247: Exception genérica → _load_error = str(exc)."""
        from unittest.mock import patch

        import joblib

        model_file = tmp_path / "model.joblib"
        joblib.dump({"not": "a classifier"}, model_file)

        # Fazer o joblib.load lançar Exception genérica
        def _bad_load(*_args: object, **_kwargs: object) -> None:
            raise OSError("disk read error")

        scorer = ProspectivityMLScorer(model_path=str(model_file))
        with patch("joblib.load", side_effect=_bad_load):
            scorer._ensure_loaded()
        assert "disk read error" in (scorer._load_error or "")
