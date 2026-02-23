"""Tests for the Content-Addressed Storage (CAS) object store."""

import pytest
from pathlib import Path
import hashlib

from codebatch.cas import ObjectStore, ObjectNotFoundError


@pytest.fixture
def store(tmp_path: Path) -> ObjectStore:
    """Create a temporary object store."""
    return ObjectStore(tmp_path)


class TestObjectStore:
    """Tests for ObjectStore."""

    def test_put_and_get_roundtrip(self, store: ObjectStore):
        """Test that put_bytes and get_bytes round-trip correctly."""
        data = b"Hello, World!"
        object_ref = store.put_bytes(data)

        # Verify the hash is correct and uses sha256: prefix
        expected_hash = hashlib.sha256(data).hexdigest()
        assert object_ref == f"sha256:{expected_hash}"

        # Verify we can get it back
        retrieved = store.get_bytes(object_ref)
        assert retrieved == data

    def test_dedupe_same_bytes_same_ref(self, store: ObjectStore):
        """Test that same bytes produce same reference (deduplication)."""
        data = b"Duplicate content"

        ref1 = store.put_bytes(data)
        ref2 = store.put_bytes(data)

        assert ref1 == ref2

    def test_has_returns_true_for_existing(self, store: ObjectStore):
        """Test has() returns True for existing objects."""
        data = b"Test data"
        object_ref = store.put_bytes(data)

        assert store.has(object_ref) is True

    def test_has_returns_false_for_missing(self, store: ObjectStore):
        """Test has() returns False for missing objects."""
        fake_ref = "sha256:" + "a" * 64
        assert store.has(fake_ref) is False

    def test_get_missing_object_raises(self, store: ObjectStore):
        """Test get_bytes raises ObjectNotFoundError for missing objects."""
        fake_ref = "sha256:" + "b" * 64

        with pytest.raises(ObjectNotFoundError) as exc_info:
            store.get_bytes(fake_ref)

        assert exc_info.value.object_ref == fake_ref

    def test_directory_sharding(self, store: ObjectStore):
        """Test objects are stored with proper directory sharding."""
        data = b"Sharding test"
        object_ref = store.put_bytes(data)

        # Verify directory structure - extract hex hash from sha256:<hex>
        hex_hash = object_ref.split(":")[1]
        aa = hex_hash[:2]
        bb = hex_hash[2:4]
        expected_path = store.objects_dir / aa / bb / hex_hash

        assert expected_path.exists()

    def test_empty_bytes(self, store: ObjectStore):
        """Test storing empty bytes."""
        data = b""
        object_ref = store.put_bytes(data)

        # SHA-256 of empty string is well-known
        expected = (
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        assert object_ref == expected
        assert store.get_bytes(object_ref) == data

    def test_large_binary_data(self, store: ObjectStore):
        """Test storing larger binary data."""
        # 1MB of random-ish data
        data = bytes(range(256)) * 4096
        object_ref = store.put_bytes(data)

        retrieved = store.get_bytes(object_ref)
        assert retrieved == data

    def test_invalid_object_ref_raises(self, store: ObjectStore):
        """Test that invalid object refs raise ValueError."""
        with pytest.raises(ValueError):
            store._object_path("too_short")

        with pytest.raises(ValueError):
            store._object_path("x" * 65)  # too long

    def test_get_path_returns_path_for_existing(self, store: ObjectStore):
        """Test get_path returns path for existing objects."""
        data = b"Path test"
        object_ref = store.put_bytes(data)

        path = store.get_path(object_ref)
        assert path is not None
        assert path.exists()

    def test_get_path_returns_none_for_missing(self, store: ObjectStore):
        """Test get_path returns None for missing objects."""
        fake_ref = "sha256:" + "c" * 64
        assert store.get_path(fake_ref) is None
