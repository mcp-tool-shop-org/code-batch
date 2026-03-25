"""Tests for parallel shard execution in WorkflowRunner.

Tests cover:
- max_workers=1 (sequential, backward compatible)
- max_workers>1 (parallel)
- Deterministic results regardless of parallelism
- Callbacks still fire for all shards
"""

import pytest
import threading
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.snapshot import SnapshotBuilder
from codebatch.store import init_store
from codebatch.workflow import WorkflowRunner


@pytest.fixture
def multi_file_store(tmp_path: Path) -> tuple[Path, str]:
    """Create a store with multiple files to ensure multiple shards."""
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    corpus = tmp_path / "corpus"
    corpus.mkdir()

    # Create enough files that we get multiple distinct shard IDs
    for i in range(20):
        (corpus / f"mod_{i}.py").write_text(
            f"def func_{i}():\n    return {i}\n\nresult = func_{i}()\n"
        )

    builder = SnapshotBuilder(store)
    snapshot_id = builder.build(corpus)

    manager = BatchManager(store)
    batch_id = manager.init_batch(snapshot_id, "parse")

    return store, batch_id


@pytest.fixture
def multi_file_full_store(tmp_path: Path) -> tuple[Path, str]:
    """Create a store with multiple files using the full pipeline."""
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    corpus = tmp_path / "corpus"
    corpus.mkdir()

    for i in range(10):
        (corpus / f"module_{i}.py").write_text(
            f"import os\n\ndef process_{i}(data):\n    return len(data) + {i}\n"
        )

    builder = SnapshotBuilder(store)
    snapshot_id = builder.build(corpus)

    manager = BatchManager(store)
    batch_id = manager.init_batch(snapshot_id, "full")

    return store, batch_id


class TestParallelExecution:
    """Tests for parallel shard execution."""

    def test_sequential_still_works(self, multi_file_store):
        """max_workers=1 (default) runs sequentially as before."""
        store, batch_id = multi_file_store
        runner = WorkflowRunner(store)

        result = runner.run(batch_id, max_workers=1)

        assert result.success is True
        assert result.tasks_completed >= 1
        assert result.shards_completed >= 1

    def test_parallel_completes_all_shards(self, multi_file_store):
        """max_workers=4 runs all shards to completion."""
        store, batch_id = multi_file_store
        runner = WorkflowRunner(store)

        result = runner.run(batch_id, max_workers=4)

        assert result.success is True
        assert result.tasks_completed >= 1
        assert result.shards_completed >= 1
        assert result.shards_failed == 0

    def test_parallel_deterministic_results(self, tmp_path: Path):
        """Parallel and sequential runs produce same output counts."""
        # Create two identical stores
        for label, workers in [("seq", 1), ("par", 4)]:
            store = tmp_path / f"store_{label}"
            store.mkdir()
            init_store(store)

            corpus = tmp_path / "corpus"
            if not corpus.exists():
                corpus.mkdir()
                for i in range(10):
                    (corpus / f"f_{i}.py").write_text(
                        f"x_{i} = {i}\n"
                    )

            builder = SnapshotBuilder(store)
            snapshot_id = builder.build(corpus)

            manager = BatchManager(store)
            batch_id = manager.init_batch(snapshot_id, "parse")

            runner = WorkflowRunner(store)
            result = runner.run(batch_id, max_workers=workers)

            assert result.success is True

        # Both should complete the same number of shards
        # (We can't compare exact counts because shard distribution
        # is deterministic, so they should match exactly)
        seq_store = tmp_path / "store_seq"
        par_store = tmp_path / "store_par"

        seq_runner = WorkflowRunner(seq_store)
        par_runner = WorkflowRunner(par_store)

        # Get batch IDs (only one batch in each store)
        seq_batches = list((seq_store / "batches").iterdir())
        par_batches = list((par_store / "batches").iterdir())

        seq_status = seq_runner.get_status(seq_batches[0].name)
        par_status = par_runner.get_status(par_batches[0].name)

        assert seq_status.done_shards == par_status.done_shards

    def test_parallel_callbacks_fire(self, multi_file_store):
        """Callbacks still fire for every shard in parallel mode."""
        store, batch_id = multi_file_store
        runner = WorkflowRunner(store)

        started = []
        completed = []
        lock = threading.Lock()

        def on_start(b, t, s):
            with lock:
                started.append((b, t, s))

        def on_complete(b, t, s, state):
            with lock:
                completed.append((b, t, s, state["status"]))

        result = runner.run(
            batch_id,
            max_workers=4,
            on_shard_start=on_start,
            on_shard_complete=on_complete,
        )

        assert result.success is True
        assert len(started) >= 1
        assert len(completed) >= 1
        # Every started shard should also be completed
        assert len(started) == len(completed)
        # All should be done
        assert all(status == "done" for _, _, _, status in completed)

    def test_parallel_full_pipeline(self, multi_file_full_store):
        """Full pipeline with parallel shards completes successfully."""
        store, batch_id = multi_file_full_store
        runner = WorkflowRunner(store)

        result = runner.run(batch_id, max_workers=4)

        assert result.success is True
        assert result.tasks_completed == 4  # parse, analyze, symbols, lint
        assert result.shards_failed == 0

    def test_resume_with_parallel(self, multi_file_store):
        """Resume with max_workers passes through to run."""
        store, batch_id = multi_file_store
        runner = WorkflowRunner(store)

        # First run completes everything
        runner.run(batch_id, max_workers=2)

        # Resume should find everything done
        result = runner.resume(batch_id, max_workers=2)

        assert result.success is True
        # All shards were already done, so shards_completed reflects that
        assert result.shards_completed >= 1

    def test_max_workers_two(self, multi_file_store):
        """max_workers=2 also works correctly."""
        store, batch_id = multi_file_store
        runner = WorkflowRunner(store)

        result = runner.run(batch_id, max_workers=2)

        assert result.success is True
        assert result.shards_failed == 0
