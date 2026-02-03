"""Unit tests for diff engine (Phase 6).

Tests for pure set-math comparison functions.
"""

import pytest
from pathlib import Path

from codebatch.ui.diff import (
    DiffResult,
    DiagnosticDelta,
    diff_sets,
    normalize_output,
    make_output_key,
    is_regression,
    is_improvement,
    severity_value,
)


class TestNormalizeOutput:
    """Tests for normalize_output function."""

    def test_removes_timestamp(self):
        """Should remove timestamp field."""
        record = {"path": "test.py", "ts": "2024-01-01T00:00:00"}
        normalized = normalize_output(record)

        assert "ts" not in normalized
        assert "path" in normalized

    def test_removes_run_id(self):
        """Should remove run_id field."""
        record = {"path": "test.py", "run_id": "abc123"}
        normalized = normalize_output(record)

        assert "run_id" not in normalized

    def test_removes_shard_id(self):
        """Should remove shard_id field."""
        record = {"path": "test.py", "shard_id": "ab"}
        normalized = normalize_output(record)

        assert "shard_id" not in normalized

    def test_preserves_other_fields(self):
        """Should preserve non-ephemeral fields."""
        record = {
            "kind": "diagnostic",
            "path": "test.py",
            "code": "E001",
            "severity": "error",
        }
        normalized = normalize_output(record)

        assert normalized == record

    def test_custom_ignore_fields(self):
        """Should respect custom ignore fields."""
        record = {"path": "test.py", "custom": "value"}
        normalized = normalize_output(record, ignore_fields={"custom"})

        assert "custom" not in normalized


class TestMakeOutputKey:
    """Tests for make_output_key function."""

    def test_diagnostic_key(self):
        """Should create key for diagnostic."""
        record = {
            "kind": "diagnostic",
            "path": "test.py",
            "line": 10,
            "column": 5,
            "code": "E001",
        }
        key = make_output_key(record)

        assert key == ("diagnostic", "test.py", 10, 5, "E001")

    def test_metric_key(self):
        """Should create key for metric."""
        record = {
            "kind": "metric",
            "path": "test.py",
            "name": "complexity",
        }
        key = make_output_key(record)

        assert key == ("metric", "test.py", "complexity")

    def test_symbol_key(self):
        """Should create key for symbol."""
        record = {
            "kind": "symbol",
            "path": "test.py",
            "name": "MyClass",
            "line": 1,
        }
        key = make_output_key(record)

        assert key == ("symbol", "test.py", "MyClass", 1)

    def test_generic_key(self):
        """Should create key for unknown kind."""
        record = {
            "kind": "unknown",
            "path": "test.py",
        }
        key = make_output_key(record)

        assert key == ("unknown", "test.py")


