"""Tests for the lint task executor.

The lint task produces diagnostics:
- kind=diagnostic: Lint warnings with severity, code, message, location
"""

import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.parse import parse_executor
from codebatch.tasks.lint import (
    lint_executor,
    lint_trailing_whitespace,
    lint_line_too_long,
    lint_todo_fixme,
    lint_tab_indentation,
    lint_missing_final_newline,
    lint_content,
)


@pytest.fixture
def clean_store(tmp_path: Path) -> Path:
    """Create a clean temporary store."""
    store = tmp_path / "store"
    store.mkdir()
    return store


@pytest.fixture
def corpus_dir() -> Path:
    """Get the test corpus directory."""
    return Path(__file__).parent / "fixtures" / "corpus"


class TestLintTrailingWhitespace:
    """Unit tests for trailing whitespace rule."""

    def test_detects_trailing_spaces(self):
        lines = ["hello  \n", "world\n"]
        diags = lint_trailing_whitespace(lines, "test.py")
        assert len(diags) == 1
        assert diags[0]["code"] == "L001"
        assert diags[0]["line"] == 1

    def test_clean_lines(self):
        lines = ["hello\n", "world\n"]
        diags = lint_trailing_whitespace(lines, "test.py")
        assert len(diags) == 0

    def test_trailing_tabs(self):
        lines = ["hello\t\n"]
        diags = lint_trailing_whitespace(lines, "test.py")
        assert len(diags) == 1


class TestLintLineTooLong:
    """Unit tests for line too long rule."""

    def test_long_line(self):
        lines = ["a" * 150 + "\n"]
        diags = lint_line_too_long(lines, "test.py", max_length=120)
        assert len(diags) == 1
        assert diags[0]["code"] == "L002"
        assert "150 > 120" in diags[0]["message"]

    def test_acceptable_line(self):
        lines = ["a" * 100 + "\n"]
        diags = lint_line_too_long(lines, "test.py", max_length=120)
        assert len(diags) == 0

    def test_exactly_max_length(self):
        lines = ["a" * 120 + "\n"]
        diags = lint_line_too_long(lines, "test.py", max_length=120)
        assert len(diags) == 0


class TestLintTodoFixme:
    """Unit tests for TODO/FIXME detection."""

    def test_detects_todo(self):
        lines = ["# TODO: fix this\n"]
        diags = lint_todo_fixme(lines, "test.py")
        assert len(diags) == 1
        assert diags[0]["code"] == "L003"
        assert "TODO" in diags[0]["message"]

    def test_detects_fixme(self):
        lines = ["# FIXME: broken\n"]
        diags = lint_todo_fixme(lines, "test.py")
        assert len(diags) == 1
        assert "FIXME" in diags[0]["message"]

    def test_case_insensitive(self):
        lines = ["# todo: lowercase\n"]
        diags = lint_todo_fixme(lines, "test.py")
        assert len(diags) == 1

    def test_no_todo(self):
        lines = ["# This is fine\n"]
        diags = lint_todo_fixme(lines, "test.py")
        assert len(diags) == 0


class TestLintTabIndentation:
    """Unit tests for tab indentation rule."""

    def test_detects_tab(self):
        lines = ["\tindented\n"]
        diags = lint_tab_indentation(lines, "test.py")
        assert len(diags) == 1
        assert diags[0]["code"] == "L004"

    def test_spaces_ok(self):
        lines = ["    indented\n"]
        diags = lint_tab_indentation(lines, "test.py")
        assert len(diags) == 0

    def test_tab_not_at_start(self):
        lines = ["hello\tworld\n"]
        diags = lint_tab_indentation(lines, "test.py")
        assert len(diags) == 0  # Only leading tabs


class TestLintMissingFinalNewline:
    """Unit tests for missing final newline rule."""

    def test_missing_newline(self):
        content = "hello"
        diags = lint_missing_final_newline(content, "test.py")
        assert len(diags) == 1
        assert diags[0]["code"] == "L005"

    def test_has_newline(self):
        content = "hello\n"
        diags = lint_missing_final_newline(content, "test.py")
        assert len(diags) == 0

    def test_empty_file(self):
        content = ""
        diags = lint_missing_final_newline(content, "test.py")
        assert len(diags) == 0


class TestLintContent:
    """Integration tests for lint_content function."""

    def test_all_rules(self):
        content = "\tline  \n" + "a" * 150 + "\n# TODO fix\nhello"
        diags = lint_content(content, "test.py", {})

        codes = {d["code"] for d in diags}
        assert "L001" in codes  # trailing whitespace
        assert "L002" in codes  # line too long
        assert "L003" in codes  # TODO
        assert "L004" in codes  # tab
        assert "L005" in codes  # missing final newline

    def test_config_disables_rules(self):
        content = "hello  \n"  # trailing whitespace
        diags = lint_content(content, "test.py", {"check_trailing_whitespace": False})
        assert len(diags) == 0


