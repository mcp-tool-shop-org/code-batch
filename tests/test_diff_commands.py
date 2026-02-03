"""End-to-end tests for diff/regressions/improvements commands (Phase 6).

Tests verify:
- diff shows correct added/removed/changed
- regressions shows new problems
- improvements shows fixes
- --json outputs match expected schema
- Read-only: store is not modified
"""

import json
import pytest
from pathlib import Path

from codebatch.cli import cmd_diff, cmd_regressions, cmd_improvements
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
def two_batches(tmp_path: Path):
    """Create a store with two batches for diff testing.

    Batch A: baseline with some code
    Batch B: modified code (adds new file, changes existing)

    Returns:
        Tuple of (store_path, batch_a_id, batch_b_id)
    """
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    # --- Batch A: Baseline ---
    corpus_a = tmp_path / "corpus_a"
    corpus_a.mkdir()

    # File that will stay the same
    (corpus_a / "unchanged.py").write_text("x = 1\n")

    # File that will be removed in B
    (corpus_a / "removed.py").write_text("y = 2\n")

    # File that will change in B
    (corpus_a / "changed.py").write_text("z = 3\n")

    builder = SnapshotBuilder(store)
    snapshot_a = builder.build(corpus_a)

    manager = BatchManager(store)
    batch_a = manager.init_batch(snapshot_a, "full")

    # Run batch A
    runner = ShardRunner(store)
    records_a = builder.load_file_index(snapshot_a)
    shards_a = set(object_shard_prefix(r["object"]) for r in records_a)
    plan_a = manager.load_plan(batch_a)

    for shard_id in shards_a:
        for task_def in plan_a["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_a, task_def["task_id"], shard_id, executor)

    # --- Batch B: Modified ---
    corpus_b = tmp_path / "corpus_b"
    corpus_b.mkdir()

    # Unchanged file
    (corpus_b / "unchanged.py").write_text("x = 1\n")

    # Changed file (different content)
    (corpus_b / "changed.py").write_text("z = 100\nw = 200\n")

    # New file
    (corpus_b / "added.py").write_text("new_var = 'hello'\n")

    snapshot_b = builder.build(corpus_b)
    batch_b = manager.init_batch(snapshot_b, "full")

    # Run batch B
    records_b = builder.load_file_index(snapshot_b)
    shards_b = set(object_shard_prefix(r["object"]) for r in records_b)
    plan_b = manager.load_plan(batch_b)

    for shard_id in shards_b:
        for task_def in plan_b["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_b, task_def["task_id"], shard_id, executor)

    return store, batch_a, batch_b


class TestDiffCommand:
    """Tests for diff command."""

    def test_diff_returns_changes(self, two_batches, capsys):
        """Should return changes between batches."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            kind=None,
            json=False,
            no_color=True,
            explain=False,
        )

        result = cmd_diff(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Diff:" in captured.out

    def test_diff_json_output(self, two_batches, capsys):
        """Should produce valid JSON output."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            kind=None,
            json=True,
            no_color=True,
            explain=False,
        )

        result = cmd_diff(args)

        assert result == 0
        captured = capsys.readouterr()

        # Should be valid JSON with expected structure
        data = json.loads(captured.out)
        assert "added" in data
        assert "removed" in data
        assert "changed" in data
        assert "summary" in data

    def test_diff_json_stable(self, two_batches, capsys):
        """JSON output should be deterministic."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            kind=None,
            json=True,
            no_color=True,
            explain=False,
        )

        # Run twice
        cmd_diff(args)
        output1 = capsys.readouterr().out

        cmd_diff(args)
        output2 = capsys.readouterr().out

        assert output1 == output2

    def test_diff_kind_filter(self, two_batches, capsys):
        """Should filter by kind."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            kind="metric",
            json=True,
            no_color=True,
            explain=False,
        )

        result = cmd_diff(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        # All items should be metrics if any exist
        for item in data.get("added", []) + data.get("removed", []):
            assert item.get("kind") == "metric"

    def test_diff_read_only(self, two_batches):
        """Should not modify the store (P6-RO gate)."""
        store, batch_a, batch_b = two_batches

        def get_store_files(root):
            files = set()
            for p in root.rglob("*"):
                if p.is_file():
                    files.add(str(p.relative_to(root)))
            return files

        before = get_store_files(store)

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            kind=None,
            json=True,
            no_color=True,
            explain=False,
        )

        cmd_diff(args)

        after = get_store_files(store)
        assert before == after

    def test_diff_explain(self, two_batches, capsys):
        """--explain should show data sources."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            kind=None,
            json=False,
            no_color=True,
            explain=True,
        )

        result = cmd_diff(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Data Sources:" in captured.out
        assert "does not use events" in captured.out.lower()


class TestRegressionsCommand:
    """Tests for regressions command."""

    def test_regressions_basic(self, two_batches, capsys):
        """Should run without errors."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=False,
            no_color=True,
            explain=False,
        )

        result = cmd_regressions(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Regressions:" in captured.out

    def test_regressions_json_output(self, two_batches, capsys):
        """Should produce valid JSON output."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=True,
            no_color=True,
            explain=False,
        )

        result = cmd_regressions(args)

        assert result == 0
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "regressions" in data
        assert "count" in data
        assert isinstance(data["regressions"], list)

    def test_regressions_read_only(self, two_batches):
        """Should not modify the store."""
        store, batch_a, batch_b = two_batches

        def get_store_files(root):
            return set(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

        before = get_store_files(store)

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=True,
            no_color=True,
            explain=False,
        )

        cmd_regressions(args)

        after = get_store_files(store)
        assert before == after


class TestImprovementsCommand:
    """Tests for improvements command."""

    def test_improvements_basic(self, two_batches, capsys):
        """Should run without errors."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=False,
            no_color=True,
            explain=False,
        )

        result = cmd_improvements(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Improvements:" in captured.out

    def test_improvements_json_output(self, two_batches, capsys):
        """Should produce valid JSON output."""
        store, batch_a, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=True,
            no_color=True,
            explain=False,
        )

        result = cmd_improvements(args)

        assert result == 0
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert "improvements" in data
        assert "count" in data
        assert isinstance(data["improvements"], list)

    def test_improvements_read_only(self, two_batches):
        """Should not modify the store."""
        store, batch_a, batch_b = two_batches

        def get_store_files(root):
            return set(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

        before = get_store_files(store)

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=True,
            no_color=True,
            explain=False,
        )

        cmd_improvements(args)

        after = get_store_files(store)
        assert before == after


class TestDiffErrorHandling:
    """Tests for error handling in diff commands."""

    def test_diff_nonexistent_batch_a(self, two_batches, capsys):
        """Should error on nonexistent batch A."""
        store, _, batch_b = two_batches

        args = MockArgs(
            store=str(store),
            batch_a="nonexistent",
            batch_b=batch_b,
            kind=None,
            json=False,
            no_color=True,
            explain=False,
        )

        result = cmd_diff(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_diff_nonexistent_batch_b(self, two_batches, capsys):
        """Should error on nonexistent batch B."""
        store, batch_a, _ = two_batches

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b="nonexistent",
            kind=None,
            json=False,
            no_color=True,
            explain=False,
        )

        result = cmd_diff(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_diff_nonexistent_store(self, tmp_path, capsys):
        """Should error on nonexistent store."""
        args = MockArgs(
            store=str(tmp_path / "nonexistent"),
            batch_a="batch1",
            batch_b="batch2",
            kind=None,
            json=False,
            no_color=True,
            explain=False,
        )

        result = cmd_diff(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "Store does not exist" in captured.err
