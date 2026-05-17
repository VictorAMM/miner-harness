"""Self-improvement subsystem — profiling, auto-tuning, and RCA learning.

Ref: ASO v3 Phase 11
"""

from miner_harness.self_improvement.feedback_loop import FeedbackLoop, FeedbackSummary
from miner_harness.self_improvement.profiler import (
    Bottleneck,
    PipelineProfile,
    identify_bottlenecks,
    profile_pipeline,
)
from miner_harness.self_improvement.rca_learner import (
    RCAHistory,
    RCAPattern,
    build_classification_hints,
    extract_patterns,
    load_rca_history,
)
from miner_harness.self_improvement.tuner import (
    TunerRecommendation,
    TuningReport,
    apply_recommendations,
    generate_tuning_report,
)

__all__ = [
    "Bottleneck",
    "FeedbackLoop",
    "FeedbackSummary",
    "PipelineProfile",
    "RCAHistory",
    "RCAPattern",
    "TunerRecommendation",
    "TuningReport",
    "apply_recommendations",
    "build_classification_hints",
    "extract_patterns",
    "generate_tuning_report",
    "identify_bottlenecks",
    "load_rca_history",
    "profile_pipeline",
]
