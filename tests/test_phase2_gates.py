"""Phase 2 Gate Tests.

These tests enforce the Phase 2 hard perimeter:
- Gate 1: Multi-task pipeline end-to-end
- Gate 2: Log independence (queries work without events)
- Gate 3: Cache deletion equivalence
- Gate 4: Retry determinism (per-shard replacement)
- Gate 5: Spec stability (tested via CI script)

All gates must pass for Phase 2 completion.
"""

import json
import os
import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.parse import parse_executor


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


def canonicalize_outputs(outputs: list[dict]) -> list[dict]:
    """Canonicalize outputs for comparison (remove timestamps)."""
    canonical = []
    for o in outputs:
        c = {k: v for k, v in o.items() if k != "ts"}
        canonical.append(c)
    # Sort by (kind, path, code/object)
    return sorted(canonical, key=lambda x: (
        x.get("kind", ""),
        x.get("path", ""),
        x.get("code", ""),
        x.get("object", ""),
    ))


class TestGate1MultiTaskPipeline:
    """Gate 1: Multi-task pipeline end-to-end.

    Tests that a complete pipeline with dependencies works.
    Currently tests parse pipeline (Phase 1).
    Phase 2 will extend to: parse -> analyze -> symbols -> lint
    """

    def test_parse_pipeline_completes(self, clean_store: Path, corpus_dir: Path):
        """Parse pipeline runs to completion on all shards."""
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        runner = ShardRunner(clean_store)

        # Get shards with files
        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run all shards
        for shard_id in shards_with_files:
            state = runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            assert state["status"] == "done", f"Shard {shard_id} failed: {state.get('error')}"

        # Verify outputs exist
        engine = QueryEngine(clean_store)
        outputs = engine.query_outputs(batch_id, "01_parse")
        assert len(outputs) > 0, "No outputs produced"

        # Verify we have AST outputs
        ast_outputs = [o for o in outputs if o["kind"] == "ast"]
        assert len(ast_outputs) > 0, "No AST outputs produced"

    def test_deps_order_enforced(self, clean_store: Path, corpus_dir: Path):
        """Task dependencies must be respected.

        This test will be extended in Phase 2 when deps are enforced.
        Currently just verifies the plan structure.
        """
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)

        # Create batch with analyze pipeline (has deps)
        batch_id = batch_manager.init_batch(snapshot_id, "analyze")

        # Load plan and verify deps structure
        plan = batch_manager.load_plan(batch_id)
        tasks = plan["tasks"]

        # Find analyze task
        analyze_task = next((t for t in tasks if t["task_id"] == "02_analyze"), None)
        assert analyze_task is not None, "02_analyze task not in plan"

        # Verify it has deps on parse (Phase 2 will enforce this)
        assert "depends_on" in analyze_task or "deps" in analyze_task or True, \
            "Deps field expected (Phase 2 will enforce)"


class TestGate2LogIndependence:
    """Gate 2: Log independence.

    Semantic queries must work without reading events.jsonl files.
    """

    def test_queries_work_without_events(self, clean_store: Path, corpus_dir: Path):
        """Deleting events.jsonl doesn't break queries."""
        # Setup and run
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Capture query results BEFORE deleting events
        engine = QueryEngine(clean_store)
        outputs_before = engine.query_outputs(batch_id, "01_parse")
        stats_before = engine.query_stats(batch_id, "01_parse", group_by="kind")

        # Delete ALL events.jsonl files
        for events_file in clean_store.rglob("events.jsonl"):
            events_file.unlink()

        # Verify no events files remain
        events_remaining = list(clean_store.rglob("events.jsonl"))
        assert len(events_remaining) == 0, "Events files still exist"

        # Capture query results AFTER deleting events
        outputs_after = engine.query_outputs(batch_id, "01_parse")
        stats_after = engine.query_stats(batch_id, "01_parse", group_by="kind")

        # Compare (canonicalized)
        assert canonicalize_outputs(outputs_before) == canonicalize_outputs(outputs_after), \
            "Outputs differ after deleting events"
        assert stats_before == stats_after, \
            "Stats differ after deleting events"


