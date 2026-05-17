"""Feedback loop — orchestrates the self-improvement cycle.

Integrates profiling, auto-tuning, and RCA learning into a single
feedback cycle that evolves configuration over time.

Ref: ASO v3 Phase 11 — Self-Improvement
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from miner_harness.self_improvement.profiler import PipelineProfile, profile_pipeline
from miner_harness.self_improvement.rca_learner import (
    build_classification_hints,
    extract_patterns,
    load_rca_history,
)
from miner_harness.self_improvement.tuner import (
    TuningReport,
    apply_recommendations,
    generate_tuning_report,
)

if TYPE_CHECKING:
    from miner_harness.core.config import MinerHarnessConfig
    from miner_harness.observability.metrics import MetricsCollector

logger = structlog.get_logger(__name__)


@dataclass
class FeedbackSummary:
    """Result of one self-improvement feedback cycle."""

    profile: PipelineProfile
    tuning_report: TuningReport
    rca_patterns_found: int
    classification_hints: dict[str, list[str]] = field(default_factory=dict)
    config_updated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "tuning_report": self.tuning_report.to_dict(),
            "rca_patterns_found": self.rca_patterns_found,
            "classification_hints": self.classification_hints,
            "config_updated": self.config_updated,
        }


class FeedbackLoop:
    """Orchestrates the self-improvement feedback cycle.

    Each call to ``run()`` performs:
      1. Profile the pipeline run (bottleneck detection).
      2. Generate tuning recommendations.
      3. Apply recommendations and persist the updated config.
      4. Load RCA history and extract classification hints.

    Usage::

        loop = FeedbackLoop(config)
        summary = loop.run(metrics)
        new_config = loop.tuned_config
    """

    def __init__(
        self,
        config: MinerHarnessConfig,
        rca_dir: Path | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._rca_dir = rca_dir or Path("docs/rca")
        self._output_dir = output_dir or (config.storage.miner_home / "self_improvement")
        self._tuned_config: MinerHarnessConfig | None = None

    @property
    def tuned_config(self) -> MinerHarnessConfig:
        """Most recently tuned config, or the original if no changes were made."""
        return self._tuned_config or self._config

    def run(self, metrics: MetricsCollector) -> FeedbackSummary:
        """Execute one full self-improvement cycle.

        Args:
            metrics: MetricsCollector populated by a completed pipeline run.

        Returns:
            FeedbackSummary describing what was profiled, tuned, and learned.
        """
        # 1. Profile
        profile = profile_pipeline(metrics)

        # 2. Tune
        tuning_report = generate_tuning_report(profile, self._config)

        # 3. Apply and persist
        config_updated = False
        if tuning_report.has_changes:
            self._tuned_config = apply_recommendations(self._config, tuning_report.recommendations)
            config_updated = True
            self._persist_tuned_config()

        # 4. Learn from RCA history
        history = load_rca_history(self._rca_dir)
        patterns = extract_patterns(history)
        hints = build_classification_hints(patterns)

        summary = FeedbackSummary(
            profile=profile,
            tuning_report=tuning_report,
            rca_patterns_found=len(patterns),
            classification_hints=hints,
            config_updated=config_updated,
        )

        logger.info(
            "feedback_cycle_complete",
            region=profile.region_name,
            recommendations=len(tuning_report.recommendations),
            rca_patterns=len(patterns),
            config_updated=config_updated,
        )

        return summary

    def _persist_tuned_config(self) -> None:
        """Write the tuned config to disk as JSON."""
        if self._tuned_config is None:
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / "tuned_config.json"
        path.write_text(
            json.dumps(
                self._tuned_config.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info("tuned_config_persisted", path=str(path))
