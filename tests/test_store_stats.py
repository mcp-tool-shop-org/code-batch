"""Tests for the store-stats command."""

from pathlib import Path

from codebatch.cli import get_store_stats, _dir_size, _format_size
from codebatch.store import init_store


def test_dir_size_empty(tmp_path: Path) -> None:
    """Empty directory returns zero."""
    d = tmp_path / "empty"
    d.mkdir()
    size, count = _dir_size(d)
    assert size == 0
    assert count == 0


def test_dir_size_with_files(tmp_path: Path) -> None:
    """Directory with files returns correct totals."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("hello")
    (d / "b.txt").write_text("world!")
    size, count = _dir_size(d)
    assert count == 2
    assert size == 5 + 6  # "hello" + "world!"


def test_dir_size_nonexistent(tmp_path: Path) -> None:
    """Non-existent directory returns zero."""
    size, count = _dir_size(tmp_path / "nope")
    assert size == 0
    assert count == 0


def test_format_size_bytes() -> None:
    assert _format_size(0) == "0 B"
    assert _format_size(512) == "512 B"


def test_format_size_kb() -> None:
    assert _format_size(1024) == "1.0 KB"
    assert _format_size(2048) == "2.0 KB"


def test_format_size_mb() -> None:
    assert _format_size(1024 * 1024) == "1.0 MB"


def test_get_store_stats_fresh_store(tmp_path: Path) -> None:
    """Fresh store has minimal size and correct structure."""
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    stats = get_store_stats(store)

    assert stats["store"] == str(store)
    assert "breakdown" in stats
    assert set(stats["breakdown"].keys()) == {"objects", "snapshots", "batches", "indexes"}
    assert stats["total_files"] >= 1  # at least store.json
    assert stats["total_bytes"] > 0  # store.json has content


def test_get_store_stats_json_flag(tmp_path: Path) -> None:
    """Stats dict is JSON-serializable."""
    import json

    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    stats = get_store_stats(store)
    # Should not raise
    output = json.dumps(stats)
    assert "total_bytes" in output


def test_get_store_stats_with_data(tmp_path: Path) -> None:
    """Store with data in subdirs reports correct counts."""
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    # Add some fake data to batches
    batch_dir = store / "batches" / "test-batch"
    batch_dir.mkdir(parents=True)
    (batch_dir / "plan.json").write_text('{"tasks": []}')

    stats = get_store_stats(store)
    assert stats["breakdown"]["batches"]["files"] == 1
    assert stats["breakdown"]["batches"]["bytes"] == len('{"tasks": []}')
