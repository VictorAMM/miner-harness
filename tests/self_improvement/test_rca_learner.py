"""Tests for self_improvement.rca_learner module."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TCH003

from miner_harness.self_improvement.rca_learner import (
    RCAHistory,
    RCAPattern,
    build_classification_hints,
    extract_patterns,
    load_rca_history,
)


def _write_rca(rca_dir: Path, name: str, category: str, error_type: str, message: str = "") -> None:
    data = {
        "id": name,
        "classified_error": {
            "category": category,
            "error_type": error_type,
            "message": message,
        },
    }
    (rca_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


class TestRCAHistory:
    def test_count(self) -> None:
        h = RCAHistory(reports=[{"a": 1}, {"b": 2}])
        assert h.count == 2

    def test_empty(self) -> None:
        h = RCAHistory()
        assert h.count == 0


class TestRCAPattern:
    def test_to_dict(self) -> None:
        p = RCAPattern(category="NETWORK", error_type="ConnectError", count=3)
        d = p.to_dict()
        assert d["category"] == "NETWORK"
        assert d["count"] == 3
        assert "example_messages" in d

    def test_to_dict_truncates_messages(self) -> None:
        p = RCAPattern(
            category="LLM",
            error_type="Timeout",
            count=5,
            example_messages=["m1", "m2", "m3", "m4", "m5"],
        )
        d = p.to_dict()
        assert len(d["example_messages"]) <= 3  # noqa: PLR2004


class TestLoadRcaHistory:
    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        history = load_rca_history(tmp_path / "nonexistent")
        assert history.count == 0

    def test_loads_valid_files(self, tmp_path: Path) -> None:
        _write_rca(tmp_path, "rca-001", "NETWORK", "ConnectError", "refused")
        _write_rca(tmp_path, "rca-002", "LLM", "Timeout", "timed out")
        history = load_rca_history(tmp_path)
        assert history.count == 2  # noqa: PLR2004

    def test_skips_malformed_json(self, tmp_path: Path) -> None:
        (tmp_path / "rca-bad.json").write_text("{broken", encoding="utf-8")
        _write_rca(tmp_path, "rca-good", "DATA", "ValueError")
        history = load_rca_history(tmp_path)
        assert history.count == 1

    def test_only_loads_rca_prefix(self, tmp_path: Path) -> None:
        _write_rca(tmp_path, "rca-001", "NETWORK", "X")
        (tmp_path / "other.json").write_text('{"a":1}', encoding="utf-8")
        history = load_rca_history(tmp_path)
        assert history.count == 1


class TestExtractPatterns:
    def test_empty_history(self) -> None:
        patterns = extract_patterns(RCAHistory())
        assert patterns == []

    def test_single_report(self) -> None:
        history = RCAHistory(
            reports=[
                {
                    "classified_error": {
                        "category": "NETWORK",
                        "error_type": "ConnectError",
                        "message": "refused",
                    }
                }
            ]
        )
        patterns = extract_patterns(history)
        assert len(patterns) == 1
        assert patterns[0].category == "NETWORK"

    def test_deduplicates_messages(self) -> None:
        reports = [
            {"classified_error": {"category": "LLM", "error_type": "Timeout", "message": "same"}},
            {"classified_error": {"category": "LLM", "error_type": "Timeout", "message": "same"}},
        ]
        history = RCAHistory(reports=reports)
        patterns = extract_patterns(history)
        assert len(patterns) == 1
        assert len(patterns[0].example_messages) == 1

    def test_sorted_by_count(self) -> None:
        reports = [
            {"classified_error": {"category": "NETWORK", "error_type": "X", "message": "a"}},
            {"classified_error": {"category": "NETWORK", "error_type": "X", "message": "b"}},
            {"classified_error": {"category": "LLM", "error_type": "Y", "message": "c"}},
        ]
        history = RCAHistory(reports=reports)
        patterns = extract_patterns(history)
        counts = [p.count for p in patterns]
        assert counts == sorted(counts, reverse=True)


class TestBuildClassificationHints:
    def test_empty_patterns(self) -> None:
        hints = build_classification_hints([])
        assert hints == {}

    def test_groups_by_category(self) -> None:
        patterns = [
            RCAPattern("NETWORK", "ConnectError", 2),
            RCAPattern("NETWORK", "TimeoutError", 1),
            RCAPattern("LLM", "Timeout", 1),
        ]
        hints = build_classification_hints(patterns)
        assert "NETWORK" in hints
        assert "ConnectError" in hints["NETWORK"]
        assert "TimeoutError" in hints["NETWORK"]
        assert "LLM" in hints

    def test_no_duplicate_error_types(self) -> None:
        patterns = [
            RCAPattern("NETWORK", "ConnectError", 3),
            RCAPattern("NETWORK", "ConnectError", 1),
        ]
        hints = build_classification_hints(patterns)
        assert hints["NETWORK"].count("ConnectError") == 1
