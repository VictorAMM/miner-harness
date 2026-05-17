"""Tests for MetricsCollector.

Ref: Phase 9 — Observabilidade
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from miner_harness.observability.metrics import MetricsCollector, get_metrics, reset_metrics

if TYPE_CHECKING:
    from pathlib import Path


class TestMetricsCollector:
    """Unit tests for MetricsCollector."""

    def test_cache_hit_miss(self) -> None:
        m = MetricsCollector()
        m.record_cache_hit("ocorrencias")
        m.record_cache_hit("ocorrencias")
        m.record_cache_miss("ocorrencias")
        assert m.cache["ocorrencias"].hits == 2
        assert m.cache["ocorrencias"].misses == 1
        assert m.cache["ocorrencias"].hit_rate == 2 / 3

    def test_cache_hit_rate_empty(self) -> None:
        m = MetricsCollector()
        assert m.overall_cache_hit_rate == 0.0

    def test_llm_request(self) -> None:
        m = MetricsCollector()
        m.record_llm_request(prompt_tokens=100, completion_tokens=50, duration_ms=1200)
        m.record_llm_request(prompt_tokens=80, completion_tokens=40, duration_ms=800)
        assert m.llm.requests == 2
        assert m.llm.prompt_tokens == 180
        assert m.llm.completion_tokens == 90
        assert m.llm.total_tokens == 270
        assert m.llm.avg_duration_ms == 1000.0

    def test_llm_error(self) -> None:
        m = MetricsCollector()
        m.record_llm_error()
        m.record_llm_error()
        assert m.llm.errors == 2

    def test_record_step(self) -> None:
        m = MetricsCollector()
        m.record_step("tectonic_history", duration_ms=500, tokens_used=200, confidence="high")
        assert len(m.steps) == 1
        assert m.steps[0].step_name == "tectonic_history"
        assert m.steps[0].duration_ms == 500

    def test_pipeline_timing(self) -> None:
        m = MetricsCollector()
        m.start_pipeline("Carajas", "qwen2.5:14b")
        assert m.region_name == "Carajas"
        assert m.pipeline_start_time is not None
        m.end_pipeline()
        assert m.pipeline_duration_ms >= 0
        assert m.pipeline_end_time is not None
        assert m.pipeline_end_time >= m.pipeline_start_time

    def test_to_dict(self) -> None:
        m = MetricsCollector()
        m.start_pipeline("Test", "model")
        m.record_cache_hit("ocorrencias")
        m.record_llm_request(10, 20, 100)
        m.record_step("step1", 50, tokens_used=30, confidence="medium")
        m.end_pipeline()

        d = m.to_dict()
        assert d["region_name"] == "Test"
        assert d["model_used"] == "model"
        assert "cache" in d
        assert d["cache"]["ocorrencias"]["hits"] == 1
        assert d["llm"]["requests"] == 1
        assert len(d["steps"]) == 1

    def test_export_json(self, tmp_path: Path) -> None:
        m = MetricsCollector()
        m.start_pipeline("Export", "model")
        m.end_pipeline()

        out = tmp_path / "metrics.json"
        m.export_json(out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["region_name"] == "Export"

    def test_overall_cache_hit_rate(self) -> None:
        m = MetricsCollector()
        m.record_cache_hit("a")
        m.record_cache_hit("a")
        m.record_cache_miss("b")
        m.record_cache_miss("b")
        assert m.overall_cache_hit_rate == 0.5


class TestMetricsSingleton:
    """Test get_metrics/reset_metrics."""

    def test_singleton(self) -> None:
        reset_metrics()
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_reset(self) -> None:
        reset_metrics()
        m1 = get_metrics()
        reset_metrics()
        m2 = get_metrics()
        assert m1 is not m2
