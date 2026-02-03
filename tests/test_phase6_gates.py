"""Phase 6 gate harness tests.

Tests for Phase 6 gates are initially marked as xfail/skip until
the corresponding commands and modules are implemented.

Phase 6 Gates:
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


def capture_file_mtimes(store_root: Path) -> dict[str, float]:
    """Capture modification times for all files in store.

    Returns:
        Dict mapping relative path to mtime.
    """
    mtimes = {}
    for root, dirs, files in os.walk(store_root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        root_path = Path(root)
        for f in files:
            if f.endswith(".pyc"):
                continue
            full = root_path / f
            rel = full.relative_to(store_root)
            mtimes[str(rel)] = full.stat().st_mtime
    return mtimes


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


# --- Gate P6-RO: Read-Only Enforcement ---


@pytest.mark.xfail(reason="P6-RO: inspect command not yet implemented")
class TestGateP6RO_Inspect:
    """P6-RO gate tests for inspect command."""

    def test_inspect_does_not_write(self, store_with_batch):
        """inspect command should not modify store."""
        store, batch_id = store_with_batch

        # Capture before
        before = canonicalize_store_tree(store)

        # Run inspect (when implemented)
        # from codebatch.cli import cmd_inspect
        # cmd_inspect(store, batch_id, "some/path.py")

        # Capture after
        after = canonicalize_store_tree(store)

        assert before == after, f"Store modified! Added: {after - before}, Removed: {before - after}"


@pytest.mark.xfail(reason="P6-RO: diff command not yet implemented")
class TestGateP6RO_Diff:
    """P6-RO gate tests for diff command."""

    def test_diff_does_not_write(self, two_batches_fixture):
        """diff command should not modify store."""
        store, batch_a, batch_b = two_batches_fixture

        # Capture before
        before = canonicalize_store_tree(store)

        # Run diff (when implemented)
        # from codebatch.cli import cmd_diff
        # cmd_diff(store, batch_a, batch_b)

        # Capture after
        after = canonicalize_store_tree(store)

        assert before == after


@pytest.mark.xfail(reason="P6-RO: regressions command not yet implemented")
class TestGateP6RO_Regressions:
    """P6-RO gate tests for regressions command."""

    def test_regressions_does_not_write(self, two_batches_fixture):
        """regressions command should not modify store."""
        store, batch_a, batch_b = two_batches_fixture

        before = canonicalize_store_tree(store)

        # Run regressions (when implemented)

        after = canonicalize_store_tree(store)

        assert before == after


@pytest.mark.xfail(reason="P6-RO: improvements command not yet implemented")
class TestGateP6RO_Improvements:
    """P6-RO gate tests for improvements command."""

    def test_improvements_does_not_write(self, two_batches_fixture):
        """improvements command should not modify store."""
        store, batch_a, batch_b = two_batches_fixture

        before = canonicalize_store_tree(store)

        # Run improvements (when implemented)

        after = canonicalize_store_tree(store)

        assert before == after


# --- Gate P6-DIFF: Diff Correctness ---


@pytest.mark.xfail(reason="P6-DIFF: diff engine not yet implemented")
class TestGateP6Diff:
    """P6-DIFF gate tests for diff correctness."""

    def test_diff_added_set(self):
        """Diff should correctly identify added items."""
        # from codebatch.ui.diff import diff_sets

        set_a = {("diagnostic", "file.py", "E001")}
        set_b = {("diagnostic", "file.py", "E001"), ("diagnostic", "file.py", "E002")}

        # result = diff_sets(set_a, set_b)
        # assert result.added == {("diagnostic", "file.py", "E002")}
        # assert result.removed == set()
        pass

    def test_diff_removed_set(self):
        """Diff should correctly identify removed items."""
        set_a = {("diagnostic", "file.py", "E001"), ("diagnostic", "file.py", "E002")}
        set_b = {("diagnostic", "file.py", "E001")}

        # result = diff_sets(set_a, set_b)
        # assert result.added == set()
        # assert result.removed == {("diagnostic", "file.py", "E002")}
        pass

    def test_diff_deterministic(self):
        """Diff should produce identical results across runs."""
        # Run diff multiple times and compare
        pass


# --- Gate P6-EXPLAIN: Explain Fidelity ---


@pytest.mark.xfail(reason="P6-EXPLAIN: explain command not yet implemented")
class TestGateP6Explain:
    """P6-EXPLAIN gate tests for explain fidelity."""

    def test_explain_lists_output_kinds(self):
        """Explain should list which output kinds are used."""
        # from codebatch.cli import cmd_explain

        # output = cmd_explain("inspect", capture=True)
        # assert "diagnostic" in output or "metric" in output or "symbol" in output
        pass

    def test_explain_lists_tasks(self):
        """Explain should list which tasks are referenced."""
        # output = cmd_explain("inspect", capture=True)
        # assert "01_parse" in output or "02_lint" in output
        pass

    def test_explain_does_not_mention_events(self):
        """Explain should NOT mention events as a dependency."""
        # output = cmd_explain("inspect", capture=True)
        # assert "events" not in output.lower()
        pass

    def test_explain_deterministic(self):
        """Explain output should be identical across runs."""
        # output1 = cmd_explain("inspect", capture=True)
        # output2 = cmd_explain("inspect", capture=True)
        # assert output1 == output2
        pass


# --- Gate P6-HEADLESS: Headless Compatibility ---


@pytest.mark.xfail(reason="P6-HEADLESS: UI commands not yet implemented")
class TestGateP6Headless:
    """P6-HEADLESS gate tests for headless compatibility."""

    def test_no_color_disables_ansi(self):
        """--no-color should produce no ANSI sequences."""
        # from codebatch.cli import cmd_inspect

        # output = cmd_inspect(store, batch_id, path, no_color=True, capture=True)
        # assert not contains_ansi(output)
        pass

    def test_json_output_valid(self):
        """--json should produce valid JSON."""
        # output = cmd_inspect(store, batch_id, path, json_out=True, capture=True)
        # assert is_valid_json(output)
        pass

    def test_json_keys_stable(self):
        """--json should have stable key ordering."""
        # output1 = cmd_inspect(store, batch_id, path, json_out=True, capture=True)
        # output2 = cmd_inspect(store, batch_id, path, json_out=True, capture=True)
        # assert output1 == output2  # Byte-identical
        pass

    def test_non_tty_works(self):
        """Commands should work when stdout is not a TTY."""
        # Run command with stdout redirected to file/pipe
        pass


# --- Gate P6-ISOLATION: UI Module Isolation ---


@pytest.mark.xfail(reason="P6-ISOLATION: UI module not yet implemented")
class TestGateP6Isolation:
    """P6-ISOLATION gate tests for UI module isolation."""

    def test_ui_module_importable(self):
        """UI module should be independently importable."""
        # from codebatch import ui
        # from codebatch.ui import format
        # from codebatch.ui import pager
        # from codebatch.ui import diff
        pass

    def test_core_modules_no_ui_import(self):
        """Core modules should not import UI at module level."""
        # Check that runner, query, store don't import ui
        import codebatch.runner as runner_mod
        import codebatch.query as query_mod
        import codebatch.store as store_mod

        # This should pass - core modules shouldn't depend on UI
        assert "ui" not in dir(runner_mod)
        assert "ui" not in dir(query_mod)
        assert "ui" not in dir(store_mod)


# --- Fixture stubs (to be implemented) ---


@pytest.fixture
def store_with_batch(tmp_path: Path):
    """Create a store with a batch for testing.

    TODO: Move to conftest.py when implementing Phase 6 commands.
    """
    from codebatch.store import init_store
    from codebatch.snapshot import SnapshotBuilder
    from codebatch.batch import BatchManager
    from codebatch.runner import ShardRunner
    from codebatch.common import object_shard_prefix
    from codebatch.tasks import get_executor

    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    # Create a simple corpus
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "test.py").write_text("print('hello')")

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
def two_batches_fixture(tmp_path: Path):
    """Create a store with two batches for diff testing.

    Batch A: has diagnostic E001 on file.py
    Batch B: has E001 removed, E002 added

    TODO: Implement when diff command is built.
    """
    pytest.skip("two_batches_fixture not yet implemented")
