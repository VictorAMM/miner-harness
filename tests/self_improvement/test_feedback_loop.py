"""Tests for self_improvement.feedback_loop module."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TCH003

from miner_harness.core.config import (
    GeoSGBConfig,
    MinerHarnessConfig,
    OrchestratorConfig,
    StorageConfig,
)
from miner_harness.observability.metrics import CacheMetrics, MetricsCollector, StepMetrics
from miner_harness.self_improvement.feedback_loop import FeedbackLoop, FeedbackSummary


def _make_config(tmp_path: Path) -> MinerHarnessConfig:
    return MinerHarnessConfig(
        storage=StorageConfig(miner_home=tmp_path / ".miner-harness"),
        orchestrator=OrchestratorConfig(
            max_tokens_per_step=4096,
            max_data_records_per_prompt=50,
        ),
        geosgb=GeoSGBConfig(min_delay_ms=500),
    )


def _make_metrics(
    region: str = "TestRegion",
    llm_errors: int = 0,
    llm_requests: int = 0,
) -> MetricsCollector:
    m = MetricsCollector(region_name=region)
    m.llm.requests = llm_requests
    m.llm.errors = llm_errors
    m.steps = [
        StepMetrics("step_a", duration_ms=1000),
        StepMetrics("step_b", duration_ms=1000),
    ]
    m.pipeline_start_time = 0.0
    m.pipeline_end_time = 2.0
    return m


class TestFeedbackSummary:
    def test_to_dict_keys(self) -> None:
        from miner_harness.self_improvement.profiler import PipelineProfile
        from miner_harness.self_improvement.tuner import TuningReport

        summary = FeedbackSummary(
            profile=PipelineProfile("R", 1000),
            tuning_report=TuningReport("R"),
            rca_patterns_found=2,
        )
        d = summary.to_dict()
        assert "profile" in d
        assert "tuning_report" in d
        assert d["rca_patterns_found"] == 2  # noqa: PLR2004
        assert "classification_hints" in d


class TestFeedbackLoop:
    def test_tuned_config_returns_original_when_no_changes(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        loop = FeedbackLoop(cfg, rca_dir=tmp_path / "rca", output_dir=tmp_path / "out")
        assert loop.tuned_config is cfg

    def test_run_returns_summary(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        loop = FeedbackLoop(cfg, rca_dir=tmp_path / "rca", output_dir=tmp_path / "out")
        metrics = _make_metrics()
        summary = loop.run(metrics)
        assert isinstance(summary, FeedbackSummary)
        assert summary.profile.region_name == "TestRegion"

    def test_run_with_high_llm_errors_updates_config(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        loop = FeedbackLoop(cfg, rca_dir=tmp_path / "rca", output_dir=tmp_path / "out")
        metrics = _make_metrics(llm_errors=5, llm_requests=10)
        summary = loop.run(metrics)
        assert summary.config_updated is True
        assert loop.tuned_config.orchestrator.max_tokens_per_step < 4096  # noqa: PLR2004

    def test_run_persists_tuned_config_json(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        out_dir = tmp_path / "out"
        loop = FeedbackLoop(cfg, rca_dir=tmp_path / "rca", output_dir=out_dir)
        metrics = _make_metrics(llm_errors=5, llm_requests=10)
        loop.run(metrics)
        persisted = out_dir / "tuned_config.json"
        assert persisted.exists()
        data = json.loads(persisted.read_text())
        assert "orchestrator" in data

    def test_run_loads_rca_history(self, tmp_path: Path) -> None:
        rca_dir = tmp_path / "rca"
        rca_dir.mkdir()
        rca_data = {
            "id": "rca-001",
            "classified_error": {
                "category": "NETWORK",
                "error_type": "ConnectError",
                "message": "refused",
            },
        }
        (rca_dir / "rca-001.json").write_text(json.dumps(rca_data), encoding="utf-8")

        cfg = _make_config(tmp_path)
        loop = FeedbackLoop(cfg, rca_dir=rca_dir, output_dir=tmp_path / "out")
        summary = loop.run(_make_metrics())
        assert summary.rca_patterns_found >= 1
        assert "NETWORK" in summary.classification_hints

    def test_run_no_rca_dir(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        loop = FeedbackLoop(cfg, rca_dir=tmp_path / "nonexistent", output_dir=tmp_path / "out")
        summary = loop.run(_make_metrics())
        assert summary.rca_patterns_found == 0
        assert summary.classification_hints == {}

    def test_no_update_when_healthy(self, tmp_path: Path) -> None:
        # Good cache hit rate, no LLM errors, no slow steps, max records at cap
        cfg = MinerHarnessConfig(
            storage=StorageConfig(miner_home=tmp_path / ".miner-harness"),
            orchestrator=OrchestratorConfig(max_data_records_per_prompt=100),
            geosgb=GeoSGBConfig(min_delay_ms=500),
        )
        loop = FeedbackLoop(cfg, rca_dir=tmp_path / "rca", output_dir=tmp_path / "out")
        metrics = _make_metrics()
        metrics.cache["svc"] = CacheMetrics(hits=9, misses=1)
        summary = loop.run(metrics)
        assert not summary.config_updated
