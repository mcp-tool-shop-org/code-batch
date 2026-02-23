"""Tests for store initialization and validation."""

import pytest
from pathlib import Path

from codebatch.store import (
    init_store,
    load_store,
    ensure_store,
    is_valid_store,
    StoreExistsError,
    InvalidStoreError,
)


@pytest.fixture
def store_root(tmp_path: Path) -> Path:
    """Create a temporary store root path."""
    return tmp_path / "store"


class TestInitStore:
    """Tests for init_store."""

    def test_init_creates_structure(self, store_root: Path):
        """Init creates correct directory structure."""
        store_meta = init_store(store_root)

        assert store_root.exists()
        assert (store_root / "store.json").exists()
        assert (store_root / "objects" / "sha256").is_dir()
        assert (store_root / "snapshots").is_dir()
        assert (store_root / "batches").is_dir()

        # Verify store.json content
        assert store_meta["schema_name"] == "codebatch.store"
        assert isinstance(store_meta["schema_version"], int)
        assert store_meta["schema_version"] >= 1
        assert "producer" in store_meta
        assert "created_at" in store_meta

    def test_init_existing_raises(self, store_root: Path):
        """Init raises if store already exists."""
        init_store(store_root)

        with pytest.raises(StoreExistsError):
            init_store(store_root)

    def test_init_non_empty_dir_raises(self, store_root: Path):
        """Init raises if directory is non-empty."""
        store_root.mkdir(parents=True)
        (store_root / "something.txt").write_text("data")

        with pytest.raises(StoreExistsError):
            init_store(store_root)

    def test_init_empty_dir_succeeds(self, store_root: Path):
        """Init succeeds on empty directory."""
        store_root.mkdir(parents=True)

        store_meta = init_store(store_root)
        assert store_meta["schema_name"] == "codebatch.store"


class TestLoadStore:
    """Tests for load_store."""

    def test_load_valid_store(self, store_root: Path):
        """Load returns metadata for valid store."""
        init_store(store_root)
        store_meta = load_store(store_root)

        assert store_meta["schema_name"] == "codebatch.store"
        assert isinstance(store_meta["schema_version"], int)

    def test_load_missing_raises(self, store_root: Path):
        """Load raises for non-existent directory."""
        with pytest.raises(InvalidStoreError, match="does not exist"):
            load_store(store_root)

    def test_load_no_store_json_raises(self, store_root: Path):
        """Load raises if store.json is missing."""
        store_root.mkdir(parents=True)

        with pytest.raises(InvalidStoreError, match="missing store.json"):
            load_store(store_root)

    def test_load_invalid_json_raises(self, store_root: Path):
        """Load raises for invalid JSON."""
        store_root.mkdir(parents=True)
        (store_root / "store.json").write_text("{invalid")

        with pytest.raises(InvalidStoreError, match="invalid JSON"):
            load_store(store_root)

    def test_load_wrong_schema_name_raises(self, store_root: Path):
        """Load raises for wrong schema_name."""
        store_root.mkdir(parents=True)
        (store_root / "store.json").write_text(
            '{"schema_name": "wrong", "schema_version": 1}'
        )

        with pytest.raises(InvalidStoreError, match="invalid schema_name"):
            load_store(store_root)


class TestEnsureStore:
    """Tests for ensure_store."""

    def test_ensure_creates_new(self, store_root: Path):
        """Ensure creates new store if not exists."""
        store_meta = ensure_store(store_root)

        assert store_meta["schema_name"] == "codebatch.store"
        assert (store_root / "store.json").exists()

    def test_ensure_returns_existing(self, store_root: Path):
        """Ensure returns existing store metadata."""
        original = init_store(store_root)
        loaded = ensure_store(store_root)

        assert loaded["created_at"] == original["created_at"]


class TestIsValidStore:
    """Tests for is_valid_store."""

    def test_valid_store(self, store_root: Path):
        """Returns True for valid store."""
        init_store(store_root)
        assert is_valid_store(store_root) is True

    def test_non_existent(self, store_root: Path):
        """Returns False for non-existent path."""
        assert is_valid_store(store_root) is False

    def test_empty_dir(self, store_root: Path):
        """Returns False for empty directory."""
        store_root.mkdir(parents=True)
        assert is_valid_store(store_root) is False
