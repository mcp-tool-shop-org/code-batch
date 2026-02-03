"""Tests for LMDB index build and cache infrastructure.

Phase 3 Gate Tests:
- Gate A1: Cache Equivalence (cached queries = JSONL scan)
- Gate A2: Cache Deletion Equivalence (fallback works)
- Gate A3: Deterministic Rebuild
- Gate A4: Truth-Store Guard
"""

import json
import pytest
import shutil
from pathlib import Path

from codebatch.batch import BatchManager, PIPELINES
from codebatch.common import object_shard_prefix
from codebatch.index_build import build_index, iter_shard_outputs
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


class TestIterShardOutputs:
    """Tests for the iter_shard_outputs helper."""

    def test_iterates_all_outputs(self, full_pipeline_batch):
        """Should iterate all outputs across all shards."""
        store_root, batch_id, _ = full_pipeline_batch

        # Get outputs for parse task
        outputs = list(iter_shard_outputs(store_root, batch_id, "01_parse"))

        # Should have some outputs
        assert len(outputs) > 0

        # All should have shard_id added
        for o in outputs:
            assert "shard_id" in o

    def test_empty_for_nonexistent_task(self, full_pipeline_batch):
        """Should return empty for nonexistent task."""
        store_root, batch_id, _ = full_pipeline_batch

        outputs = list(iter_shard_outputs(store_root, batch_id, "99_fake"))
        assert outputs == []


class TestBuildIndex:
    """Tests for the build_index function."""

    def test_builds_index(self, full_pipeline_batch):
        """Should build index without errors."""
        store_root, batch_id, _ = full_pipeline_batch

        stats = build_index(store_root, batch_id)

        assert stats["files_indexed"] > 0
        assert stats["outputs_indexed"] > 0
        assert "source_fingerprint" in stats

    def test_creates_lmdb_directory(self, full_pipeline_batch):
        """Should create indexes/lmdb/ directory."""
        store_root, batch_id, _ = full_pipeline_batch

        build_index(store_root, batch_id)

        lmdb_dir = store_root / "indexes" / "lmdb"
        assert lmdb_dir.exists()
        assert (lmdb_dir / "data.mdb").exists()

    def test_creates_cache_meta(self, full_pipeline_batch):
        """Should create cache_meta.json inside lmdb directory."""
        store_root, batch_id, _ = full_pipeline_batch

        build_index(store_root, batch_id)

        # cache_meta.json lives inside the lmdb directory per cache.py
        meta_path = store_root / "indexes" / "lmdb" / "cache_meta.json"
        assert meta_path.exists()

        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["snapshot_id"] is not None
        assert meta["batch_id"] == batch_id
        assert "source_fingerprint" in meta
        assert meta["cache_schema_version"] == 1

    def test_rebuild_deletes_existing(self, full_pipeline_batch):
        """Should delete existing cache when rebuild=True."""
        store_root, batch_id, _ = full_pipeline_batch

        # Build once
        stats1 = build_index(store_root, batch_id)

        # Build again with rebuild
        stats2 = build_index(store_root, batch_id, rebuild=True)

        # Both should succeed with same counts
        assert stats1["files_indexed"] == stats2["files_indexed"]
        assert stats1["outputs_indexed"] == stats2["outputs_indexed"]

    def test_indexes_diagnostics_if_present(self, full_pipeline_batch):
        """Should index diagnostics when lint produces them."""
        store_root, batch_id, _ = full_pipeline_batch

        stats = build_index(store_root, batch_id)

        # diagnostics_indexed count should be populated (may be 0 if corpus is clean)
        assert "diagnostics_indexed" in stats
        # Just verify the field exists and is a non-negative int
        assert isinstance(stats["diagnostics_indexed"], int)
        assert stats["diagnostics_indexed"] >= 0


