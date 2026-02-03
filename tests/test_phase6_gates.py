"""Phase 6 gate enforcement tests.

These tests enforce the Phase 6 gates:
- P6-RO: Read-only enforcement (no store writes)
- P6-DIFF: Diff correctness (pure set math)
- P6-EXPLAIN: Explain fidelity (accurate data sources)
- P6-HEADLESS: Headless compatibility (non-TTY works)
- P6-ISOLATION: UI module isolation (removable without breaks)
"""

import json
import os
import pytest
from pathlib import Path
from typing import Set

from codebatch.cli import cmd_inspect, cmd_diff, cmd_regressions, cmd_improvements, cmd_explain
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


# --- Helper functions for gate harness ---


def canonicalize_store_tree(store_root: Path) -> Set[str]:
    """Capture store tree as set of relative paths.

    Used by P6-RO gate to verify no store writes occurred.

    Returns:
        Set of relative paths from store root.
    """
    paths = set()
    for root, dirs, files in os.walk(store_root):
        # Skip __pycache__ and .pyc files
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        root_path = Path(root)
        for f in files:
            if f.endswith(".pyc"):
                continue
            rel = (root_path / f).relative_to(store_root)
            paths.add(str(rel))
    return paths


def contains_ansi(text: str) -> bool:
    """Check if text contains ANSI escape sequences.

    Used by P6-HEADLESS gate.
    """
    return "\x1b[" in text or "\033[" in text


def is_valid_json(text: str) -> bool:
    """Check if text is valid JSON.

    Used by P6-HEADLESS gate.
    """
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


# --- Fixtures ---


@pytest.fixture
def store_with_batch(tmp_path: Path):
    """Create a store with a batch for testing.

    Returns:
        Tuple of (store_path, batch_id)
    """
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    # Create a simple corpus
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "test.py").write_text("x = 1\nprint(x)")

    # Create snapshot
    builder = SnapshotBuilder(store)
    snapshot_id = builder.build(corpus)

    # Create batch
    manager = BatchManager(store)
    batch_id = manager.init_batch(snapshot_id, "full")

    # Run tasks
    runner = ShardRunner(store)
    records = builder.load_file_index(snapshot_id)
    shards = set(object_shard_prefix(r["object"]) for r in records)

    plan = manager.load_plan(batch_id)
    for shard_id in shards:
        for task_def in plan["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_id, task_def["task_id"], shard_id, executor)

    return store, batch_id


@pytest.fixture
def two_batches(tmp_path: Path):
    """Create a store with two batches for diff testing.

    Returns:
        Tuple of (store_path, batch_a_id, batch_b_id)
    """
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    builder = SnapshotBuilder(store)
    manager = BatchManager(store)
    runner = ShardRunner(store)

    # Batch A
    corpus_a = tmp_path / "corpus_a"
    corpus_a.mkdir()
    (corpus_a / "test.py").write_text("x = 1")

    snapshot_a = builder.build(corpus_a)
    batch_a = manager.init_batch(snapshot_a, "full")

    records_a = builder.load_file_index(snapshot_a)
    shards_a = set(object_shard_prefix(r["object"]) for r in records_a)
    plan_a = manager.load_plan(batch_a)

    for shard_id in shards_a:
        for task_def in plan_a["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_a, task_def["task_id"], shard_id, executor)

    # Batch B
    corpus_b = tmp_path / "corpus_b"
    corpus_b.mkdir()
    (corpus_b / "test.py").write_text("x = 1\ny = 2")
    (corpus_b / "new.py").write_text("z = 3")

    snapshot_b = builder.build(corpus_b)
    batch_b = manager.init_batch(snapshot_b, "full")

    records_b = builder.load_file_index(snapshot_b)
    shards_b = set(object_shard_prefix(r["object"]) for r in records_b)
    plan_b = manager.load_plan(batch_b)

    for shard_id in shards_b:
        for task_def in plan_b["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_b, task_def["task_id"], shard_id, executor)

    return store, batch_a, batch_b


# --- Gate P6-RO: Read-Only Enforcement ---


class TestGateP6RO:
    """P6-RO gate: Phase 6 commands must not modify the store."""

    def test_inspect_does_not_write(self, store_with_batch, capsys):
        """inspect command should not modify store."""
        store, batch_id = store_with_batch

        before = canonicalize_store_tree(store)

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path="test.py",
            kinds=None,
            json=True,
            no_color=True,
            explain=False,
        )
        cmd_inspect(args)

        after = canonicalize_store_tree(store)
        assert before == after, f"Store modified by inspect! Added: {after - before}"

    def test_diff_does_not_write(self, two_batches, capsys):
        """diff command should not modify store."""
        store, batch_a, batch_b = two_batches

        before = canonicalize_store_tree(store)

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

        after = canonicalize_store_tree(store)
        assert before == after, f"Store modified by diff!"

    def test_regressions_does_not_write(self, two_batches, capsys):
        """regressions command should not modify store."""
        store, batch_a, batch_b = two_batches

        before = canonicalize_store_tree(store)

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=True,
            no_color=True,
            explain=False,
        )
        cmd_regressions(args)

        after = canonicalize_store_tree(store)
        assert before == after, f"Store modified by regressions!"

    def test_improvements_does_not_write(self, two_batches, capsys):
        """improvements command should not modify store."""
        store, batch_a, batch_b = two_batches

        before = canonicalize_store_tree(store)

        args = MockArgs(
            store=str(store),
            batch_a=batch_a,
            batch_b=batch_b,
            json=True,
            no_color=True,
            explain=False,
        )
        cmd_improvements(args)

        after = canonicalize_store_tree(store)
        assert before == after, f"Store modified by improvements!"


# --- Gate P6-HEADLESS: Headless Compatibility ---


class TestGateP6Headless:
    """P6-HEADLESS gate: Commands must work without TTY."""

    def test_inspect_no_color_no_ansi(self, store_with_batch, capsys):
        """inspect --no-color should produce no ANSI sequences."""
        store, batch_id = store_with_batch

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path="test.py",
            kinds=None,
            json=False,
            no_color=True,
            explain=False,
        )
        cmd_inspect(args)

        captured = capsys.readouterr()
        assert not contains_ansi(captured.out), "ANSI codes in --no-color output"

    def test_inspect_json_valid(self, store_with_batch, capsys):
        """inspect --json should produce valid JSON."""
        store, batch_id = store_with_batch

        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path="test.py",
            kinds=None,
            json=True,
            no_color=True,
            explain=False,
        )
        cmd_inspect(args)

        captured = capsys.readouterr()
        assert is_valid_json(captured.out), "Invalid JSON output"

    def test_diff_no_color_no_ansi(self, two_batches, capsys):
        """diff --no-color should produce no ANSI sequences."""
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
        cmd_diff(args)

        captured = capsys.readouterr()
        assert not contains_ansi(captured.out), "ANSI codes in --no-color output"

    def test_diff_json_valid(self, two_batches, capsys):
        """diff --json should produce valid JSON."""
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
        cmd_diff(args)

        captured = capsys.readouterr()
        assert is_valid_json(captured.out), "Invalid JSON output"

    def test_explain_json_valid(self, capsys):
        """explain --json should produce valid JSON."""
        args = MockArgs(subcommand="inspect", json=True)
        cmd_explain(args)

        captured = capsys.readouterr()
        assert is_valid_json(captured.out), "Invalid JSON output"


