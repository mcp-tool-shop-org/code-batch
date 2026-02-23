"""End-to-end Phase 1 acceptance tests.

These tests verify the complete workflow from snapshot to query.
"""

import json
import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.cas import ObjectStore
from codebatch.common import object_shard_prefix
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.parse import parse_executor


@pytest.fixture
def clean_store(tmp_path: Path) -> Path:
    """Create a completely clean store directory."""
    store = tmp_path / "store"
    store.mkdir()
    return store


@pytest.fixture
def corpus_dir() -> Path:
    """Get the test corpus directory."""
    return Path(__file__).parent / "fixtures" / "corpus"


class TestCleanRoomRun:
    """C1. Clean-room run acceptance tests."""

    def test_full_workflow(self, clean_store: Path, corpus_dir: Path):
        """Complete workflow: snapshot -> batch -> run shards -> query."""
        # 1. Snapshot fixture corpus
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        # Verify snapshot created
        snapshot = snapshot_builder.load_snapshot(snapshot_id)
        assert snapshot["file_count"] >= 5
        assert snapshot["total_bytes"] > 0

        # 2. Batch init parse pipeline
        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        # Verify batch created
        batch = batch_manager.load_batch(batch_id)
        assert batch["status"] == "pending"
        assert batch["pipeline"] == "parse"

        # 3. Run all shards that have files
        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards_with_files:
            state = runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            assert state["status"] == "done"

        # 4. Run queries
        engine = QueryEngine(clean_store)

        # Query diagnostics
        engine.query_diagnostics(batch_id, "01_parse")
        # Our corpus has clean files, so may be empty

        # Query AST outputs
        ast_outputs = engine.query_outputs(batch_id, "01_parse", kind="ast")
        assert len(ast_outputs) >= 1, "Should have at least one AST output"

        # Query stats
        stats = engine.query_stats(batch_id, "01_parse", group_by="kind")
        assert "ast" in stats
        assert stats["ast"] >= 1

        # Get summary
        summary = engine.get_task_summary(batch_id, "01_parse")
        assert summary["total_outputs"] >= 1
        assert summary["files_with_outputs"] >= 1

    def test_queries_work_without_events(self, clean_store: Path, corpus_dir: Path):
        """Queries work even if events.jsonl files are deleted."""
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)
        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")
        runner = ShardRunner(clean_store)

        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Delete events.jsonl files
        batch_events = clean_store / "batches" / batch_id / "events.jsonl"
        task_events = (
            clean_store / "batches" / batch_id / "tasks" / "01_parse" / "events.jsonl"
        )

        if batch_events.exists():
            batch_events.unlink()
        if task_events.exists():
            task_events.unlink()

        # Queries should still work
        engine = QueryEngine(clean_store)
        outputs = engine.query_outputs(batch_id, "01_parse")
        assert len(outputs) >= 1

        stats = engine.query_stats(batch_id, "01_parse")
        assert "ast" in stats


class TestChaosResilience:
    """C2. Chaos / resilience checks."""

    def test_kill_shard_midrun_and_rerun(self, clean_store: Path, corpus_dir: Path):
        """Kill shard mid-run, rerun shard -> stable done."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)
        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")
        runner = ShardRunner(clean_store)

        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        call_count = [0]

        def crashing_executor(config, files, r):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Simulated crash")
            return parse_executor(config, files, r)

        # First run - crashes
        state = runner.run_shard(batch_id, "01_parse", shard_id, crashing_executor)
        assert state["status"] == "failed"

        # Reset and rerun
        runner.reset_shard(batch_id, "01_parse", shard_id)
        state = runner.run_shard(batch_id, "01_parse", shard_id, crashing_executor)
        assert state["status"] == "done"

    def test_duplicate_run_no_semantic_duplicates(
        self, clean_store: Path, corpus_dir: Path
    ):
        """Running same shard twice doesn't create duplicate outputs."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)
        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")
        runner = ShardRunner(clean_store)

        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        # Run once
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        outputs1 = runner.get_shard_outputs(batch_id, "01_parse", shard_id)

        # Reset to ready state manually (simulate wanting to rerun)
        state = runner._load_state(batch_id, "01_parse", shard_id)
        state["status"] = "ready"
        runner._save_state(batch_id, "01_parse", shard_id, state)

        # Run again
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        outputs2 = runner.get_shard_outputs(batch_id, "01_parse", shard_id)

        # Same number of outputs (replaced, not duplicated)
        assert len(outputs1) == len(outputs2)