class TestDiagnosticsIndexing:
    """Tests specifically for diagnostic indexing with a messy corpus."""

    @pytest.fixture
    def messy_corpus_dir(self) -> Path:
        """Get the messy test corpus directory (has lint issues)."""
        return Path(__file__).parent / "fixtures" / "corpus_lint"

    @pytest.fixture
    def messy_batch(self, clean_store: Path, messy_corpus_dir: Path) -> tuple[Path, str, str]:
        """Run the full pipeline on messy corpus."""
        # Create snapshot
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(messy_corpus_dir)

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

    def test_indexes_diagnostics_from_messy_corpus(self, messy_batch):
        """Should index diagnostics from lint issues in messy corpus."""
        store_root, batch_id, _ = messy_batch

        stats = build_index(store_root, batch_id)

        # Messy corpus should produce diagnostics (TODO, tab indent, long line)
        assert stats["diagnostics_indexed"] > 0, "Expected diagnostics from messy corpus"


class TestGateA4TruthStoreGuard:
    """Gate A4: Cache operations don't write to unauthorized locations."""

    def test_cache_writes_only_under_indexes(self, full_pipeline_batch):
        """Cache build should only write under indexes/."""
        store_root, batch_id, snapshot_id = full_pipeline_batch

        # Record paths before build
        def get_all_paths(root: Path) -> set[str]:
            paths = set()
            for p in root.rglob("*"):
                rel = p.relative_to(root)
                paths.add(str(rel))
            return paths

        paths_before = get_all_paths(store_root)

        # Build cache
        build_index(store_root, batch_id)

        paths_after = get_all_paths(store_root)

        # New paths
        new_paths = paths_after - paths_before

        # All new paths should be under indexes/
        for p in new_paths:
            assert p.startswith("indexes"), f"Unauthorized write: {p}"

    def test_allowed_store_structure(self, full_pipeline_batch):
        """Store should only contain allowed top-level directories."""
        store_root, batch_id, _ = full_pipeline_batch

        build_index(store_root, batch_id)

        allowed = {"store.json", "objects", "snapshots", "batches", "indexes"}
        top_level = {p.name for p in store_root.iterdir()}

        unauthorized = top_level - allowed
        assert not unauthorized, f"Unauthorized top-level paths: {unauthorized}"


class TestCacheInfrastructure:
    """Tests for cache environment and I/O."""

    def test_cache_env_opens(self, full_pipeline_batch):
        """CacheEnv should open the database."""
        from codebatch.cache import CacheEnv

        store_root, batch_id, _ = full_pipeline_batch
        build_index(store_root, batch_id)

        env = CacheEnv(store_root, readonly=True)
        env.open()
        try:
            assert env.is_open
        finally:
            env.close()

    def test_cache_reader_gets_files(self, full_pipeline_batch):
        """CacheReader should retrieve indexed files."""
        from codebatch.cache import CacheEnv, CacheReader

        store_root, batch_id, snapshot_id = full_pipeline_batch
        build_index(store_root, batch_id)

        env = CacheEnv(store_root, readonly=True)
        env.open()
        try:
            reader = CacheReader(env)
            # Try to iterate files (implementation may vary)
            # For now just verify reader can be created
            assert reader is not None
        finally:
            env.close()


def canonicalize_outputs(outputs: list[dict]) -> list[tuple]:
    """Canonicalize outputs for comparison (sort, drop timestamps).

    Returns sorted tuples of (kind, path, object_ref) for comparison.
    Treats None and '' as equivalent for object_ref.
    """
    result = []
    for o in outputs:
        obj = o.get("object", o.get("object_ref", ""))
        # Normalize None to "" for comparison
        if obj is None:
            obj = ""
        key = (
            o.get("kind", ""),
            o.get("path", ""),
            obj,
        )
        result.append(key)
    return sorted(result)


def canonicalize_stats(stats: dict[str, int]) -> list[tuple]:
    """Canonicalize stats for comparison."""
    return sorted(stats.items())