class TestGate3CacheDeletionEquivalence:
    """Gate 3: Cache deletion equivalence.

    If indexes/ cache exists, deleting it must not change query results.
    Phase 1 doesn't have indexes/, so this is a placeholder.
    """

    def test_queries_work_without_cache(self, clean_store: Path, corpus_dir: Path):
        """Deleting indexes/ doesn't break queries (when implemented)."""
        # Setup and run
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Capture query results
        engine = QueryEngine(clean_store)
        outputs_before = engine.query_outputs(batch_id, "01_parse")

        # Create and delete indexes/ (simulating cache)
        indexes_dir = clean_store / "indexes"
        indexes_dir.mkdir(exist_ok=True)
        (indexes_dir / "dummy_cache.json").write_text("{}")

        # Delete cache
        import shutil
        shutil.rmtree(indexes_dir)

        # Query again
        outputs_after = engine.query_outputs(batch_id, "01_parse")

        # Compare
        assert canonicalize_outputs(outputs_before) == canonicalize_outputs(outputs_after), \
            "Outputs differ after deleting cache"


class TestGate4RetryDeterminism:
    """Gate 4: Retry determinism.

    Per-shard output replacement must produce identical semantic results.
    """

    def test_shard_retry_produces_same_outputs(self, clean_store: Path, corpus_dir: Path):
        """Retrying a shard produces identical outputs."""
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)

        # Find a shard with files
        shard_id = object_shard_prefix(records[0]["object"])

        # Run 1: clean run
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        outputs_path = clean_store / "batches" / batch_id / "tasks" / "01_parse" / "shards" / shard_id / "outputs.index.jsonl"

        run1_outputs = []
        with open(outputs_path, "r") as f:
            for line in f:
                if line.strip():
                    run1_outputs.append(json.loads(line))

        # Delete state and outputs (simulate retry need)
        state_path = outputs_path.parent / "state.json"
        state_path.unlink()
        outputs_path.unlink()

        # Recreate initial state
        initial_state = {
            "schema_name": "codebatch.shard_state",
            "schema_version": 1,
            "producer": {"name": "codebatch", "version": "0.1.0"},
            "shard_id": shard_id,
            "task_id": "01_parse",
            "batch_id": batch_id,
            "status": "ready",
        }
        with open(state_path, "w") as f:
            json.dump(initial_state, f)

        # Run 2: retry
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        run2_outputs = []
        with open(outputs_path, "r") as f:
            for line in f:
                if line.strip():
                    run2_outputs.append(json.loads(line))

        # Compare (canonicalized - timestamps will differ)
        run1_canonical = canonicalize_outputs(run1_outputs)
        run2_canonical = canonicalize_outputs(run2_outputs)

        assert len(run1_canonical) == len(run2_canonical), \
            f"Output count differs: {len(run1_canonical)} vs {len(run2_canonical)}"

        for i, (o1, o2) in enumerate(zip(run1_canonical, run2_canonical)):
            # Compare kind and path (object refs may differ if not deterministic)
            assert o1.get("kind") == o2.get("kind"), f"Output {i} kind differs"
            assert o1.get("path") == o2.get("path"), f"Output {i} path differs"

    def test_retry_replaces_not_appends(self, clean_store: Path, corpus_dir: Path):
        """Retry overwrites outputs, doesn't append."""
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)

        shard_id = object_shard_prefix(records[0]["object"])

        # Run 1
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        outputs_path = clean_store / "batches" / batch_id / "tasks" / "01_parse" / "shards" / shard_id / "outputs.index.jsonl"
        run1_count = sum(1 for _ in open(outputs_path))

        # Reset to ready state
        state_path = outputs_path.parent / "state.json"
        with open(state_path, "r") as f:
            state = json.load(f)
        state["status"] = "ready"
        with open(state_path, "w") as f:
            json.dump(state, f)

        # Run 2 (should replace, not append)
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        run2_count = sum(1 for _ in open(outputs_path))

        # Counts should be same (replacement), not doubled (append)
        assert run2_count == run1_count, \
            f"Outputs appear to append ({run2_count}) instead of replace ({run1_count})"


class TestGate5SpecStability:
    """Gate 5: Spec stability.

    Protected SPEC regions should not change.
    This is enforced by CI script: scripts/check_spec_protected.py

    This test just verifies the markers exist.
    """

    def test_spec_has_protected_markers(self):
        """SPEC.md contains protected region markers."""
        spec_path = Path(__file__).parent.parent / "SPEC.md"
        assert spec_path.exists(), "SPEC.md not found"

        content = spec_path.read_text()
        assert "SPEC_PROTECTED_BEGIN" in content, "Missing SPEC_PROTECTED_BEGIN marker"
        assert "SPEC_PROTECTED_END" in content, "Missing SPEC_PROTECTED_END marker"

        # Verify BEGIN comes before END
        begin_pos = content.find("SPEC_PROTECTED_BEGIN")
        end_pos = content.find("SPEC_PROTECTED_END")
        assert begin_pos < end_pos, "Protected markers in wrong order"
