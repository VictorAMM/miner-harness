"""Tests for self_improvement.tuner module."""

from __future__ import annotations

from miner_harness.core.config import GeoSGBConfig, MinerHarnessConfig, OrchestratorConfig
from miner_harness.self_improvement.profiler import Bottleneck, PipelineProfile
from miner_harness.self_improvement.tuner import (
    TunerRecommendation,
    TuningReport,
    apply_recommendations,
    generate_tuning_report,
)


def _profile(
    region: str = "R",
    cache_hit_rate: float = 0.8,
    llm_error_rate: float = 0.0,
    step_durations: dict[str, int] | None = None,
    bottlenecks: list[Bottleneck] | None = None,
) -> PipelineProfile:
    return PipelineProfile(
        region_name=region,
        total_duration_ms=sum((step_durations or {}).values()) or 1000,
        step_durations=step_durations or {},
        bottlenecks=bottlenecks or [],
        cache_hit_rate=cache_hit_rate,
        llm_error_rate=llm_error_rate,
    )


def _cfg(
    min_delay_ms: int = 500,
    max_tokens: int = 4096,
    max_records: int = 50,
) -> MinerHarnessConfig:
    return MinerHarnessConfig(
        geosgb=GeoSGBConfig(min_delay_ms=min_delay_ms),
        orchestrator=OrchestratorConfig(
            max_tokens_per_step=max_tokens,
            max_data_records_per_prompt=max_records,
        ),
    )


class TestTunerRecommendation:
    def test_to_dict(self) -> None:
        rec = TunerRecommendation(
            parameter="orchestrator.max_tokens_per_step",
            current_value=4096,
            recommended_value=3584,
            reason="LLM errors",
            confidence="high",
        )
        d = rec.to_dict()
        assert d["parameter"] == "orchestrator.max_tokens_per_step"
        assert d["recommended_value"] == 3584
        assert d["confidence"] == "high"


class TestTuningReport:
    def test_has_changes_empty(self) -> None:
        r = TuningReport(profile_region="R")
        assert not r.has_changes

    def test_has_changes_with_recs(self) -> None:
        r = TuningReport(profile_region="R")
        r.recommendations.append(TunerRecommendation("p", 1, 2, "reason", "low"))
        assert r.has_changes

    def test_to_dict(self) -> None:
        r = TuningReport(profile_region="X")
        d = r.to_dict()
        assert d["profile_region"] == "X"
        assert d["recommendations"] == []


class TestGenerateTuningReport:
    def test_no_issues_no_recs_at_max_records(self) -> None:
        # At max records (100), no increase should be suggested
        profile = _profile(cache_hit_rate=0.9, llm_error_rate=0.0)
        cfg = _cfg(max_records=100)
        report = generate_tuning_report(profile, cfg)
        assert not report.has_changes

    def test_low_cache_hit_suggests_delay_increase(self) -> None:
        profile = _profile(cache_hit_rate=0.4)
        cfg = _cfg(min_delay_ms=500)
        report = generate_tuning_report(profile, cfg)
        params = [r.parameter for r in report.recommendations]
        assert "geosgb.min_delay_ms" in params

    def test_high_llm_errors_suggest_token_reduction(self) -> None:
        profile = _profile(llm_error_rate=0.5)
        cfg = _cfg(max_tokens=4096)
        report = generate_tuning_report(profile, cfg)
        params = [r.parameter for r in report.recommendations]
        assert "orchestrator.max_tokens_per_step" in params

    def test_slow_step_suggests_record_reduction(self) -> None:
        profile = _profile(step_durations={"slow_step": 15_000}, cache_hit_rate=0.9)
        cfg = _cfg(max_records=50)
        report = generate_tuning_report(profile, cfg)
        params = [r.parameter for r in report.recommendations]
        assert "orchestrator.max_data_records_per_prompt" in params

    def test_no_bottleneck_increases_records(self) -> None:
        profile = _profile(
            step_durations={"a": 1000, "b": 1000},
            bottlenecks=[],
            cache_hit_rate=0.9,
        )
        cfg = _cfg(max_records=50)
        report = generate_tuning_report(profile, cfg)
        params = [r.parameter for r in report.recommendations]
        assert "orchestrator.max_data_records_per_prompt" in params

    def test_delay_cap_at_2000(self) -> None:
        profile = _profile(cache_hit_rate=0.1)
        cfg = _cfg(min_delay_ms=1950)
        report = generate_tuning_report(profile, cfg)
        delay_rec = next(
            (r for r in report.recommendations if r.parameter == "geosgb.min_delay_ms"),
            None,
        )
        if delay_rec:
            assert delay_rec.recommended_value <= 2000  # noqa: PLR2004

    def test_token_floor_at_1024(self) -> None:
        profile = _profile(llm_error_rate=0.9)
        cfg = _cfg(max_tokens=1200)
        report = generate_tuning_report(profile, cfg)
        tok_rec = next(
            (r for r in report.recommendations if "max_tokens" in r.parameter),
            None,
        )
        if tok_rec:
            assert tok_rec.recommended_value >= 1024  # noqa: PLR2004


class TestApplyRecommendations:
    def test_applies_valid_parameter(self) -> None:
        cfg = _cfg(max_tokens=4096)
        rec = TunerRecommendation(
            parameter="orchestrator.max_tokens_per_step",
            current_value=4096,
            recommended_value=3584,
            reason="test",
            confidence="high",
        )
        new_cfg = apply_recommendations(cfg, [rec])
        assert new_cfg.orchestrator.max_tokens_per_step == 3584  # noqa: PLR2004

    def test_ignores_unknown_parameter(self) -> None:
        cfg = _cfg()
        rec = TunerRecommendation("nonexistent.param", 1, 2, "x", "low")
        new_cfg = apply_recommendations(cfg, [rec])
        assert new_cfg is not cfg

    def test_original_config_unchanged(self) -> None:
        cfg = _cfg(max_tokens=4096)
        rec = TunerRecommendation("orchestrator.max_tokens_per_step", 4096, 2048, "r", "high")
        apply_recommendations(cfg, [rec])
        assert cfg.orchestrator.max_tokens_per_step == 4096  # noqa: PLR2004

    def test_geosgb_delay_applied(self) -> None:
        cfg = _cfg(min_delay_ms=500)
        rec = TunerRecommendation("geosgb.min_delay_ms", 500, 600, "r", "medium")
        new_cfg = apply_recommendations(cfg, [rec])
        assert new_cfg.geosgb.min_delay_ms == 600  # noqa: PLR2004

    def test_parameter_without_dot_is_skipped(self) -> None:
        """Parâmetro sem ponto é ignorado com continue (linha 123)."""
        cfg = _cfg(max_tokens=4096)
        rec = TunerRecommendation("noDotParameter", 4096, 2048, "x", "low")
        new_cfg = apply_recommendations(cfg, [rec])
        # Config não deve ter mudado
        assert new_cfg.orchestrator.max_tokens_per_step == 4096  # noqa: PLR2004