class TestDiffSets:
    """Tests for diff_sets function."""

    def test_identical_sets(self):
        """Identical sets should have no differences."""
        set_a = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "code": "E001"},
        ]
        set_b = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "code": "E001"},
        ]

        result = diff_sets(set_a, set_b)

        assert result.added == []
        assert result.removed == []
        assert result.changed == []

    def test_added_records(self):
        """Should detect added records."""
        set_a = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "code": "E001"},
        ]
        set_b = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "code": "E001"},
            {"kind": "diagnostic", "path": "test.py", "line": 2, "code": "E002"},
        ]

        result = diff_sets(set_a, set_b)

        assert len(result.added) == 1
        assert result.added[0]["code"] == "E002"
        assert result.removed == []

    def test_removed_records(self):
        """Should detect removed records."""
        set_a = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "code": "E001"},
            {"kind": "diagnostic", "path": "test.py", "line": 2, "code": "E002"},
        ]
        set_b = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "code": "E001"},
        ]

        result = diff_sets(set_a, set_b)

        assert result.added == []
        assert len(result.removed) == 1
        assert result.removed[0]["code"] == "E002"

    def test_changed_records(self):
        """Should detect changed records (same key, different values)."""
        set_a = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "column": 0, "code": "E001", "severity": "warning"},
        ]
        set_b = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "column": 0, "code": "E001", "severity": "error"},
        ]

        result = diff_sets(set_a, set_b)

        assert result.added == []
        assert result.removed == []
        assert len(result.changed) == 1
        old, new = result.changed[0]
        assert old["severity"] == "warning"
        assert new["severity"] == "error"

    def test_ignores_timestamps(self):
        """Should ignore timestamps when comparing."""
        set_a = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "column": 0, "code": "E001", "ts": "2024-01-01"},
        ]
        set_b = [
            {"kind": "diagnostic", "path": "test.py", "line": 1, "column": 0, "code": "E001", "ts": "2024-01-02"},
        ]

        result = diff_sets(set_a, set_b)

        # Should be no changes (ts is ignored)
        assert result.added == []
        assert result.removed == []
        assert result.changed == []

    def test_deterministic_ordering(self):
        """Results should be sorted deterministically."""
        set_a = []
        set_b = [
            {"kind": "diagnostic", "path": "z.py", "line": 1, "column": 0, "code": "E003"},
            {"kind": "diagnostic", "path": "a.py", "line": 1, "column": 0, "code": "E001"},
            {"kind": "diagnostic", "path": "m.py", "line": 1, "column": 0, "code": "E002"},
        ]

        result = diff_sets(set_a, set_b)

        # Added should be sorted
        paths = [r["path"] for r in result.added]
        assert paths == sorted(paths)

    def test_empty_sets(self):
        """Should handle empty sets."""
        result = diff_sets([], [])

        assert result.added == []
        assert result.removed == []
        assert result.changed == []


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_total_changes(self):
        """Should compute total changes."""
        result = DiffResult()
        result.added = [{"a": 1}, {"b": 2}]
        result.removed = [{"c": 3}]
        result.changed = [({"d": 4}, {"d": 5})]

        assert result.total_changes == 4

    def test_to_dict(self):
        """Should convert to dictionary."""
        result = DiffResult()
        result.added = [{"kind": "diagnostic", "code": "E001"}]

        d = result.to_dict()

        assert "added" in d
        assert "removed" in d
        assert "changed" in d
        assert "summary" in d
        assert d["summary"]["added_count"] == 1


class TestSeverityFunctions:
    """Tests for severity comparison functions."""

    def test_severity_value_order(self):
        """Severity values should be ordered correctly."""
        assert severity_value("error") < severity_value("warning")
        assert severity_value("warning") < severity_value("info")
        assert severity_value("info") < severity_value("hint")

    def test_unknown_severity(self):
        """Unknown severity should have high value."""
        assert severity_value("unknown") > severity_value("hint")

    def test_is_regression_new_diagnostic(self):
        """New diagnostic is a regression."""
        assert is_regression(None, {"severity": "warning"}) is True

    def test_is_regression_severity_increase(self):
        """Severity increase is a regression."""
        old = {"severity": "warning"}
        new = {"severity": "error"}
        assert is_regression(old, new) is True

    def test_is_regression_severity_decrease(self):
        """Severity decrease is not a regression."""
        old = {"severity": "error"}
        new = {"severity": "warning"}
        assert is_regression(old, new) is False

    def test_is_improvement_removed(self):
        """Removed diagnostic is an improvement."""
        assert is_improvement({"severity": "error"}, None) is True

    def test_is_improvement_severity_decrease(self):
        """Severity decrease is an improvement."""
        old = {"severity": "error"}
        new = {"severity": "warning"}
        assert is_improvement(old, new) is True

    def test_is_improvement_severity_increase(self):
        """Severity increase is not an improvement."""
        old = {"severity": "warning"}
        new = {"severity": "error"}
        assert is_improvement(old, new) is False


class TestDiagnosticDelta:
    """Tests for DiagnosticDelta dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        delta = DiagnosticDelta()
        delta.regressions = [{"code": "E001"}]
        delta.improvements = [{"code": "E002"}]

        d = delta.to_dict()

        assert "regressions" in d
        assert "improvements" in d
        assert "unchanged" in d
        assert "summary" in d
        assert d["summary"]["regressions_count"] == 1
        assert d["summary"]["improvements_count"] == 1
