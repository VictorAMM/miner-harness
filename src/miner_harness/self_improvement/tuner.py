"""Auto-tuner for pipeline configuration parameters.

Analyzes performance profiles to recommend configuration adjustments
that improve throughput, cache utilization, and LLM reliability.

Ref: ASO v3 Phase 11 — Self-Improvement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.core.config import MinerHarnessConfig
    from miner_harness.self_improvement.profiler import PipelineProfile

logger = structlog.get_logger(__name__)

# Tuning thresholds
_CACHE_HIT_TARGET = 0.7  # below → slow requests to encourage reuse
_LLM_ERROR_THRESHOLD = 0.1  # above → reduce token budget
_SLOW_STEP_MS = 10_000  # above → reduce data records per prompt
_MIN_DELAY_CAP_MS = 2_000
_MIN_TOKENS = 1_024
_MIN_RECORDS = 20
_MAX_RECORDS = 100
_RECORDS_STEP = 10


@dataclass
class TunerRecommendation:
    """A single configuration tuning recommendation."""

    parameter: str
    current_value: Any
    recommended_value: Any
    reason: str
    confidence: str  # "high", "medium", "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class TuningReport:
    """Collection of tuning recommendations for one pipeline run."""

    profile_region: str
    recommendations: list[TunerRecommendation] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.recommendations) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_region": self.profile_region,
            "recommendations": [r.to_dict() for r in self.recommendations],
        }


def generate_tuning_report(
    profile: PipelineProfile,
    config: MinerHarnessConfig,
) -> TuningReport:
    """Generate tuning recommendations from a performance profile.

    Args:
        profile: Performance profile of the last pipeline run.
        config: Current configuration to compare against.

    Returns:
        TuningReport with zero or more recommendations.
    """
    report = TuningReport(profile_region=profile.region_name)

    _check_cache_hit_rate(profile, config, report)
    _check_llm_error_rate(profile, config, report)
    _check_slow_steps(profile, config, report)
    _check_no_bottlenecks(profile, config, report)

    logger.info(
        "tuning_report_generated",
        region=profile.region_name,
        recommendations=len(report.recommendations),
    )

    return report


def apply_recommendations(
    config: MinerHarnessConfig,
    recommendations: list[TunerRecommendation],
) -> MinerHarnessConfig:
    """Apply tuning recommendations to produce an updated config.

    Only applies recommendations for parameters that exist in the config.
    Returns a new MinerHarnessConfig instance; the original is unchanged.

    Args:
        config: Current configuration.
        recommendations: List of recommendations to apply.

    Returns:
        Updated MinerHarnessConfig.
    """
    from miner_harness.core.config import MinerHarnessConfig as Cfg  # noqa: PLC0415

    data = config.model_dump()

    for rec in recommendations:
        parts = rec.parameter.split(".", 1)
        if len(parts) != 2:
            continue
        section, key = parts
        if section in data and isinstance(data[section], dict) and key in data[section]:
            data[section][key] = rec.recommended_value
            logger.info(
                "config_param_tuned",
                parameter=rec.parameter,
                old=rec.current_value,
                new=rec.recommended_value,
            )

    return Cfg(**data)


# ---------------------------------------------------------------------------
# Internal checkers
# ---------------------------------------------------------------------------


def _check_cache_hit_rate(
    profile: PipelineProfile,
    config: MinerHarnessConfig,
    report: TuningReport,
) -> None:
    if 0 < profile.cache_hit_rate < _CACHE_HIT_TARGET:
        current = config.geosgb.min_delay_ms
        recommended = min(current + 100, _MIN_DELAY_CAP_MS)
        if recommended != current:
            report.recommendations.append(
                TunerRecommendation(
                    parameter="geosgb.min_delay_ms",
                    current_value=current,
                    recommended_value=recommended,
                    reason=(
                        f"Cache hit rate {profile.cache_hit_rate:.1%} is below target "
                        f"{_CACHE_HIT_TARGET:.0%} — slowing requests improves cache reuse"
                    ),
                    confidence="medium",
                )
            )


def _check_llm_error_rate(
    profile: PipelineProfile,
    config: MinerHarnessConfig,
    report: TuningReport,
) -> None:
    if profile.llm_error_rate > _LLM_ERROR_THRESHOLD:
        current = config.orchestrator.max_tokens_per_step
        recommended = max(current - 512, _MIN_TOKENS)
        if recommended != current:
            report.recommendations.append(
                TunerRecommendation(
                    parameter="orchestrator.max_tokens_per_step",
                    current_value=current,
                    recommended_value=recommended,
                    reason=(
                        f"LLM error rate {profile.llm_error_rate:.1%} exceeds "
                        f"{_LLM_ERROR_THRESHOLD:.0%} — reducing token budget reduces overload"
                    ),
                    confidence="high",
                )
            )


def _check_slow_steps(
    profile: PipelineProfile,
    config: MinerHarnessConfig,
    report: TuningReport,
) -> None:
    slow = [name for name, ms in profile.step_durations.items() if ms > _SLOW_STEP_MS]
    if not slow:
        return
    current = config.orchestrator.max_data_records_per_prompt
    if current > _MIN_RECORDS:
        recommended = max(current - _RECORDS_STEP, _MIN_RECORDS)
        report.recommendations.append(
            TunerRecommendation(
                parameter="orchestrator.max_data_records_per_prompt",
                current_value=current,
                recommended_value=recommended,
                reason=(
                    f"{len(slow)} step(s) exceeded {_SLOW_STEP_MS}ms — "
                    "reducing data records per prompt shortens LLM context"
                ),
                confidence="medium",
            )
        )


def _check_no_bottlenecks(
    profile: PipelineProfile,
    config: MinerHarnessConfig,
    report: TuningReport,
) -> None:
    # Only increase records if no slow steps and no bottlenecks
    has_slow = any(ms > _SLOW_STEP_MS for ms in profile.step_durations.values())
    if profile.bottlenecks or has_slow:
        return
    current = config.orchestrator.max_data_records_per_prompt
    if current < _MAX_RECORDS:
        recommended = min(current + _RECORDS_STEP, _MAX_RECORDS)
        report.recommendations.append(
            TunerRecommendation(
                parameter="orchestrator.max_data_records_per_prompt",
                current_value=current,
                recommended_value=recommended,
                reason=("No bottlenecks detected — increasing data records enriches analysis"),
                confidence="low",
            )
        )