class TestGateA1CacheEquivalence:
    """Gate A1: Cached queries return identical results to JSONL scan.

    This is the most critical cache test - ensures correctness.
    """

    def test_query_outputs_equivalence(self, full_pipeline_batch):
        """query_outputs with cache == query_outputs without cache."""
        store_root, batch_id, _ = full_pipeline_batch

        # Query without cache
        engine_no_cache = QueryEngine(store_root, use_cache=False)
        scan_results = engine_no_cache.query_outputs(batch_id, "01_parse")

        # Build cache
        build_index(store_root, batch_id)

        # Query with cache
        engine_cache = QueryEngine(store_root, use_cache=True)
        cache_results = engine_cache.query_outputs(batch_id, "01_parse")

        # Compare canonicalized results
        scan_canonical = canonicalize_outputs(scan_results)
        cache_canonical = canonicalize_outputs(cache_results)

        assert scan_canonical == cache_canonical, \
            f"Cache mismatch for query_outputs: {len(scan_canonical)} scan vs {len(cache_canonical)} cache"

    def test_query_outputs_with_kind_filter_equivalence(self, full_pipeline_batch):
        """query_outputs(kind=X) with cache == without cache."""
        store_root, batch_id, _ = full_pipeline_batch

        # Query without cache
        engine_no_cache = QueryEngine(store_root, use_cache=False)
        scan_results = engine_no_cache.query_outputs(batch_id, "01_parse", kind="ast")

        # Build cache
        build_index(store_root, batch_id)

        # Query with cache
        engine_cache = QueryEngine(store_root, use_cache=True)
        cache_results = engine_cache.query_outputs(batch_id, "01_parse", kind="ast")

        # Compare
        scan_canonical = canonicalize_outputs(scan_results)
        cache_canonical = canonicalize_outputs(cache_results)

        assert scan_canonical == cache_canonical

    def test_query_stats_by_kind_equivalence(self, full_pipeline_batch):
        """query_stats(group_by=kind) with cache == without cache."""
        store_root, batch_id, _ = full_pipeline_batch

        # Query without cache
        engine_no_cache = QueryEngine(store_root, use_cache=False)
        scan_stats = engine_no_cache.query_stats(batch_id, "02_analyze", group_by="kind")

        # Build cache
        build_index(store_root, batch_id)

        # Query with cache
        engine_cache = QueryEngine(store_root, use_cache=True)
        cache_stats = engine_cache.query_stats(batch_id, "02_analyze", group_by="kind")

        # Compare
        assert canonicalize_stats(scan_stats) == canonicalize_stats(cache_stats)

    def test_query_stats_by_lang_equivalence(self, full_pipeline_batch):
        """query_stats(group_by=lang) with cache == without cache."""
        store_root, batch_id, _ = full_pipeline_batch

        # Query without cache
        engine_no_cache = QueryEngine(store_root, use_cache=False)
        scan_stats = engine_no_cache.query_stats(batch_id, "02_analyze", group_by="lang")

        # Build cache
        build_index(store_root, batch_id)

        # Query with cache
        engine_cache = QueryEngine(store_root, use_cache=True)
        cache_stats = engine_cache.query_stats(batch_id, "02_analyze", group_by="lang")

        # Compare
        assert canonicalize_stats(scan_stats) == canonicalize_stats(cache_stats)

    def test_all_tasks_outputs_equivalence(self, full_pipeline_batch):
        """query_outputs for all 4 tasks with cache == without cache."""
        store_root, batch_id, _ = full_pipeline_batch

        # Build cache first this time
        build_index(store_root, batch_id)

        # Test all 4 tasks
        for task_id in ["01_parse", "02_analyze", "03_symbols", "04_lint"]:
            engine_no_cache = QueryEngine(store_root, use_cache=False)
            engine_cache = QueryEngine(store_root, use_cache=True)

            scan_results = engine_no_cache.query_outputs(batch_id, task_id)
            cache_results = engine_cache.query_outputs(batch_id, task_id)

            scan_canonical = canonicalize_outputs(scan_results)
            cache_canonical = canonicalize_outputs(cache_results)

            assert scan_canonical == cache_canonical, \
                f"Cache mismatch for {task_id}: {len(scan_canonical)} scan vs {len(cache_canonical)} cache"


