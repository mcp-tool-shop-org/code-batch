"""Tests for the analyze task executor.

The analyze task produces file-level metrics:
- bytes: File size
- loc: Lines of code (non-empty lines)
- lang: Language hint from snapshot
"""

import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.analyze import analyze_executor, count_lines
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


class TestCountLines:
    """Unit tests for count_lines helper."""

    def test_empty_string(self):
        assert count_lines("") == 0

    def test_single_line(self):
        assert count_lines("hello") == 1

    def test_multiple_lines(self):
        assert count_lines("a\nb\nc") == 3

    def test_empty_lines_excluded(self):
        assert count_lines("a\n\nb\n\n\nc") == 3

    def test_whitespace_only_lines_excluded(self):
        assert count_lines("a\n   \nb\n\t\nc") == 3


class TestAnalyzeExecutor:
    """Tests for the analyze_executor function."""

    def test_produces_metrics(self, clean_store: Path, corpus_dir: Path):
        """Analyze task produces metric records."""
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "analyze")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)

        # Find a shard with files
        shard_id = object_shard_prefix(records[0]["object"])

        # Run parse first (dependency)
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Run analyze
        state = runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)
        assert state["status"] == "done"

        # Check outputs
        outputs = runner.get_shard_outputs(batch_id, "02_analyze", shard_id)
        assert len(outputs) > 0, "No metrics produced"

        # All outputs should be kind=metric
        for o in outputs:
            assert o["kind"] == "metric"

    def test_emits_bytes_metric(self, clean_store: Path, corpus_dir: Path):
        """Analyze task emits bytes metric for each file."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "analyze")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)

        outputs = runner.get_shard_outputs(batch_id, "02_analyze", shard_id)
        bytes_metrics = [o for o in outputs if o.get("metric") == "bytes"]

        assert len(bytes_metrics) > 0, "No bytes metrics"
        for m in bytes_metrics:
            assert isinstance(m["value"], int)
            assert m["value"] > 0

    def test_emits_loc_metric_for_text(self, clean_store: Path, corpus_dir: Path):
        """Analyze task emits LOC metric for text files."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "analyze")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)

        # Run ALL shards to ensure we hit text files
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)
        all_loc_metrics = []

        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)
            outputs = runner.get_shard_outputs(batch_id, "02_analyze", shard_id)
            all_loc_metrics.extend([o for o in outputs if o.get("metric") == "loc"])

        # Should have at least some LOC metrics across all shards
        assert len(all_loc_metrics) > 0, (
            "No LOC metrics for text files across all shards"
        )
        for m in all_loc_metrics:
            assert isinstance(m["value"], int)
            assert m["value"] >= 0

    def test_emits_lang_metric(self, clean_store: Path, corpus_dir: Path):
        """Analyze task emits lang metric from snapshot."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "analyze")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)

        outputs = runner.get_shard_outputs(batch_id, "02_analyze", shard_id)
        lang_metrics = [o for o in outputs if o.get("metric") == "lang"]

        assert len(lang_metrics) > 0, "No lang metrics"
        for m in lang_metrics:
            assert isinstance(m["value"], str)

    def test_deterministic_outputs(self, clean_store: Path, corpus_dir: Path):
        """Analyze outputs are deterministic across runs."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)

        # Run 1
        batch_id_1 = batch_manager.init_batch(
            snapshot_id, "analyze", batch_id="batch-run1"
        )
        runner1 = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shard_id = object_shard_prefix(records[0]["object"])

        runner1.run_shard(batch_id_1, "01_parse", shard_id, parse_executor)
        runner1.run_shard(batch_id_1, "02_analyze", shard_id, analyze_executor)
        outputs_1 = runner1.get_shard_outputs(batch_id_1, "02_analyze", shard_id)

        # Run 2
        batch_id_2 = batch_manager.init_batch(
            snapshot_id, "analyze", batch_id="batch-run2"
        )
        runner2 = ShardRunner(clean_store)

        runner2.run_shard(batch_id_2, "01_parse", shard_id, parse_executor)
        runner2.run_shard(batch_id_2, "02_analyze", shard_id, analyze_executor)
        outputs_2 = runner2.get_shard_outputs(batch_id_2, "02_analyze", shard_id)

        # Compare (ignore timestamps and batch-specific fields)
        def normalize(outputs):
            return sorted(
                [(o["kind"], o["path"], o["metric"], o["value"]) for o in outputs]
            )

        assert normalize(outputs_1) == normalize(outputs_2)


class TestAnalyzeIntegration:
    """Integration tests for analyze in the full pipeline."""

    def test_query_metrics_by_kind(self, clean_store: Path, corpus_dir: Path):
        """Can query metrics grouped by metric type."""
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "analyze")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run all shards
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)

        # Query
        engine = QueryEngine(clean_store)
        all_outputs = engine.query_outputs(batch_id, "02_analyze")

        # Should have metrics
        assert len(all_outputs) > 0

        # Group by metric type
        by_metric = {}
        for o in all_outputs:
            metric = o.get("metric", "unknown")
            by_metric.setdefault(metric, []).append(o)

        # Should have bytes, loc, lang
        assert "bytes" in by_metric, (
            f"Missing bytes metrics. Got: {list(by_metric.keys())}"
        )
        assert "lang" in by_metric, (
            f"Missing lang metrics. Got: {list(by_metric.keys())}"
        )
