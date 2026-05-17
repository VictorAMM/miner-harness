"""ReportValidator -- Evaluator-Optimizer for ProspectionReport.

Validates reasoning trace, step quality, and report consistency.
Implements Prune-Freeze-Repair for low-quality steps.

Ref: ASO v3 Phase 6, RFC-002 Section 4.2
"""

from __future__ import annotations

import structlog

from miner_harness.core.types import (
    AnalysisStep,
    BoundingBox,
    Confidence,
    MineralTarget,
    ProspectionReport,
)

logger = structlog.get_logger(__name__)


class ValidationIssue:
    """Single validation issue found in a report."""

    __slots__ = ("severity", "step", "message", "field")

    def __init__(
        self,
        severity: str,
        message: str,
        step: AnalysisStep | None = None,
        field: str | None = None,
    ) -> None:
        self.severity = severity  # "error", "warning", "info"
        self.step = step
        self.message = message
        self.field = field

    def __repr__(self) -> str:
        step_str = f" [{self.step.value}]" if self.step else ""
        return f"ValidationIssue({self.severity}{step_str}: {self.message})"


class ValidationResult:
    """Aggregated validation result."""

    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []
        self.score: float = 1.0  # 0-1, starts perfect

    @property
    def is_valid(self) -> bool:
        """Report passes if no errors."""
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if issue.severity == "error":
            self.score = max(0.0, self.score - 0.2)
        elif issue.severity == "warning":
            self.score = max(0.0, self.score - 0.05)


