"""Tests for self_improvement.profiler module."""

from __future__ import annotations

from miner_harness.observability.metrics import MetricsCollector, StepMetrics
from miner_harness.self_improvement.profiler import (
    Bottleneck,
    PipelineProfile,
    identify_bottlenecks,
    profile_pipeline,
)


def _make_metrics(
    region: str = "TestRegion",
    steps: list[tuple[str, int]] | None = None,
    pipeline_ms: int = 0,
    llm_requests: int = 0,
    llm_errors: int = 0,
    cache_hits: int = 0,
    cache_misses: int = 0,
) -> MetricsCollector:
    m = MetricsCollector(region_name=region)
    for name, ms in steps or []:
        m.steps.append(StepMetrics(step_name=name, duration_ms=ms))
    m.llm.requests = llm_requests
    m.llm.errors = llm_errors
    if cache_hits or cache_misses:
        from miner_harness.observability.metrics import CacheMetrics

        m.cache["svc"] = CacheMetrics(hits=cache_hits, misses=cache_misses)
    if pipeline_ms:
        m.pipeline_start_time = 0.0
        m.pipeline_end_time = pipeline_ms / 1000
    return m


class TestBottleneck:
    def test_to_dict(self) -> None:
        b = Bottleneck(
            step_name="step_a",
            duration_ms=5000,
            pct_of_total=50.0,
            severity="high",
            recommendation="Reduce prompt size",
        )
        d = b.to_dict()
        assert d["step_name"] == "step_a"
        assert d["pct_of_total"] == 50.0
        assert d["severity"] == "high"

    def test_fields(self) -> None:
        b = Bottleneck("x", 1000, 10.0, "medium", "rec")
        assert b.step_name == "x"
        assert b.duration_ms == 1000


class TestPipelineProfile:
    def test_to_dict_keys(self) -> None:
        p = PipelineProfile(
            region_name="R",
            total_duration_ms=1000,
            step_durations={"a": 500, "b": 500},
        )
        d = p.to_dict()
        assert "region_name" in d
        assert "step_durations" in d
        assert "bottlenecks" in d

    def test_defaults(self) -> None:
        p = PipelineProfile(region_name="R", total_duration_ms=0)
        assert p.bottlenecks == []
        assert p.slowest_step == ""
        assert p.llm_error_rate == 0.0


class TestIdentifyBottlenecks:
    def test_empty_steps(self) -> None:
        result = identify_bottlenecks({}, 1000)
        assert result == []

    def test_zero_total_ms(self) -> None:
        result = identify_bottlenecks({"a": 500}, 0)
        assert result == []

    def test_no_bottlenecks_uniform(self) -> None:
        durations = {"a": 100, "b": 100, "c": 100}
        result = identify_bottlenecks(durations, 300)
        assert result == []

    def test_critical_bottleneck(self) -> None:
        durations = {"slow": 800, "fast": 200}
        result = identify_bottlenecks(durations, 1000)
        assert len(result) >= 1
        assert result[0].step_name == "slow"
        assert result[0].severity in ("critical", "high")

    def test_sorted_by_duration_desc(self) -> None:
        durations = {"medium": 600, "fast": 100, "slow": 900}
        result = identify_bottlenecks(durations, 1000)
        durations_list = [b.duration_ms for b in result]
        assert durations_list == sorted(durations_list, reverse=True)

    def test_medium_severity_bottleneck(self) -> None:
        """Step is_slow mas pct<=40% → severity='medium' (linhas 159-160)."""
        # slow=300 (30% < 40%), avg=142, 300>284=is_slow → medium
        durations = {"slow": 300, "a": 116, "b": 116, "c": 116, "d": 116, "e": 116, "f": 120}
        result = identify_bottlenecks(durations, 1000)
        medium_steps = [b for b in result if b.severity == "medium"]
        assert len(medium_steps) >= 1

    def test_pct_of_total_computed(self) -> None:
        durations = {"big": 700, "small": 300}
        result = identify_bottlenecks(durations, 1000)
        big = next(b for b in result if b.step_name == "big")
        assert big.pct_of_total == 70.0


class TestProfilePipeline:
    def test_basic_profile(self) -> None:
        m = _make_metrics(
            region="Carajás",
            steps=[("tectonic", 2000), ("structural", 3000)],
            pipeline_ms=5000,
        )
        p = profile_pipeline(m)
        assert p.region_name == "Carajás"
        assert p.total_duration_ms == 5000
        assert "tectonic" in p.step_durations
        assert p.slowest_step == "structural"

    def test_llm_error_rate(self) -> None:
        m = _make_metrics(llm_requests=10, llm_errors=3)
        p = profile_pipeline(m)
        assert p.llm_error_rate == 0.3

    def test_zero_llm_requests(self) -> None:
        m = _make_metrics()
        p = profile_pipeline(m)
        assert p.llm_error_rate == 0.0

    def test_cache_hit_rate(self) -> None:
        m = _make_metrics(cache_hits=8, cache_misses=2)
        p = profile_pipeline(m)
        assert p.cache_hit_rate == 0.8

    def test_empty_steps_profile(self) -> None:
        m = _make_metrics()
        p = profile_pipeline(m)
        assert p.slowest_step == ""
        assert p.avg_step_duration_ms == 0.0
