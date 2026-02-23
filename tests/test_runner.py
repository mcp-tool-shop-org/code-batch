"""Tests for shard runner."""

import json
import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """Create a temporary store root."""
    return tmp_path / "store"


@pytest.fixture
def corpus_dir() -> Path:
    """Get the test corpus directory."""
    return Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def snapshot_id(store: Path, corpus_dir: Path) -> str:
    """Create a snapshot and return its ID."""
    store.mkdir(parents=True, exist_ok=True)
    builder = SnapshotBuilder(store)
    return builder.build(corpus_dir, snapshot_id="test-snapshot")


@pytest.fixture
def batch_id(store: Path, snapshot_id: str) -> str:
    """Create a batch and return its ID."""
    manager = BatchManager(store)
    return manager.init_batch(snapshot_id, "parse", batch_id="test-batch")


def simple_executor(config: dict, files: list[dict], runner: ShardRunner) -> list[dict]:
    """Simple test executor that just counts files."""
    return [
        {
            "path": f["path"],
            "kind": "metric",
            "value": f["size"],
        }
        for f in files
    ]


def failing_executor(
    config: dict, files: list[dict], runner: ShardRunner
) -> list[dict]:
    """Executor that always fails."""
    raise RuntimeError("Intentional failure")


class TestShardRunner:
    """Tests for ShardRunner."""

    def test_run_shard_success(self, store: Path, batch_id: str):
        """Running a shard produces outputs and transitions to done."""
        runner = ShardRunner(store)

        # Pick a shard that has files (check which ones exist)
        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)

        # Find a shard with files
        shard_id = None
        for r in records:
            shard_id = object_shard_prefix(r["object"])
            break

        assert shard_id is not None, "No files in snapshot"

        # Run the shard
        final_state = runner.run_shard(batch_id, "01_parse", shard_id, simple_executor)

        assert final_state["status"] == "done"
        assert final_state["attempt"] == 1
        assert "completed_at" in final_state
        assert final_state["stats"]["files_processed"] >= 1

        # Check outputs were written
        outputs = runner.get_shard_outputs(batch_id, "01_parse", shard_id)
        assert len(outputs) >= 1
        assert outputs[0]["kind"] == "metric"

    def test_run_shard_failure(self, store: Path, batch_id: str):
        """Running a failing shard transitions to failed state."""
        runner = ShardRunner(store)

        # Use shard "00" (may or may not have files, doesn't matter for failure test)
        shard_id = "00"

        final_state = runner.run_shard(batch_id, "01_parse", shard_id, failing_executor)

        assert final_state["status"] == "failed"
        assert final_state["attempt"] == 1
        assert "error" in final_state
        assert final_state["error"]["code"] == "RuntimeError"
        assert "Intentional failure" in final_state["error"]["message"]

    def test_run_shard_already_done_skips(self, store: Path, batch_id: str):
        """Running an already-done shard skips execution."""
        runner = ShardRunner(store)

        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        # Run once
        runner.run_shard(batch_id, "01_parse", shard_id, simple_executor)

        # Run again - should skip
        call_count = [0]

        def counting_executor(config, files, r):
            call_count[0] += 1
            return simple_executor(config, files, r)

        final_state = runner.run_shard(
            batch_id, "01_parse", shard_id, counting_executor
        )

        assert final_state["status"] == "done"
        assert call_count[0] == 0  # Executor was not called

    def test_reset_shard(self, store: Path, batch_id: str):
        """Can reset a failed shard for retry."""
        runner = ShardRunner(store)
        shard_id = "00"

        # Fail the shard
        runner.run_shard(batch_id, "01_parse", shard_id, failing_executor)

        # Reset it
        new_state = runner.reset_shard(batch_id, "01_parse", shard_id)

        assert new_state["status"] == "ready"
        assert new_state["attempt"] == 1  # Preserves previous attempt count

    def test_reset_non_failed_shard_raises(self, store: Path, batch_id: str):
        """Cannot reset a shard that isn't failed."""
        runner = ShardRunner(store)
        shard_id = "00"

        # Shard is in ready state
        with pytest.raises(ValueError, match="Can only reset failed shards"):
            runner.reset_shard(batch_id, "01_parse", shard_id)

    def test_retry_increments_attempt(self, store: Path, batch_id: str):
        """Retrying a shard increments the attempt counter."""
        runner = ShardRunner(store)
        shard_id = "00"

        # Fail twice
        runner.run_shard(batch_id, "01_parse", shard_id, failing_executor)
        state1 = runner._load_state(batch_id, "01_parse", shard_id)
        assert state1["attempt"] == 1

        runner.reset_shard(batch_id, "01_parse", shard_id)
        runner.run_shard(batch_id, "01_parse", shard_id, failing_executor)
        state2 = runner._load_state(batch_id, "01_parse", shard_id)
        assert state2["attempt"] == 2

    def test_events_logged(self, store: Path, batch_id: str):
        """Events are logged during shard execution."""
        runner = ShardRunner(store)

        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, simple_executor)

        # Check task events
        events_path = (
            store / "batches" / batch_id / "tasks" / "01_parse" / "events.jsonl"
        )
        events = []
        with open(events_path, "r") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        event_types = [e["event"] for e in events]
        assert "shard_started" in event_types
        assert "shard_completed" in event_types

    def test_outputs_have_required_fields(self, store: Path, batch_id: str):
        """Output records have all required fields."""
        runner = ShardRunner(store)

        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, simple_executor)

        outputs = runner.get_shard_outputs(batch_id, "01_parse", shard_id)
        for output in outputs:
            assert "schema_version" in output
            assert "snapshot_id" in output
            assert "batch_id" in output
            assert "task_id" in output
            assert "shard_id" in output
            assert "path" in output
            assert "kind" in output
            assert "ts" in output


class TestAtomicOutputCommit:
    """Tests for atomic output commits."""

    def test_kill_mid_run_no_corruption(self, store: Path, batch_id: str):
        """Simulating a kill mid-run doesn't corrupt outputs."""
        runner = ShardRunner(store)
        shard_id = "00"

        call_count = [0]

        def interrupting_executor(config, files, r):
            call_count[0] += 1
            if call_count[0] == 1:
                # Simulate a crash by raising an exception
                raise KeyboardInterrupt("Simulated crash")
            return simple_executor(config, files, r)

        # First run - crash
        try:
            runner.run_shard(batch_id, "01_parse", shard_id, interrupting_executor)
        except KeyboardInterrupt:
            pass

        # State should be failed (KeyboardInterrupt is caught)
        runner._load_state(batch_id, "01_parse", shard_id)
        # Note: KeyboardInterrupt might propagate or be caught - check outputs
        outputs_path = (
            runner._shard_dir(batch_id, "01_parse", shard_id) / "outputs.index.jsonl"
        )

        # The temp file should not have been renamed to outputs
        # (atomic write means no partial outputs)
        temp_path = outputs_path.with_suffix(".tmp")
        assert not temp_path.exists()
