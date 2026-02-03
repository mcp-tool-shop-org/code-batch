"""Performance benchmarks for LMDB cache vs JSONL scan.

These tests measure the speedup from cache acceleration.
Run with: pytest tests/test_cache_perf.py --benchmark-only -v
"""

import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.index_build import build_index
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks import get_executor


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


@pytest.fixture
def full_pipeline_batch(clean_store: Path, corpus_dir: Path) -> tuple[Path, str, str]:
    """Run the full pipeline and return (store_root, batch_id, snapshot_id)."""
    # Create snapshot
    snapshot_builder = SnapshotBuilder(clean_store)
    snapshot_id = snapshot_builder.build(corpus_dir)

    # Create batch with full pipeline
    batch_manager = BatchManager(clean_store)
    batch_id = batch_manager.init_batch(snapshot_id, "full")

    # Run all tasks
    runner = ShardRunner(clean_store)
    records = snapshot_builder.load_file_index(snapshot_id)
    shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

    plan = batch_manager.load_plan(batch_id)
    task_order = [t["task_id"] for t in plan["tasks"]]

    for shard_id in shards_with_files:
        for task_id in task_order:
            executor = get_executor(task_id)
            runner.run_shard(batch_id, task_id, shard_id, executor)

    return clean_store, batch_id, snapshot_id


class TestCachePerformance:
    """Performance benchmarks comparing cache vs scan."""

    def test_query_outputs_scan_baseline(self, benchmark, full_pipeline_batch):
        """Benchmark: query_outputs without cache (JSONL scan)."""
        store_root, batch_id, _ = full_pipeline_batch
        engine = QueryEngine(store_root, use_cache=False)

        def query():
            return engine.query_outputs(batch_id, "01_parse")

        result = benchmark(query)
        assert len(result) > 0

    def test_query_outputs_cached(self, benchmark, full_pipeline_batch):
        """Benchmark: query_outputs with cache (LMDB)."""
        store_root, batch_id, _ = full_pipeline_batch
        build_index(store_root, batch_id)
        engine = QueryEngine(store_root, use_cache=True)

        def query():
            return engine.query_outputs(batch_id, "01_parse")

        result = benchmark(query)
        engine.close()
        assert len(result) > 0

    def test_query_stats_scan_baseline(self, benchmark, full_pipeline_batch):
        """Benchmark: query_stats without cache (JSONL scan)."""
        store_root, batch_id, _ = full_pipeline_batch
        engine = QueryEngine(store_root, use_cache=False)

        def query():
            return engine.query_stats(batch_id, "02_analyze", group_by="kind")

        result = benchmark(query)
        assert len(result) > 0

    def test_query_stats_cached(self, benchmark, full_pipeline_batch):
        """Benchmark: query_stats with cache (pre-aggregated counters)."""
        store_root, batch_id, _ = full_pipeline_batch
        build_index(store_root, batch_id)
        engine = QueryEngine(store_root, use_cache=True)

        def query():
            return engine.query_stats(batch_id, "02_analyze", group_by="kind")

        result = benchmark(query)
        engine.close()
        assert len(result) > 0

    def test_multiple_queries_scan(self, benchmark, full_pipeline_batch):
        """Benchmark: multiple queries without cache."""
        store_root, batch_id, _ = full_pipeline_batch
        engine = QueryEngine(store_root, use_cache=False)

        def queries():
            results = []
            for task_id in ["01_parse", "02_analyze", "03_symbols", "04_lint"]:
                results.append(engine.query_outputs(batch_id, task_id))
            return results

        result = benchmark(queries)
        assert len(result) == 4

    def test_multiple_queries_cached(self, benchmark, full_pipeline_batch):
        """Benchmark: multiple queries with cache."""
        store_root, batch_id, _ = full_pipeline_batch
        build_index(store_root, batch_id)
        engine = QueryEngine(store_root, use_cache=True)

        def queries():
            results = []
            for task_id in ["01_parse", "02_analyze", "03_symbols", "04_lint"]:
                results.append(engine.query_outputs(batch_id, task_id))
            return results

        result = benchmark(queries)
        engine.close()
        assert len(result) == 4