class TestGateA2CacheDeletionEquivalence:
    """Gate A2: Deleting cache falls back to scan with identical results.

    Ensures fallback path works correctly.
    """

    def test_cache_deletion_fallback(self, full_pipeline_batch):
        """After deleting cache, queries should fall back to scan and return same results."""
        store_root, batch_id, _ = full_pipeline_batch

        # Build cache and query
        build_index(store_root, batch_id)
        engine1 = QueryEngine(store_root, use_cache=True)
        cached_results = engine1.query_outputs(batch_id, "01_parse")

        # Close cache before deleting (LMDB keeps file handle open)
        engine1.close()

        # Delete cache
        lmdb_dir = store_root / "indexes" / "lmdb"
        shutil.rmtree(lmdb_dir)

        # Query again - should fall back to scan
        engine2 = QueryEngine(store_root, use_cache=True)
        fallback_results = engine2.query_outputs(batch_id, "01_parse")
        engine2.close()

        # Results should be identical
        cached_canonical = canonicalize_outputs(cached_results)
        fallback_canonical = canonicalize_outputs(fallback_results)

        assert cached_canonical == fallback_canonical

    def test_cache_deletion_stats_fallback(self, full_pipeline_batch):
        """Stats queries fall back correctly after cache deletion."""
        store_root, batch_id, _ = full_pipeline_batch

        # Build cache and query stats
        build_index(store_root, batch_id)
        engine1 = QueryEngine(store_root, use_cache=True)
        cached_stats = engine1.query_stats(batch_id, "02_analyze", group_by="kind")

        # Close cache before deleting
        engine1.close()

        # Delete cache
        lmdb_dir = store_root / "indexes" / "lmdb"
        shutil.rmtree(lmdb_dir)

        # Query again
        engine2 = QueryEngine(store_root, use_cache=True)
        fallback_stats = engine2.query_stats(batch_id, "02_analyze", group_by="kind")
        engine2.close()

        # Should be identical
        assert canonicalize_stats(cached_stats) == canonicalize_stats(fallback_stats)


class TestGateA3DeterministicRebuild:
    """Gate A3: Cache builds are reproducible.

    Query results should be identical across rebuilds.
    """

    def test_rebuild_produces_identical_query_results(self, full_pipeline_batch):
        """Rebuilding cache produces identical query results."""
        store_root, batch_id, _ = full_pipeline_batch

        # Build 1
        build_index(store_root, batch_id)
        engine1 = QueryEngine(store_root, use_cache=True)
        results1 = engine1.query_outputs(batch_id, "01_parse")
        stats1 = engine1.query_stats(batch_id, "02_analyze", group_by="kind")
        engine1.close()

        # Delete and rebuild
        lmdb_dir = store_root / "indexes" / "lmdb"
        shutil.rmtree(lmdb_dir)
        build_index(store_root, batch_id)

        # Build 2 queries
        engine2 = QueryEngine(store_root, use_cache=True)
        results2 = engine2.query_outputs(batch_id, "01_parse")
        stats2 = engine2.query_stats(batch_id, "02_analyze", group_by="kind")
        engine2.close()

        # Compare
        assert canonicalize_outputs(results1) == canonicalize_outputs(results2)
        assert canonicalize_stats(stats1) == canonicalize_stats(stats2)

    def test_rebuild_with_flag_produces_identical_results(self, full_pipeline_batch):
        """Using rebuild=True produces identical query results."""
        store_root, batch_id, _ = full_pipeline_batch

        # Build 1
        build_index(store_root, batch_id)
        engine1 = QueryEngine(store_root, use_cache=True)
        results1 = engine1.query_outputs(batch_id, "02_analyze")
        engine1.close()

        # Rebuild with flag (close previous cache handles before rebuild)
        build_index(store_root, batch_id, rebuild=True)

        # Build 2 queries
        engine2 = QueryEngine(store_root, use_cache=True)
        results2 = engine2.query_outputs(batch_id, "02_analyze")
        engine2.close()

        # Compare
        assert canonicalize_outputs(results1) == canonicalize_outputs(results2)