class TestDriftResistance:
    """C3. Drift resistance checks."""

    def test_unknown_field_tolerance(self, clean_store: Path, corpus_dir: Path):
        """Reader tolerates unknown fields in records."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)
        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")
        runner = ShardRunner(clean_store)

        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run all shards with files
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Verify we have outputs before modification
        engine = QueryEngine(clean_store)
        initial_outputs = engine.query_outputs(batch_id, "01_parse")
        assert len(initial_outputs) >= 1, "Should have outputs before modification"

        # Add unknown field to ALL output records in ALL shards
        for shard_id in shards_with_files:
            outputs_path = (
                clean_store
                / "batches"
                / batch_id
                / "tasks"
                / "01_parse"
                / "shards"
                / shard_id
                / "outputs.index.jsonl"
            )

            if outputs_path.exists():
                content = outputs_path.read_text().strip()
                if content:
                    lines = content.split("\n")
                    modified_lines = []
                    for line in lines:
                        if line:
                            record = json.loads(line)
                            record["future_unknown_field"] = "some_value"
                            modified_lines.append(json.dumps(record))
                    outputs_path.write_text("\n".join(modified_lines) + "\n")

        # Query should still work after adding unknown fields
        outputs = engine.query_outputs(batch_id, "01_parse")
        assert len(outputs) >= 1

    def test_snapshot_determinism(self, clean_store: Path, corpus_dir: Path):
        """Snapshot twice on same input yields identical output."""
        snapshot_builder = SnapshotBuilder(clean_store)

        # First snapshot
        snap1 = snapshot_builder.build(corpus_dir, snapshot_id="snap-1")
        records1 = snapshot_builder.load_file_index(snap1)

        # Second snapshot
        snap2 = snapshot_builder.build(corpus_dir, snapshot_id="snap-2")
        records2 = snapshot_builder.load_file_index(snap2)

        # Same number of records
        assert len(records1) == len(records2)

        # Same paths and objects
        paths1 = [(r["path"], r["object"]) for r in records1]
        paths2 = [(r["path"], r["object"]) for r in records2]
        assert paths1 == paths2

    def test_object_deduplication(self, clean_store: Path, corpus_dir: Path):
        """Same file content deduplicates in CAS."""
        object_store = ObjectStore(clean_store)

        data = b"Hello, World!"

        ref1 = object_store.put_bytes(data)
        ref2 = object_store.put_bytes(data)

        assert ref1 == ref2

        # Only one object exists - extract hex hash from sha256:<hex>
        hex_hash = ref1.split(":")[1]
        object_path = (
            clean_store / "objects" / "sha256" / hex_hash[:2] / hex_hash[2:4] / hex_hash
        )
        assert object_path.exists()


class TestSemanticOutputsAsTruth:
    """Verify semantic queries don't depend on events."""

    def test_outputs_index_is_sufficient(self, clean_store: Path, corpus_dir: Path):
        """All semantic questions answerable from outputs index alone."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)
        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")
        runner = ShardRunner(clean_store)

        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        engine = QueryEngine(clean_store)

        # All these queries use only outputs.index.jsonl
        # 1. Which files produced diagnostics?
        failed = engine.query_failed_files(batch_id, "01_parse")
        assert isinstance(failed, list)

        # 2. Which outputs exist for task?
        outputs = engine.query_outputs(batch_id, "01_parse")
        assert isinstance(outputs, list)

        # 3. Aggregate counts
        stats = engine.query_stats(batch_id, "01_parse", group_by="kind")
        assert isinstance(stats, dict)

        stats_sev = engine.query_stats(batch_id, "01_parse", group_by="severity")
        assert isinstance(stats_sev, dict)
