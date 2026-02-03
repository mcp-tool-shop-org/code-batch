"""Tests for batch management."""

import pytest
from pathlib import Path

from codebatch.batch import BatchManager, generate_batch_id, PIPELINES
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


class TestBatchManager:
    """Tests for BatchManager."""

    def test_init_batch_creates_structure(self, store: Path, snapshot_id: str):
        """Initializing a batch creates the complete directory structure."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse")

        batch_dir = store / "batches" / batch_id

        # Check batch-level files
        assert (batch_dir / "batch.json").exists()
        assert (batch_dir / "plan.json").exists()
        assert (batch_dir / "events.jsonl").exists()

        # Check task structure
        task_dir = batch_dir / "tasks" / "01_parse"
        assert (task_dir / "task.json").exists()
        assert (task_dir / "events.jsonl").exists()

        # Check shards (256 of them)
        shards_dir = task_dir / "shards"
        assert shards_dir.exists()
        shard_dirs = list(shards_dir.iterdir())
        assert len(shard_dirs) == 256

        # Check each shard has state.json and outputs.index.jsonl
        for shard_dir in shard_dirs:
            assert (shard_dir / "state.json").exists()
            assert (shard_dir / "outputs.index.jsonl").exists()

    def test_init_batch_custom_id(self, store: Path, snapshot_id: str):
        """Can specify a custom batch ID."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse", batch_id="my-batch")

        assert batch_id == "my-batch"
        assert (store / "batches" / "my-batch" / "batch.json").exists()

    def test_init_batch_invalid_snapshot(self, store: Path):
        """Initializing with invalid snapshot raises ValueError."""
        store.mkdir(parents=True, exist_ok=True)
        manager = BatchManager(store)

        with pytest.raises(ValueError, match="Snapshot not found"):
            manager.init_batch("nonexistent-snapshot", "parse")

    def test_init_batch_invalid_pipeline(self, store: Path, snapshot_id: str):
        """Initializing with invalid pipeline raises ValueError."""
        manager = BatchManager(store)

        with pytest.raises(ValueError, match="Unknown pipeline"):
            manager.init_batch(snapshot_id, "nonexistent-pipeline")

    def test_load_batch(self, store: Path, snapshot_id: str):
        """Can load batch metadata."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse")

        batch = manager.load_batch(batch_id)

        assert batch["batch_id"] == batch_id
        assert batch["snapshot_id"] == snapshot_id
        assert batch["pipeline"] == "parse"
        assert batch["status"] == "pending"

    def test_load_plan(self, store: Path, snapshot_id: str):
        """Can load batch plan."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse")

        plan = manager.load_plan(batch_id)

        assert plan["batch_id"] == batch_id
        assert len(plan["tasks"]) == 1
        assert plan["tasks"][0]["task_id"] == "01_parse"

    def test_load_task(self, store: Path, snapshot_id: str):
        """Can load task metadata."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse")

        task = manager.load_task(batch_id, "01_parse")

        assert task["task_id"] == "01_parse"
        assert task["batch_id"] == batch_id
        assert task["type"] == "parse"
        assert task["sharding"]["shard_count"] == 256

    def test_load_shard_state(self, store: Path, snapshot_id: str):
        """Can load shard state."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse")

        state = manager.load_shard_state(batch_id, "01_parse", "ab")

        assert state["shard_id"] == "ab"
        assert state["task_id"] == "01_parse"
        assert state["batch_id"] == batch_id
        assert state["status"] == "ready"
        assert state["attempt"] == 0

    def test_list_batches(self, store: Path, snapshot_id: str):
        """Can list all batches."""
        manager = BatchManager(store)

        id1 = manager.init_batch(snapshot_id, "parse", batch_id="batch-1")
        id2 = manager.init_batch(snapshot_id, "parse", batch_id="batch-2")

        batches = manager.list_batches()
        assert set(batches) == {"batch-1", "batch-2"}

    def test_get_task_ids(self, store: Path, snapshot_id: str):
        """Can get task IDs for a batch."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "parse")

        task_ids = manager.get_task_ids(batch_id)
        assert task_ids == ["01_parse"]

    def test_analyze_pipeline_creates_two_tasks(self, store: Path, snapshot_id: str):
        """Analyze pipeline creates two tasks with dependency."""
        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "analyze")

        task_ids = manager.get_task_ids(batch_id)
        assert set(task_ids) == {"01_parse", "02_analyze"}

        # Check dependency
        analyze_task = manager.load_task(batch_id, "02_analyze")
        assert analyze_task["inputs"]["tasks"] == ["01_parse"]


class TestGenerateBatchId:
    """Tests for generate_batch_id."""

    def test_format(self):
        """Batch ID has expected format."""
        batch_id = generate_batch_id()
        assert batch_id.startswith("batch-")
        parts = batch_id.split("-")
        assert len(parts) == 4  # batch, date, time, suffix

    def test_unique(self):
        """Generated IDs are unique."""
        ids = {generate_batch_id() for _ in range(100)}
        assert len(ids) == 100