# --- Gate P6-EXPLAIN: Explain Fidelity ---


class TestGateP6Explain:
    """P6-EXPLAIN gate: --explain must accurately describe data sources."""

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements"])
    def test_explain_does_not_mention_events(self, command, capsys):
        """--explain should NOT mention events as a dependency."""
        args = MockArgs(subcommand=command, json=False)
        cmd_explain(args)

        captured = capsys.readouterr()
        output_lower = captured.out.lower()

        # Should explicitly state events are not used
        assert "does not use events" in output_lower, "Explain should state events not used"

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements"])
    def test_explain_lists_output_kinds(self, command, capsys):
        """--explain should list output kinds used."""
        args = MockArgs(subcommand=command, json=True)
        cmd_explain(args)

        captured = capsys.readouterr()
        info = json.loads(captured.out)

        assert "output_kinds_used" in info
        assert len(info["output_kinds_used"]) > 0

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements"])
    def test_explain_deterministic(self, command, capsys):
        """--explain output should be identical across runs."""
        args = MockArgs(subcommand=command, json=True)

        cmd_explain(args)
        output1 = capsys.readouterr().out

        cmd_explain(args)
        output2 = capsys.readouterr().out

        assert output1 == output2, "Explain output not deterministic"


# --- Gate P6-ISOLATION: UI Module Isolation ---


class TestGateP6Isolation:
    """P6-ISOLATION gate: UI module can be removed without breaking core."""

    def test_ui_module_importable(self):
        """UI module should be independently importable."""
        from codebatch import ui
        from codebatch.ui import format
        from codebatch.ui import pager
        from codebatch.ui import diff

        assert hasattr(format, "render_table")
        assert hasattr(pager, "paginate")
        assert hasattr(diff, "diff_sets")

    def test_core_modules_work_without_ui(self):
        """Core modules should not fail if UI is not imported first."""
        # Import core modules without UI
        import codebatch.store as store_mod
        import codebatch.snapshot as snapshot_mod
        import codebatch.batch as batch_mod
        import codebatch.runner as runner_mod
        import codebatch.query as query_mod

        # Basic functionality should work
        assert hasattr(store_mod, "init_store")
        assert hasattr(snapshot_mod, "SnapshotBuilder")
        assert hasattr(batch_mod, "BatchManager")
        assert hasattr(runner_mod, "ShardRunner")
        assert hasattr(query_mod, "QueryEngine")
