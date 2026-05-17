"""Testes do ReportValidator.

Ref: ASO v3 Phase 6, Evaluator-Optimizer
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
    StepResult,
)
from miner_harness.orchestrator.report_validator import ReportValidator


def _make_step(
    step: AnalysisStep = AnalysisStep.TECTONIC_HISTORY,
    summary: str = "Test summary",
    findings: list[str] | None = None,
    confidence: Confidence = Confidence.MEDIUM,
    data_sources: list[str] | None = None,
    data_gaps: list[str] | None = None,
    duration_ms: int = 100,
) -> StepResult:
    return StepResult(
        step=step,
        agent="test_agent",
        summary=summary,
        findings=findings if findings is not None else ["finding1"],
        confidence=confidence,
        data_sources_used=data_sources if data_sources is not None else ["source1"],
        data_gaps=data_gaps if data_gaps is not None else [],
        raw_reasoning="test reasoning",
        duration_ms=duration_ms,
    )


def _make_target(
    name: str = "Target A",
    lon: float = -50.5,
    lat: float = -6.0,
    commodities: list[str] | None = None,
    rationale: str = "Strong Cu anomaly",
    radius: float = 5.0,
    priority: int = 1,
) -> MineralTarget:
    return MineralTarget(
        name=name,
        longitude=lon,
        latitude=lat,
        radius_km=radius,
        commodities=commodities or ["Cu", "Au"],
        mineral_system="IOCG",
        confidence=Confidence.MEDIUM,
        priority=priority,
        rationale=rationale,
        recommended_followup=["soil sampling"],
    )


def _make_report(
    steps: list[StepResult] | None = None,
    targets: list[MineralTarget] | None = None,
    caveats: list[str] | None = None,
    quality: float = 0.75,
    duration: int = 500,
) -> ProspectionReport:
    bbox = BoundingBox(lon_min=-51.5, lat_min=-7.0, lon_max=-49.5, lat_max=-5.0)
    if steps is None:
        steps = [_make_step(s) for s in AnalysisStep]
    return ProspectionReport(
        region_name="Test Region",
        bbox=bbox,
        analysis_date=datetime.now(tz=timezone.utc),  # noqa: UP017
        steps=steps,
        targets=targets or [],
        integrated_summary="Test integrated summary",
        caveats=caveats or [],
        data_quality_score=quality,
        total_duration_ms=duration,
        model_used="qwen3:8b",
    )


@pytest.fixture
def validator() -> ReportValidator:
    return ReportValidator()


class TestReportValidatorValid:
    """Tests with valid reports."""

    def test_valid_report_passes(self, validator: ReportValidator) -> None:
        report = _make_report()
        result = validator.validate(report)
        assert result.is_valid
        assert result.error_count == 0

    def test_valid_report_high_score(self, validator: ReportValidator) -> None:
        report = _make_report()
        result = validator.validate(report)
        assert result.score > 0.8


class TestReportValidatorSteps:
    """Tests for step validation."""

    def test_missing_steps_warns(self, validator: ReportValidator) -> None:
        steps = [_make_step(AnalysisStep.TECTONIC_HISTORY)]
        report = _make_report(steps=steps)
        result = validator.validate(report)
        assert result.warning_count > 0
        assert any("Missing steps" in i.message for i in result.issues)

    def test_empty_steps_is_error(self, validator: ReportValidator) -> None:
        report = _make_report(steps=[])
        result = validator.validate(report)
        assert not result.is_valid
        assert any("no analysis steps" in i.message for i in result.issues)

    def test_empty_summary_is_error(self, validator: ReportValidator) -> None:
        steps = [_make_step(summary="")]
        report = _make_report(steps=steps)
        result = validator.validate(report)
        assert not result.is_valid
        assert any("empty summary" in i.message for i in result.issues)

    def test_no_findings_warns(self, validator: ReportValidator) -> None:
        steps = [_make_step(findings=[])]
        report = _make_report(steps=steps)
        result = validator.validate(report)
        assert result.warning_count > 0

    def test_high_confidence_no_sources_warns(self, validator: ReportValidator) -> None:
        steps = [_make_step(confidence=Confidence.HIGH, data_sources=[])]
        report = _make_report(steps=steps)
        result = validator.validate(report)
        assert any("no data sources cited" in i.message for i in result.issues)

    def test_insufficient_with_findings_warns(self, validator: ReportValidator) -> None:
        steps = [
            _make_step(
                confidence=Confidence.INSUFFICIENT,
                findings=["f1", "f2", "f3"],
            )
        ]
        report = _make_report(steps=steps)
        result = validator.validate(report)
        assert any("INSUFFICIENT" in i.message for i in result.issues)


class TestReportValidatorTargets:
    """Tests for target validation."""

    def test_target_no_rationale_is_error(self, validator: ReportValidator) -> None:
        targets = [_make_target(rationale="")]
        report = _make_report(targets=targets)
        result = validator.validate(report)
        assert not result.is_valid
        assert any("no rationale" in i.message for i in result.issues)

    def test_target_no_commodities_is_error(self, validator: ReportValidator) -> None:
        targets = [_make_target(commodities=["Cu"])]
        # Manually clear commodities after creation to bypass Pydantic
        targets[0].commodities = []
        report = _make_report(targets=targets)
        result = validator.validate(report)
        assert not result.is_valid
        assert any("no commodities" in i.message for i in result.issues)

    def test_target_outside_bbox_warns(self, validator: ReportValidator) -> None:
        targets = [_make_target(lon=-40.0, lat=-20.0)]  # Way outside
        report = _make_report(targets=targets)
        result = validator.validate(report)
        assert any("outside" in i.message for i in result.issues)

    def test_target_negative_radius_is_error(self, validator: ReportValidator) -> None:
        targets = [_make_target(radius=-1.0)]
        report = _make_report(targets=targets)
        result = validator.validate(report)
        assert not result.is_valid
        assert any("invalid radius" in i.message for i in result.issues)


class TestReportValidatorTemporal:
    """Tests for temporal validation."""

    def test_negative_duration_is_error(self, validator: ReportValidator) -> None:
        report = _make_report(duration=-100)
        result = validator.validate(report)
        assert not result.is_valid
        assert any("Negative" in i.message for i in result.issues)

    def test_step_duration_exceeds_total_warns(self, validator: ReportValidator) -> None:
        steps = [_make_step(duration_ms=1000)]
        report = _make_report(steps=steps, duration=500)
        result = validator.validate(report)
        assert any("sum of steps" in i.message for i in result.issues)


class TestReportValidatorRepair:
    """Tests for Prune-Freeze-Repair."""

    def test_repair_removes_empty_rationale_targets(self, validator: ReportValidator) -> None:
        targets = [
            _make_target(name="Good", rationale="Strong anomaly"),
            _make_target(name="Bad", rationale=""),
        ]
        report = _make_report(targets=targets)
        result = validator.validate(report)
        repaired = validator.repair(report, result)
        assert len(repaired.targets) == 1
        assert repaired.targets[0].name == "Good"

    def test_repair_adds_caveats(self, validator: ReportValidator) -> None:
        report = _make_report(steps=[])  # Will produce error
        result = validator.validate(report)
        repaired = validator.repair(report, result)
        assert any("[VALIDATION]" in c for c in repaired.caveats)

    def test_repair_adjusts_quality(self, validator: ReportValidator) -> None:
        report = _make_report(steps=[], quality=0.9)
        result = validator.validate(report)
        repaired = validator.repair(report, result)
        assert repaired.data_quality_score < report.data_quality_score
