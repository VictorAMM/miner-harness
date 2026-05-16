"""Testes do ModelRegistry."""

from __future__ import annotations

import pytest

from miner_harness.connectors.ollama.registry import (
    EMBEDDING_MODEL,
    RECOMMENDED_MODELS,
    ModelRegistry,
)
from miner_harness.core.exceptions import ModelNotAvailableError


class TestModelSpec:
    """Testes do modelo de especificação."""

    def test_default_model_exists(self) -> None:
        assert "default" in RECOMMENDED_MODELS
        default = RECOMMENDED_MODELS["default"]
        assert default.family == "qwen3"
        assert default.context_window == 32768

    def test_embedding_model(self) -> None:
        assert EMBEDDING_MODEL.name == "nomic-embed-text"
        assert EMBEDDING_MODEL.vram_required_gb <= 1.0

    def test_all_models_have_required_fields(self) -> None:
        for key, spec in RECOMMENDED_MODELS.items():
            assert spec.name, f"Model {key} missing name"
            assert spec.vram_required_gb > 0, f"Model {key} missing vram"
            assert spec.context_window > 0, f"Model {key} missing context"


class TestModelRegistry:
    """Testes do registry de modelos."""

    def test_recommend_8gb_vram(self) -> None:
        registry = ModelRegistry()
        model = registry.recommend(vram_gb=8.0)
        assert model.vram_required_gb <= 8.0
        assert model.parameters_b >= 8.0  # Should get default (8B)

    def test_recommend_4gb_vram(self) -> None:
        registry = ModelRegistry()
        model = registry.recommend(vram_gb=4.0)
        assert model.vram_required_gb <= 4.0

    def test_recommend_insufficient_vram(self) -> None:
        registry = ModelRegistry()
        with pytest.raises(ModelNotAvailableError):
            registry.recommend(vram_gb=1.0)

    def test_recommend_large_vram_gets_best(self) -> None:
        registry = ModelRegistry()
        model = registry.recommend(vram_gb=16.0)
        # Should get the largest model available
        all_params = [m.parameters_b for m in RECOMMENDED_MODELS.values()]
        assert model.parameters_b == max(all_params)

    def test_get_embedding_model(self) -> None:
        registry = ModelRegistry()
        model = registry.get_embedding_model()
        assert model.name == "nomic-embed-text"

    def test_list_recommended(self) -> None:
        registry = ModelRegistry()
        models = registry.list_recommended()
        assert len(models) >= 2
        assert "default" in models
