"""Metrics collector for pipeline observability.

Tracks key performance indicators:
- Cache hit/miss rates per service
- LLM token usage (prompt + completion)
- Step durations
- Pipeline total time
- Data source coverage

Ref: ASO v3 Phase 9 — Observabilidade
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TCH003
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Singleton instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get or create the global MetricsCollector singleton."""
    global _metrics  # noqa: PLW0603
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def reset_metrics() -> None:
    """Reset metrics (for testing)."""
    global _metrics  # noqa: PLW0603
    _metrics = None


@dataclass
class CacheMetrics:
    """Cache performance metrics."""

    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.hits / self.total


@dataclass
class LLMMetrics:
    """LLM usage metrics."""

    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: int = 0
    total_duration_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def avg_duration_ms(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.total_duration_ms / self.requests


@dataclass
class StepMetrics:
    """Per-step execution metrics."""

    step_name: str
    duration_ms: int = 0
    tokens_used: int = 0
    data_sources: int = 0
    confidence: str = ""


@dataclass
class MetricsCollector:
    """Collects and exports pipeline metrics."""

    cache: dict[str, CacheMetrics] = field(default_factory=dict)
    llm: LLMMetrics = field(default_factory=LLMMetrics)
    steps: list[StepMetrics] = field(default_factory=list)
    pipeline_start_time: float | None = None
    pipeline_end_time: float | None = None
    region_name: str = ""
    model_used: str = ""

    def record_cache_hit(self, service: str) -> None:
        """Record a cache hit for a service."""
        if service not in self.cache:
            self.cache[service] = CacheMetrics()
        self.cache[service].hits += 1
        logger.debug("cache_hit", service=service)

    def record_cache_miss(self, service: str) -> None:
        """Record a cache miss for a service."""
        if service not in self.cache:
            self.cache[service] = CacheMetrics()
        self.cache[service].misses += 1
        logger.debug("cache_miss", service=service)

    def record_llm_request(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
    ) -> None:
        """Record an LLM request."""
        self.llm.requests += 1
        self.llm.prompt_tokens += prompt_tokens
        self.llm.completion_tokens += completion_tokens
        self.llm.total_duration_ms += duration_ms
        logger.debug(
            "llm_request",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
        )

    def record_llm_error(self) -> None:
        """Record an LLM request failure."""
        self.llm.errors += 1
        logger.warning("llm_error")

    def record_step(
        self,
        step_name: str,
        duration_ms: int,
        tokens_used: int = 0,
        data_sources: int = 0,
        confidence: str = "",
    ) -> None:
        """Record a completed analysis step."""
        self.steps.append(
            StepMetrics(
                step_name=step_name,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                data_sources=data_sources,
                confidence=confidence,
            )
        )
        logger.info(
            "step_completed",
            step=step_name,
            duration_ms=duration_ms,
            confidence=confidence,
        )

    def start_pipeline(self, region_name: str, model: str) -> None:
        """Mark pipeline start."""
        self.pipeline_start_time = time.time()
        self.region_name = region_name
        self.model_used = model
        logger.info("pipeline_started", region=region_name, model=model)

    def end_pipeline(self) -> None:
        """Mark pipeline end."""
        self.pipeline_end_time = time.time()
        duration = self.pipeline_duration_ms
        logger.info(
            "pipeline_completed",
            region=self.region_name,
            duration_ms=duration,
            total_tokens=self.llm.total_tokens,
            cache_hit_rate=self.overall_cache_hit_rate,
        )

    @property
    def pipeline_duration_ms(self) -> int:
        """Total pipeline duration in milliseconds."""
        if self.pipeline_start_time is None:
            return 0
        end = self.pipeline_end_time or time.time()
        return int((end - self.pipeline_start_time) * 1000)

    @property
    def overall_cache_hit_rate(self) -> float:
        """Overall cache hit rate across all services."""
        total_hits = sum(m.hits for m in self.cache.values())
        total_requests = sum(m.total for m in self.cache.values())
        if total_requests == 0:
            return 0.0
        return total_hits / total_requests

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as a dictionary."""
        return {
            "region_name": self.region_name,
            "model_used": self.model_used,
            "pipeline_duration_ms": self.pipeline_duration_ms,
            "cache": {
                service: {
                    "hits": m.hits,
                    "misses": m.misses,
                    "hit_rate": round(m.hit_rate, 3),
                }
                for service, m in self.cache.items()
            },
            "overall_cache_hit_rate": round(self.overall_cache_hit_rate, 3),
            "llm": {
                "requests": self.llm.requests,
                "prompt_tokens": self.llm.prompt_tokens,
                "completion_tokens": self.llm.completion_tokens,
                "total_tokens": self.llm.total_tokens,
                "errors": self.llm.errors,
                "avg_duration_ms": round(self.llm.avg_duration_ms, 1),
            },
            "steps": [
                {
                    "name": s.step_name,
                    "duration_ms": s.duration_ms,
                    "tokens_used": s.tokens_used,
                    "data_sources": s.data_sources,
                    "confidence": s.confidence,
                }
                for s in self.steps
            ],
        }

    def export_json(self, path: Path) -> None:
        """Export metrics to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        logger.info("metrics_exported", path=str(path))