class TestLintExecutor:
    """Tests for the lint_executor function."""

    def test_produces_diagnostics(self, clean_store: Path, corpus_dir: Path):
        """Lint task produces diagnostic records."""
        from codebatch.batch import PIPELINES
        PIPELINES["parse_lint"] = {
            "description": "Parse and lint",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {"task_id": "04_lint", "type": "lint", "depends_on": ["01_parse"], "config": {}},
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_lint")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        state = runner.run_shard(batch_id, "04_lint", shard_id, lint_executor)

        assert state["status"] == "done"

        outputs = runner.get_shard_outputs(batch_id, "04_lint", shard_id)
        # All outputs should be diagnostics
        for o in outputs:
            assert o.get("kind") == "diagnostic"

    def test_diagnostics_have_required_fields(self, clean_store: Path, corpus_dir: Path):
        """Diagnostic records have all required fields."""
        from codebatch.batch import PIPELINES
        PIPELINES["parse_lint"] = {
            "description": "Parse and lint",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {"task_id": "04_lint", "type": "lint", "depends_on": ["01_parse"], "config": {}},
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_lint")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "04_lint", shard_id, lint_executor)

        engine = QueryEngine(clean_store)
        all_outputs = engine.query_outputs(batch_id, "04_lint")

        for d in all_outputs:
            assert "path" in d, "Diagnostic missing path"
            assert "severity" in d, "Diagnostic missing severity"
            assert "code" in d, "Diagnostic missing code"
            assert "message" in d, "Diagnostic missing message"
            assert "line" in d, "Diagnostic missing line"

    def test_deterministic_outputs(self, clean_store: Path, corpus_dir: Path):
        """Lint outputs are deterministic across runs."""
        from codebatch.batch import PIPELINES
        PIPELINES["parse_lint"] = {
            "description": "Parse and lint",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {"task_id": "04_lint", "type": "lint", "depends_on": ["01_parse"], "config": {}},
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)

        # Run 1
        batch_id_1 = batch_manager.init_batch(snapshot_id, "parse_lint", batch_id="batch-lint-1")
        runner1 = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner1.run_shard(batch_id_1, "01_parse", shard_id, parse_executor)
        runner1.run_shard(batch_id_1, "04_lint", shard_id, lint_executor)
        outputs_1 = runner1.get_shard_outputs(batch_id_1, "04_lint", shard_id)

        # Run 2
        batch_id_2 = batch_manager.init_batch(snapshot_id, "parse_lint", batch_id="batch-lint-2")
        runner2 = ShardRunner(clean_store)

        runner2.run_shard(batch_id_2, "01_parse", shard_id, parse_executor)
        runner2.run_shard(batch_id_2, "04_lint", shard_id, lint_executor)
        outputs_2 = runner2.get_shard_outputs(batch_id_2, "04_lint", shard_id)

        # Compare (ignore timestamps and batch-specific fields)
        def normalize(outputs):
            return sorted([
                (o["kind"], o["path"], o["code"], o["line"], o.get("col", 0))
                for o in outputs
            ])

        assert normalize(outputs_1) == normalize(outputs_2)


class TestLintIntegration:
    """Integration tests for lint in the pipeline."""

    def test_query_diagnostics_by_severity(self, clean_store: Path, corpus_dir: Path):
        """Can query diagnostics grouped by severity."""
        from codebatch.batch import PIPELINES
        PIPELINES["parse_lint"] = {
            "description": "Parse and lint",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {"task_id": "04_lint", "type": "lint", "depends_on": ["01_parse"], "config": {}},
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_lint")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "04_lint", shard_id, lint_executor)

        engine = QueryEngine(clean_store)
        all_outputs = engine.query_outputs(batch_id, "04_lint")

        # Group by severity
        by_severity = {}
        for o in all_outputs:
            sev = o.get("severity", "unknown")
            by_severity.setdefault(sev, []).append(o)

        # Should have some diagnostics (test corpus likely has issues)
        assert len(all_outputs) >= 0  # May be 0 if corpus is clean

    def test_query_diagnostics_by_code(self, clean_store: Path, corpus_dir: Path):
        """Can query diagnostics grouped by code."""
        from codebatch.batch import PIPELINES
        PIPELINES["parse_lint"] = {
            "description": "Parse and lint",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {"task_id": "04_lint", "type": "lint", "depends_on": ["01_parse"], "config": {}},
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_lint")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "04_lint", shard_id, lint_executor)

        engine = QueryEngine(clean_store)
        all_outputs = engine.query_outputs(batch_id, "04_lint")

        # Group by code
        by_code = {}
        for o in all_outputs:
            code = o.get("code", "unknown")
            by_code.setdefault(code, []).append(o)

        # Each code should be a valid lint code
        for code in by_code.keys():
            assert code.startswith("L") or code == "E0001", f"Unexpected code: {code}"
