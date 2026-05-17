"""RCA (Root Cause Analysis) module — autonomous error handling.

Provides error classification, automatic diagnostics, RCA document
generation, and self-healing strategies.

Ref: ASO v3 Phase 10
"""

from miner_harness.rca.classifier import (
    ClassifiedError,
    ErrorCategory,
    ErrorSeverity,
    classify_error,
)
from miner_harness.rca.diagnostics import DiagnosticSnapshot, collect_diagnostics
from miner_harness.rca.reporter import RCAReport, generate_rca_report, save_rca_report
from miner_harness.rca.retry import RetryPolicy, RetryResult, retry_with_backoff

__all__ = [
    "ClassifiedError",
    "DiagnosticSnapshot",
    "ErrorCategory",
    "ErrorSeverity",
    "RCAReport",
    "RetryPolicy",
    "RetryResult",
    "classify_error",
    "collect_diagnostics",
    "generate_rca_report",
    "retry_with_backoff",
    "save_rca_report",
]
