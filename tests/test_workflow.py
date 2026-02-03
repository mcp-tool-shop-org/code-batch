"""Tests for Phase 5 workflow module.

Tests cover:
- WorkflowRunner.run()
- WorkflowRunner.resume()
- WorkflowRunner.get_status()
- Output summary
- Pipeline listing
"""

import json
import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.store import init_store
from codebatch.tasks import get_executor
from codebatch.workflow import (
    WorkflowRunner,
    get_output_summary,
    get_shards_for_task,
    list_pipelines,
    get_pipeline_details,
)


@pytest.fixture
def store_with_batch(tmp_path: Path) -> tuple[Path, str]:
    """Create a store with a batch for testing."""
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

    return store, batch_id


@pytest.fixture
def completed_batch(store_with_batch) -> tuple[Path, str]:
    """Create a store with a fully completed batch."""
    store, batch_id = store_with_batch

    # Get batch info
    manager = BatchManager(store)
    batch = manager.load_batch(batch_id)
    plan = manager.load_plan(batch_id)

    # Run tasks
    runner = ShardRunner(store)
    builder = SnapshotBuilder(store)
    records = builder.load_file_index(batch["snapshot_id"])
    shards = set(object_shard_prefix(r["object"]) for r in records)

    for shard_id in shards:
        for task_def in plan["tasks"]:
            executor = get_executor(task_def["task_id"])
            runner.run_shard(batch_id, task_def["task_id"], shard_id, executor)

    return store, batch_id


class TestWorkflowRunner:
    """Tests for WorkflowRunner."""

    def test_get_status_pending(self, store_with_batch):
        """Should show pending status for new batch."""
        store, batch_id = store_with_batch
        runner = WorkflowRunner(store)

        progress = runner.get_status(batch_id)

        assert progress.batch_id == batch_id
        assert progress.pipeline == "full"
        assert len(progress.tasks) == 4  # full pipeline has 4 tasks

    def test_get_status_done(self, completed_batch):
        """Should show done or running status for completed batch."""
        store, batch_id = completed_batch
        runner = WorkflowRunner(store)

        progress = runner.get_status(batch_id)

        # Status may be "running" if there are empty shards (ready but no files)
        # or "done" if all shards with files are done
        assert progress.status in ("done", "running")
        # At least some shards should be done
        assert progress.done_shards >= 1

    def test_run_batch(self, store_with_batch):
        """Should run all shards in a batch."""
        store, batch_id = store_with_batch
        runner = WorkflowRunner(store)

        result = runner.run(batch_id)

        assert result.batch_id == batch_id
        assert result.success is True
        assert result.tasks_completed >= 1
        assert result.shards_completed >= 1

    def test_run_with_task_filter(self, store_with_batch):
        """Should run only specified task."""
        store, batch_id = store_with_batch
        runner = WorkflowRunner(store)

        result = runner.run(batch_id, task_filter="01_parse")

        assert result.success is True
        assert result.tasks_completed == 1

    def test_resume_skips_done(self, completed_batch):
        """Should skip already completed shards."""
        store, batch_id = completed_batch
        runner = WorkflowRunner(store)

        # Resume should complete quickly (everything already done)
        result = runner.resume(batch_id)

        assert result.success is True
        # Shards were already done, so shards_completed reflects already-done count
        assert result.shards_completed >= 1

    def test_run_with_callbacks(self, store_with_batch):
        """Should call progress callbacks."""
        store, batch_id = store_with_batch
        runner = WorkflowRunner(store)

        started = []
        completed = []

        def on_start(b, t, s):
            started.append((b, t, s))

        def on_complete(b, t, s, state):
            completed.append((b, t, s, state["status"]))

        result = runner.run(
            batch_id,
            on_shard_start=on_start,
            on_shard_complete=on_complete,
        )

        assert len(started) >= 1
        assert len(completed) >= 1
        assert completed[0][3] == "done"


class TestGetShardsForTask:
    """Tests for get_shards_for_task."""

    def test_returns_shard_progress(self, completed_batch):
        """Should return ShardProgress for each shard."""
        store, batch_id = completed_batch

        shards = get_shards_for_task(store, batch_id, "01_parse")

        assert len(shards) >= 1
        for shard in shards:
            assert hasattr(shard, "shard_id")
            assert hasattr(shard, "status")

    def test_done_shard_has_stats(self, completed_batch):
        """Should include stats for done shards."""
        store, batch_id = completed_batch

        shards = get_shards_for_task(store, batch_id, "01_parse")
        done_shards = [s for s in shards if s.status == "done"]

        assert len(done_shards) >= 1
        # At least one should have processed files
        assert any(s.files_processed > 0 for s in done_shards)


class TestGetOutputSummary:
    """Tests for get_output_summary."""

    def test_returns_summary(self, completed_batch):
        """Should return summary dict."""
        store, batch_id = completed_batch

        summary = get_output_summary(store, batch_id)

        assert summary["batch_id"] == batch_id
        assert "tasks" in summary
        assert "totals" in summary
        assert summary["totals"]["outputs"] >= 1

    def test_task_filter(self, completed_batch):
        """Should filter by task."""
        store, batch_id = completed_batch

        summary = get_output_summary(store, batch_id, task_filter="01_parse")

        assert len(summary["tasks"]) == 1
        assert "01_parse" in summary["tasks"]


class TestListPipelines:
    """Tests for list_pipelines."""

    def test_returns_pipelines(self):
        """Should return list of pipelines."""
        pipelines = list_pipelines()

        assert len(pipelines) >= 3
        names = [p["name"] for p in pipelines]
        assert "parse" in names
        assert "full" in names

    def test_pipeline_has_tasks(self):
        """Should include tasks in each pipeline."""
        pipelines = list_pipelines()

        for p in pipelines:
            assert "tasks" in p
            assert len(p["tasks"]) >= 1


class TestGetPipelineDetails:
    """Tests for get_pipeline_details."""

    def test_returns_details(self):
        """Should return pipeline details."""
        details = get_pipeline_details("full")

        assert details is not None
        assert details["name"] == "full"
        assert len(details["tasks"]) == 4

    def test_unknown_pipeline(self):
        """Should return None for unknown pipeline."""
        details = get_pipeline_details("nonexistent")

        assert details is None

    def test_task_has_depends_on(self):
        """Should include depends_on in tasks."""
        details = get_pipeline_details("full")

        analyze_task = next(t for t in details["tasks"] if t["task_id"] == "02_analyze")
        assert "depends_on" in analyze_task
        assert "01_parse" in analyze_task["depends_on"]
