"""End-to-end tests for inspect command (Phase 6).

Tests verify:
- inspect returns expected outputs for a file
- Output is stable and deterministic
- --json produces valid JSON
- --kinds filter works
- Read-only: store is not modified
"""

import json
import pytest
from pathlib import Path

from codebatch.cli import cmd_inspect
from codebatch.store import init_store
from codebatch.snapshot import SnapshotBuilder
from codebatch.batch import BatchManager
from codebatch.runner import ShardRunner
from codebatch.common import object_shard_prefix
from codebatch.tasks import get_executor


class MockArgs:
    """Mock argparse namespace for testing."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def store_with_diagnostics(tmp_path: Path):
    """Create a store with a batch that has diagnostics.

    Returns:
        Tuple of (store_path, batch_id, test_file_path)
    """
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    # Create corpus with a Python file that will produce diagnostics
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    # File with some issues the linter might catch
    test_file = corpus / "test_file.py"
    test_file.write_text("""
# This file has some code
import unused_module
x = 1
y = 2
print(x + y)
""")

    # Also create a second file
    other_file = corpus / "other.py"
    other_file.write_text("# just a comment\n")

    # Create snapshot
    builder = SnapshotBuilder(store)
    snapshot_id = builder.build(corpus)

    # Create batch with full pipeline
    manager = BatchManager(store)
    batch_id = manager.init_batch(snapshot_id, "full")

    # Run all tasks
    runner = ShardRunner(store)
    records = builder.load_file_index(snapshot_id)
    shards = set(object_shard_prefix(r["object"]) for r in records)

    plan = manager.load_plan(batch_id)
    for shard_id in shards:
        for task_def in plan["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_id, task_def["task_id"], shard_id, executor)

    return store, batch_id, "test_file.py"


class TestInspectCommand:
    """Tests for inspect command."""

    def test_inspect_returns_outputs(self, store_with_diagnostics, capsys):
        """Should return outputs for a file."""
        store, batch_id, test_file = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds=None,
            json=False,
            no_color=True,
        )

        result = cmd_inspect(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Inspect:" in captured.out
        assert test_file in captured.out

    def test_inspect_json_output(self, store_with_diagnostics, capsys):
        """Should produce valid JSON output."""
        store, batch_id, test_file = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds=None,
            json=True,
            no_color=True,
        )

        result = cmd_inspect(args)

        assert result == 0
        captured = capsys.readouterr()

        # Should be valid JSON
        outputs = json.loads(captured.out)
        assert isinstance(outputs, list)

    def test_inspect_json_stable(self, store_with_diagnostics, capsys):
        """JSON output should be deterministic."""
        store, batch_id, test_file = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds=None,
            json=True,
            no_color=True,
        )

        # Run twice
        cmd_inspect(args)
        output1 = capsys.readouterr().out

        cmd_inspect(args)
        output2 = capsys.readouterr().out

        # Should be identical
        assert output1 == output2

    def test_inspect_kinds_filter(self, store_with_diagnostics, capsys):
        """Should filter by kinds."""
        store, batch_id, test_file = store_with_diagnostics

        # Filter to only metrics (we know these exist from parse/analyze)
        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds="metric",
            json=True,
            no_color=True,
        )

        result = cmd_inspect(args)

        assert result == 0
        captured = capsys.readouterr()

        # If there are any outputs, they should all be metrics
        if captured.out.strip():
            outputs = json.loads(captured.out)
            for output in outputs:
                assert output.get("kind") == "metric"

    def test_inspect_nonexistent_file(self, store_with_diagnostics, capsys):
        """Should handle nonexistent file gracefully."""
        store, batch_id, _ = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path="nonexistent.py",
            kinds=None,
            json=False,
            no_color=True,
        )

        result = cmd_inspect(args)

        assert result == 0  # Not an error, just no outputs
        captured = capsys.readouterr()
        assert "No outputs found" in captured.out

    def test_inspect_nonexistent_batch(self, store_with_diagnostics, capsys):
        """Should error on nonexistent batch."""
        store, _, test_file = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch="nonexistent-batch",
            path=test_file,
            kinds=None,
            json=False,
            no_color=True,
        )

        result = cmd_inspect(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Batch not found" in captured.err

    def test_inspect_read_only(self, store_with_diagnostics, tmp_path):
        """Should not modify the store (P6-RO gate)."""
        store, batch_id, test_file = store_with_diagnostics

        # Capture store state before
        def get_store_files(root):
            files = set()
            for p in root.rglob("*"):
                if p.is_file():
                    files.add(str(p.relative_to(root)))
            return files

        before = get_store_files(store)

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds=None,
            json=True,
            no_color=True,
        )

        cmd_inspect(args)

        # Store should be unchanged
        after = get_store_files(store)
        assert before == after, f"Store modified! Added: {after - before}"

    def test_inspect_no_color_no_ansi(self, store_with_diagnostics, capsys):
        """--no-color should produce no ANSI codes."""
        store, batch_id, test_file = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds=None,
            json=False,
            no_color=True,
        )

        cmd_inspect(args)
        captured = capsys.readouterr()

        # No ANSI escape codes
        assert "\x1b[" not in captured.out
        assert "\033[" not in captured.out


class TestInspectOutputOrdering:
    """Tests for deterministic output ordering."""

    def test_outputs_sorted_by_task_kind(self, store_with_diagnostics, capsys):
        """Outputs should be sorted by task, then kind."""
        store, batch_id, test_file = store_with_diagnostics

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path=test_file,
            kinds=None,
            json=True,
            no_color=True,
        )

        cmd_inspect(args)
        captured = capsys.readouterr()
        outputs = json.loads(captured.out)

        if len(outputs) > 1:
            # Check ordering
            for i in range(len(outputs) - 1):
                current = outputs[i]
                next_out = outputs[i + 1]

                # Should be sorted by (task_id, kind)
                current_key = (current.get("task_id", ""), current.get("kind", ""))
                next_key = (next_out.get("task_id", ""), next_out.get("kind", ""))

                assert current_key <= next_key, f"Outputs not sorted: {current_key} > {next_key}"
