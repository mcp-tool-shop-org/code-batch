"""Tests for snapshot builder."""

import json
import pytest
from pathlib import Path

from codebatch.snapshot import SnapshotBuilder, generate_snapshot_id, detect_lang_hint


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """Create a temporary store root."""
    return tmp_path / "store"


@pytest.fixture
def corpus_dir() -> Path:
    """Get the test corpus directory."""
    return Path(__file__).parent / "fixtures" / "corpus"


class TestSnapshotBuilder:
    """Tests for SnapshotBuilder."""

    def test_build_creates_snapshot(self, store: Path, corpus_dir: Path):
        """Building a snapshot creates the expected files."""
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus_dir)

        # Check snapshot directory exists
        snapshot_dir = store / "snapshots" / snapshot_id
        assert snapshot_dir.exists()

        # Check files exist
        assert (snapshot_dir / "snapshot.json").exists()
        assert (snapshot_dir / "files.index.jsonl").exists()

    def test_build_deterministic_ordering(self, store: Path, corpus_dir: Path):
        """File index is sorted by path_key."""
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus_dir)

        records = builder.load_file_index(snapshot_id)
        path_keys = [r["path_key"] for r in records]

        assert path_keys == sorted(path_keys)

    def test_build_stores_objects_in_cas(self, store: Path, corpus_dir: Path):
        """Files are stored in the CAS."""
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus_dir)

        records = builder.load_file_index(snapshot_id)
        for record in records:
            obj_ref = record["object"]
            assert builder.object_store.has(obj_ref)

    def test_build_custom_id(self, store: Path, corpus_dir: Path):
        """Can specify a custom snapshot ID."""
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus_dir, snapshot_id="my-custom-id")

        assert snapshot_id == "my-custom-id"
        assert (store / "snapshots" / "my-custom-id" / "snapshot.json").exists()

    def test_build_with_metadata(self, store: Path, corpus_dir: Path):
        """Can include custom metadata."""
        builder = SnapshotBuilder(store)
        metadata = {"description": "Test snapshot", "version": 1}
        snapshot_id = builder.build(corpus_dir, metadata=metadata)

        snapshot = builder.load_snapshot(snapshot_id)
        assert snapshot["metadata"] == metadata

    def test_snapshot_contains_correct_counts(self, store: Path, corpus_dir: Path):
        """Snapshot metadata has correct file count and total bytes."""
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus_dir)

        snapshot = builder.load_snapshot(snapshot_id)
        records = builder.load_file_index(snapshot_id)

        assert snapshot["file_count"] == len(records)
        assert snapshot["total_bytes"] == sum(r["size"] for r in records)

    def test_list_snapshots(self, store: Path, corpus_dir: Path):
        """Can list all snapshots."""
        builder = SnapshotBuilder(store)

        id1 = builder.build(corpus_dir, snapshot_id="snap-1")
        id2 = builder.build(corpus_dir, snapshot_id="snap-2")

        snapshots = builder.list_snapshots()
        assert set(snapshots) == {"snap-1", "snap-2"}

    def test_lang_hint_detection(self, store: Path, corpus_dir: Path):
        """Language hints are detected for known extensions."""
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus_dir)

        records = builder.load_file_index(snapshot_id)
        records_by_path = {r["path"]: r for r in records}

        # Python file should have lang_hint
        assert records_by_path["hello.py"].get("lang_hint") == "python"

        # Binary file should not have lang_hint
        assert "lang_hint" not in records_by_path["binary.bin"]


class TestGenerateSnapshotId:
    """Tests for generate_snapshot_id."""

    def test_format(self):
        """Snapshot ID has expected format."""
        snapshot_id = generate_snapshot_id()
        assert snapshot_id.startswith("snap-")
        parts = snapshot_id.split("-")
        assert len(parts) == 4  # snap, date, time, suffix

    def test_unique(self):
        """Generated IDs are unique."""
        ids = {generate_snapshot_id() for _ in range(100)}
        assert len(ids) == 100


class TestDetectLangHint:
    """Tests for detect_lang_hint."""

    def test_known_extensions(self):
        """Known extensions return correct hints."""
        assert detect_lang_hint("main.py") == "python"
        assert detect_lang_hint("app.ts") == "typescript"
        assert detect_lang_hint("Program.cs") == "csharp"
        assert detect_lang_hint("main.go") == "go"

    def test_unknown_extensions(self):
        """Unknown extensions return None."""
        assert detect_lang_hint("file.xyz") is None
        assert detect_lang_hint("file.bin") is None
        assert detect_lang_hint("file") is None

    def test_case_insensitive(self):
        """Extension detection is case insensitive."""
        assert detect_lang_hint("main.PY") == "python"
        assert detect_lang_hint("app.TS") == "typescript"