class ReportValidator:
    """Evaluator-Optimizer for ProspectionReport.

    Validates:
    1. Step completeness (all expected steps present)
    2. Reasoning quality (findings not empty, confidence justified)
    3. Target validity (coordinates, commodities, rationale)
    4. Data quality consistency (score matches actual coverage)
    5. Temporal consistency (durations non-negative)

    Usage:
        validator = ReportValidator()
        result = validator.validate(report)
        if not result.is_valid:
            # Prune-Freeze-Repair
            repaired = validator.repair(report, result)
    """

    # Minimum findings per step to be considered substantive
    MIN_FINDINGS_PER_STEP = 1

    # Steps that must always be present in a full analysis
    REQUIRED_STEPS = set(AnalysisStep)

    def validate(self, report: ProspectionReport) -> ValidationResult:
        """Run all validations on a report."""
        result = ValidationResult()

        self._validate_step_completeness(report, result)
        self._validate_step_quality(report, result)
        self._validate_targets(report, result)
        self._validate_data_quality(report, result)
        self._validate_temporal(report, result)
        self._validate_metadata(report, result)

        logger.info(
            "report_validated",
            is_valid=result.is_valid,
            errors=result.error_count,
            warnings=result.warning_count,
            score=round(result.score, 2),
        )
        return result

    def repair(
        self,
        report: ProspectionReport,
        validation: ValidationResult,
    ) -> ProspectionReport:
        """Prune-Freeze-Repair: fix what can be fixed, flag what cannot.

        - Prune: remove targets with no rationale
        - Freeze: keep valid steps unchanged
        - Repair: add caveats for issues, fix quality score
        """
        repaired_targets = [
            t for t in report.targets if t.rationale and len(t.rationale.strip()) > 0
        ]

        # Add validation issues as caveats
        repair_caveats = list(report.caveats)
        for issue in validation.issues:
            if issue.severity == "error":
                caveat = f"[VALIDATION] {issue.message}"
                if caveat not in repair_caveats:
                    repair_caveats.append(caveat)

        # Recalculate quality score incorporating validation
        adjusted_quality = min(
            report.data_quality_score,
            validation.score,
        )

        repaired = report.model_copy(
            update={
                "targets": repaired_targets,
                "caveats": repair_caveats,
                "data_quality_score": adjusted_quality,
            }
        )

        logger.info(
            "report_repaired",
            targets_pruned=len(report.targets) - len(repaired_targets),
            caveats_added=len(repair_caveats) - len(report.caveats),
            quality_adjusted=round(adjusted_quality, 2),
        )
        return repaired

    # ------------------------------------------------------------------
    # Validation rules
    # ------------------------------------------------------------------

    def _validate_step_completeness(
        self, report: ProspectionReport, result: ValidationResult
    ) -> None:
        """Check all expected steps are present."""
        present_steps = {s.step for s in report.steps}
        missing = self.REQUIRED_STEPS - present_steps

        if missing:
            missing_names = ", ".join(s.value for s in missing)
            result.add(
                ValidationIssue(
                    severity="warning",
                    message=f"Missing steps: {missing_names}",
                    field="steps",
                )
            )

        if len(report.steps) == 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message="Report has no analysis steps",
                    field="steps",
                )
            )

    def _validate_step_quality(self, report: ProspectionReport, result: ValidationResult) -> None:
        """Validate each step's reasoning quality."""
        for step in report.steps:
            # Empty findings
            if len(step.findings) < self.MIN_FINDINGS_PER_STEP:
                result.add(
                    ValidationIssue(
                        severity="warning",
                        step=step.step,
                        message=(
                            f"Step has {len(step.findings)} findings"
                            f" (min: {self.MIN_FINDINGS_PER_STEP})"
                        ),
                        field="findings",
                    )
                )

            # Empty summary
            if not step.summary or len(step.summary.strip()) == 0:
                result.add(
                    ValidationIssue(
                        severity="error",
                        step=step.step,
                        message="Step has empty summary",
                        field="summary",
                    )
                )

            # INSUFFICIENT confidence with non-empty findings is contradictory
            if step.confidence == Confidence.INSUFFICIENT and len(step.findings) > 2:
                result.add(
                    ValidationIssue(
                        severity="warning",
                        step=step.step,
                        message="INSUFFICIENT confidence but has findings -- review confidence level",
                        field="confidence",
                    )
                )

            # HIGH confidence without data sources is suspicious
            if step.confidence == Confidence.HIGH and len(step.data_sources_used) == 0:
                result.add(
                    ValidationIssue(
                        severity="warning",
                        step=step.step,
                        message="HIGH confidence but no data sources cited",
                        field="confidence",
                    )
                )

    def _validate_targets(self, report: ProspectionReport, result: ValidationResult) -> None:
        """Validate mineral targets."""
        for i, target in enumerate(report.targets):
            self._validate_single_target(target, i, report.bbox, result)

    def _validate_single_target(
        self,
        target: MineralTarget,
        index: int,
        bbox: BoundingBox,
        result: ValidationResult,
    ) -> None:
        """Validate a single mineral target."""
        # Empty rationale
        if not target.rationale or len(target.rationale.strip()) == 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message=f"Target {index} ({target.name}) has no rationale",
                    field="targets",
                )
            )

        # No commodities
        if len(target.commodities) == 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message=f"Target {index} ({target.name}) has no commodities",
                    field="targets",
                )
            )

        # Check coordinates within bbox
        if not bbox.contains_point(target.longitude, target.latitude):
            result.add(
                ValidationIssue(
                    severity="warning",
                    message=f"Target {index} ({target.name}) is outside the analysis bbox",
                    field="targets",
                )
            )

        # Negative radius
        if target.radius_km <= 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message=f"Target {index} ({target.name}) has invalid radius: {target.radius_km}",
                    field="targets",
                )
            )

    def _validate_data_quality(self, report: ProspectionReport, result: ValidationResult) -> None:
        """Check data quality score consistency."""
        if report.data_quality_score < 0 or report.data_quality_score > 1:
            result.add(
                ValidationIssue(
                    severity="error",
                    message=f"data_quality_score out of range: {report.data_quality_score}",
                    field="data_quality_score",
                )
            )

        # High quality with many data gaps is suspicious
        total_gaps = sum(len(s.data_gaps) for s in report.steps)
        if report.data_quality_score > 0.8 and total_gaps > 5:
            result.add(
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"High quality score ({report.data_quality_score:.2f})"
                        f" but {total_gaps} data gaps"
                    ),
                    field="data_quality_score",
                )
            )

    def _validate_temporal(self, report: ProspectionReport, result: ValidationResult) -> None:
        """Validate temporal consistency."""
        if report.total_duration_ms < 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message="Negative total_duration_ms",
                    field="total_duration_ms",
                )
            )

        for step in report.steps:
            if step.duration_ms < 0:
                result.add(
                    ValidationIssue(
                        severity="error",
                        step=step.step,
                        message="Negative step duration_ms",
                        field="duration_ms",
                    )
                )

        # Total should be >= sum of steps
        step_total = sum(s.duration_ms for s in report.steps)
        if report.total_duration_ms < step_total:
            result.add(
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"total_duration_ms ({report.total_duration_ms})"
                        f" < sum of steps ({step_total})"
                    ),
                    field="total_duration_ms",
                )
            )

    def _validate_metadata(self, report: ProspectionReport, result: ValidationResult) -> None:
        """Validate report metadata."""
        if not report.region_name or len(report.region_name.strip()) == 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message="Empty region_name",
                    field="region_name",
                )
            )

        if not report.model_used or len(report.model_used.strip()) == 0:
            result.add(
                ValidationIssue(
                    severity="error",
                    message="Empty model_used",
                    field="model_used",
                )
            )
