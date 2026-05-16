"""Testes para core/config.py — configuração do sistema."""

from __future__ import annotations

from pathlib import Path

from miner_harness.core.config import (
    GeoSGBConfig,
    MinerHarnessConfig,
    OrchestratorConfig,
    StorageConfig,
)
from miner_harness.core.types import AnalysisStep


class TestStorageConfig:
    """Testes para StorageConfig."""

    def test_default_miner_home(self) -> None:
        config = StorageConfig()
        assert config.miner_home == Path.home() / ".miner-harness"

    def test_derived_paths(self) -> None:
        config = StorageConfig(miner_home=Path("/tmp/test-miner"))
        assert config.cache_dir == Path("/tmp/test-miner/cache")
        assert config.regions_dir == Path("/tmp/test-miner/cache/regions")
        assert config.index_dir == Path("/tmp/test-miner/index")
        assert config.logs_dir == Path("/tmp/test-miner/logs")

    def test_ensure_dirs_creates_tree(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner-harness")
        config.ensure_dirs()
        assert config.cache_dir.exists()
        assert config.regions_dir.exists()
        assert config.index_dir.exists()
        assert config.exports_dir.exists()
        assert config.logs_dir.exists()

    def test_ensure_dirs_idempotent(self, tmp_path: Path) -> None:
        config = StorageConfig(miner_home=tmp_path / ".miner-harness")
        config.ensure_dirs()
        config.ensure_dirs()  # segunda chamada não deve falhar
        assert config.cache_dir.exists()


class TestOrchestratorConfig:
    """Testes para OrchestratorConfig."""

    def test_defaults(self) -> None:
        config = OrchestratorConfig()
        assert config.model == "qwen3:8b-q4_K_M"
        assert config.temperature == 0.3
        assert len(config.enabled_steps) == 5

    def test_all_steps_enabled_by_default(self) -> None:
        config = OrchestratorConfig()
        assert AnalysisStep.TECTONIC_HISTORY in config.enabled_steps
        assert AnalysisStep.TOTAL_INTEGRATION in config.enabled_steps


class TestGeoSGBConfig:
    """Testes para GeoSGBConfig."""

    def test_defaults(self) -> None:
        config = GeoSGBConfig()
        assert "geoportal.sgb.gov.br" in config.base_url
        assert config.min_delay_ms == 500
        assert config.max_concurrent == 3


class TestMinerHarnessConfig:
    """Testes para MinerHarnessConfig (raiz)."""

    def test_default_composition(self) -> None:
        config = MinerHarnessConfig()
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.orchestrator, OrchestratorConfig)
        assert isinstance(config.geosgb, GeoSGBConfig)

    def test_override_nested(self) -> None:
        config = MinerHarnessConfig(
            orchestrator=OrchestratorConfig(model="qwen3:4b"),
        )
        assert config.orchestrator.model == "qwen3:4b"
        assert config.storage.max_cache_size_gb == 5.0  # default mantido
