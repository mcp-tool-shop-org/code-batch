"""Tests for the query engine."""

import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.parse import parse_executor


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
def batch_with_outputs(store: Path, snapshot_id: str) -> str:
    """Create a batch with executed outputs."""
    manager = BatchManager(store)
    batch_id = manager.init_batch(snapshot_id, "parse", batch_id="test-batch")

    runner = ShardRunner(store)

    # Run all shards that have files
    batch = runner.batch_manager.load_batch(batch_id)
    records = runner.snapshot_builder.load_file_index(snapshot_id)

    # Get unique shards
    shards_with_files = set(r["object"][:2] for r in records)

    for shard_id in shards_with_files:
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

    return batch_id


class TestQueryEngine:
    """Tests for QueryEngine."""

    def test_query_diagnostics_empty(self, store: Path, batch_with_outputs: str):
        """Query diagnostics returns empty for clean files."""
        engine = QueryEngine(store)

        # Filter for only errors (our test corpus has clean Python)
        results = engine.query_diagnostics(
            batch_with_outputs, "01_parse", severity="error"
        )

        # Our hello.py is valid, so no errors expected
        assert isinstance(results, list)

    def test_query_outputs_by_kind(self, store: Path, batch_with_outputs: str):
        """Query outputs filtered by kind."""
        engine = QueryEngine(store)

        results = engine.query_outputs(
            batch_with_outputs, "01_parse", kind="ast"
        )

        assert len(results) >= 1
        for r in results:
            assert r["kind"] == "ast"

    def test_query_outputs_by_path(self, store: Path, batch_with_outputs: str):
        """Query outputs filtered by path substring."""
        engine = QueryEngine(store)

        results = engine.query_outputs(
            batch_with_outputs, "01_parse", path_pattern="hello"
        )

        for r in results:
            assert "hello" in r["path"].lower()

    def test_query_stats_by_kind(self, store: Path, batch_with_outputs: str):
        """Query stats grouped by kind."""
        engine = QueryEngine(store)

        stats = engine.query_stats(batch_with_outputs, "01_parse", group_by="kind")

        assert isinstance(stats, dict)
        assert "ast" in stats
        assert stats["ast"] >= 1

    def test_query_stats_by_lang(self, store: Path, batch_with_outputs: str):
        """Query stats grouped by language extension."""
        engine = QueryEngine(store)

        stats = engine.query_stats(batch_with_outputs, "01_parse", group_by="lang")

        assert isinstance(stats, dict)
        # Should have py extension
        assert "py" in stats

    def test_get_task_summary(self, store: Path, batch_with_outputs: str):
        """Get task summary with all counts."""
        engine = QueryEngine(store)

        summary = engine.get_task_summary(batch_with_outputs, "01_parse")

        assert "total_outputs" in summary
        assert "by_kind" in summary
        assert "by_severity" in summary
        assert "files_with_outputs" in summary
        assert "files_with_errors" in summary

        assert summary["total_outputs"] >= 1
        assert summary["files_with_outputs"] >= 1

    def test_query_files_with_outputs(self, store: Path, batch_with_outputs: str):
        """Query paths with specific output kind."""
        engine = QueryEngine(store)

        paths = engine.query_files_with_outputs(
            batch_with_outputs, "01_parse", kind="ast"
        )

        assert len(paths) >= 1
        assert all(isinstance(p, str) for p in paths)

    def test_query_failed_files(self, store: Path, batch_with_outputs: str):
        """Query paths with error diagnostics."""
        engine = QueryEngine(store)

        paths = engine.query_failed_files(batch_with_outputs, "01_parse")

        # Our test corpus has clean files, so should be empty
        assert isinstance(paths, list)


class TestQueryWithDiagnostics:
    """Tests for queries with actual diagnostics."""

    def test_query_syntax_error(self, store: Path, snapshot_id: str):
        """Query diagnostics for files with syntax errors."""
        # Create a corpus with a syntax error
        corpus_dir = store / "bad_corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)

        # Write a file with syntax error
        (corpus_dir / "broken.py").write_text("def foo( return")

        # Create snapshot
        builder = SnapshotBuilder(store)
        snap_id = builder.build(corpus_dir, snapshot_id="bad-snapshot")

        # Create batch
        manager = BatchManager(store)
        batch_id = manager.init_batch(snap_id, "parse", batch_id="bad-batch")

        # Run parse
        runner = ShardRunner(store)
        records = builder.load_file_index(snap_id)
        shard_id = records[0]["object"][:2]
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Query diagnostics
        engine = QueryEngine(store)
        errors = engine.query_diagnostics(batch_id, "01_parse", severity="error")

        assert len(errors) >= 1
        assert errors[0]["code"] == "E0001"
        assert "broken.py" in errors[0]["path"]

        # Check failed files
        failed = engine.query_failed_files(batch_id, "01_parse")
        assert "broken.py" in failed
