"""Pipeline performance profiler for self-improvement.

Analyzes MetricsCollector data to identify bottlenecks and
performance trends across pipeline runs.

Ref: ASO v3 Phase 11 — Self-Improvement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from miner_harness.observability.metrics import MetricsCollector

logger = structlog.get_logger(__name__)

# A step is a bottleneck if it exceeds this multiple of the average
_BOTTLENECK_MULTIPLIER = 2.0
# A step is critical if it exceeds this fraction of total pipeline time
_CRITICAL_PCT = 60.0
_HIGH_PCT = 40.0


@dataclass
class Bottleneck:
    """Identified performance bottleneck in a pipeline step."""

    step_name: str
    duration_ms: int
    pct_of_total: float
    severity: str  # "critical", "high", "medium"
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "duration_ms": self.duration_ms,
            "pct_of_total": self.pct_of_total,
            "severity": self.severity,
            "recommendation": self.recommendation,
        }


@dataclass
class PipelineProfile:
    """Performance profile derived from a single pipeline run."""

    region_name: str
    total_duration_ms: int
    step_durations: dict[str, int] = field(default_factory=dict)
    bottlenecks: list[Bottleneck] = field(default_factory=list)
    avg_step_duration_ms: float = 0.0
    slowest_step: str = ""
    cache_hit_rate: float = 0.0
    llm_error_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_name": self.region_name,
            "total_duration_ms": self.total_duration_ms,
            "step_durations": self.step_durations,
            "bottlenecks": [b.to_dict() for b in self.bottlenecks],
            "avg_step_duration_ms": self.avg_step_duration_ms,
            "slowest_step": self.slowest_step,
            "cache_hit_rate": self.cache_hit_rate,
            "llm_error_rate": self.llm_error_rate,
        }


def profile_pipeline(metrics: MetricsCollector) -> PipelineProfile:
    """Build a performance profile from a MetricsCollector snapshot.

    Args:
        metrics: Populated MetricsCollector from a pipeline run.

    Returns:
        PipelineProfile with bottlenecks and summary statistics.
    """
    step_durations = {s.step_name: s.duration_ms for s in metrics.steps}
    total_ms = metrics.pipeline_duration_ms or sum(step_durations.values())

    avg_ms = (
        sum(step_durations.values()) / len(step_durations)
        if step_durations
        else 0.0
    )
    slowest = (
        max(step_durations, key=lambda k: step_durations[k])
        if step_durations
        else ""
    )

    llm_error_rate = 0.0
    if metrics.llm.requests > 0:
        llm_error_rate = metrics.llm.errors / metrics.llm.requests

    bottlenecks = identify_bottlenecks(step_durations, total_ms)

    profile = PipelineProfile(
        region_name=metrics.region_name,
        total_duration_ms=total_ms,
        step_durations=step_durations,
        bottlenecks=bottlenecks,
        avg_step_duration_ms=round(avg_ms, 1),
        slowest_step=slowest,
        cache_hit_rate=round(metrics.overall_cache_hit_rate, 3),
        llm_error_rate=round(llm_error_rate, 3),
    )

    logger.info(
        "pipeline_profiled",
        region=metrics.region_name,
        total_ms=total_ms,
        bottlenecks=len(bottlenecks),
        slowest_step=slowest,
    )

    return profile


def identify_bottlenecks(
    step_durations: dict[str, int],
    total_ms: int,
) -> list[Bottleneck]:
    """Identify steps that are disproportionately slow.

    A step is flagged if it exceeds 2× the average duration OR
    takes more than 40% of total pipeline time.

    Args:
        step_durations: Map of step_name → duration_ms.
        total_ms: Total pipeline duration in milliseconds.

    Returns:
        List of Bottleneck objects sorted by duration descending.
    """
    if not step_durations or total_ms == 0:
        return []

    avg_ms = sum(step_durations.values()) / len(step_durations)
    bottlenecks: list[Bottleneck] = []

    for step_name, duration_ms in step_durations.items():
        pct = duration_ms / total_ms * 100
        is_slow = duration_ms > avg_ms * _BOTTLENECK_MULTIPLIER
        is_dominant = pct > _HIGH_PCT

        if not (is_slow or is_dominant):
            continue

        if pct > _CRITICAL_PCT:
            severity = "critical"
            rec = (
                f"Step '{step_name}' consumes {pct:.0f}% of pipeline time — "
                "consider parallelization or aggressive caching"
            )
        elif pct > _HIGH_PCT:
            severity = "high"
            rec = (
                f"Step '{step_name}' is a major bottleneck — "
                "review LLM prompt size and data volume"
            )
        else:
            severity = "medium"
            rec = (
                f"Step '{step_name}' is {duration_ms / avg_ms:.1f}× slower than average — "
                "check input data size"
            )

        bottlenecks.append(Bottleneck(
            step_name=step_name,
            duration_ms=duration_ms,
            pct_of_total=round(pct, 1),
            severity=severity,
            recommendation=rec,
        ))

    bottlenecks.sort(key=lambda b: b.duration_ms, reverse=True)
    return bottlenecks
