"""Cache metadata and fingerprinting for LMDB acceleration cache.

The cache is derived, rebuildable, never truth. Source fingerprinting
ensures we can detect when the cache is stale.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from .common import SCHEMA_VERSION, PRODUCER, utc_now_z


# Cache schema version - bump when cache format changes
CACHE_SCHEMA_VERSION = 1

# Key delimiter for LMDB keys
KEY_DELIMITER = "\x1f"  # Unit separator

# Key prefix for schema versioning
KEY_PREFIX = "v1"


@dataclass
class CacheMeta:
    """Metadata for the LMDB cache."""

    cache_schema_version: int
    snapshot_id: str
    batch_id: str
    tasks_indexed: list[str]
    source_fingerprint: str
    built_at: str
    producer: dict

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "schema_name": "codebatch.cache_meta",
            "cache_schema_version": self.cache_schema_version,
            "snapshot_id": self.snapshot_id,
            "batch_id": self.batch_id,
            "tasks_indexed": self.tasks_indexed,
            "source_fingerprint": self.source_fingerprint,
            "built_at": self.built_at,
            "producer": self.producer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CacheMeta":
        """Create from dictionary."""
        return cls(
            cache_schema_version=data["cache_schema_version"],
            snapshot_id=data["snapshot_id"],
            batch_id=data["batch_id"],
            tasks_indexed=data["tasks_indexed"],
            source_fingerprint=data["source_fingerprint"],
            built_at=data["built_at"],
            producer=data["producer"],
        )


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file's contents.

    Args:
        filepath: Path to the file.

    Returns:
        Hex-encoded SHA256 hash.
    """
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_source_fingerprint(
    store_root: Path,
    snapshot_id: str,
    batch_id: str,
    task_ids: list[str],
) -> str:
    """Compute a stable fingerprint from authoritative sources.

    The fingerprint includes:
    - Hash of snapshot files.index.jsonl
    - Hashes of all shard outputs.index.jsonl for indexed tasks

    If sources change, the fingerprint changes, invalidating the cache.

    Args:
        store_root: Root directory of the CodeBatch store.
        snapshot_id: Snapshot ID.
        batch_id: Batch ID.
        task_ids: List of task IDs to include.

    Returns:
        Hex-encoded combined fingerprint.
    """
    hasher = hashlib.sha256()

    # Include snapshot files.index.jsonl
    snapshot_index = store_root / "snapshots" / snapshot_id / "files.index.jsonl"
    if snapshot_index.exists():
        hasher.update(f"snapshot:{snapshot_id}:".encode())
        hasher.update(compute_file_hash(snapshot_index).encode())

    # Include all shard outputs for each task
    for task_id in sorted(task_ids):
        shards_dir = store_root / "batches" / batch_id / "tasks" / task_id / "shards"
        if not shards_dir.exists():
            continue

        for shard_dir in sorted(shards_dir.iterdir()):
            if not shard_dir.is_dir():
                continue
            outputs_index = shard_dir / "outputs.index.jsonl"
            if outputs_index.exists():
                hasher.update(f"outputs:{task_id}:{shard_dir.name}:".encode())
                hasher.update(compute_file_hash(outputs_index).encode())

    return hasher.hexdigest()


def make_cache_key(*parts: str) -> bytes:
    """Create a cache key from parts with delimiter.

    Args:
        *parts: Key components (will be joined with delimiter).

    Returns:
        UTF-8 encoded key bytes.
    """
    return KEY_DELIMITER.join([KEY_PREFIX] + list(parts)).encode("utf-8")


def parse_cache_key(key: bytes) -> list[str]:
    """Parse a cache key into its parts.

    Args:
        key: UTF-8 encoded key bytes.

    Returns:
        List of key components (excluding version prefix).
    """
    parts = key.decode("utf-8").split(KEY_DELIMITER)
    # Skip version prefix
    return parts[1:] if parts and parts[0] == KEY_PREFIX else parts


def encode_counter(value: int) -> bytes:
    """Encode a counter value as 8-byte big-endian.

    Args:
        value: Counter value (must be non-negative).

    Returns:
        8-byte big-endian encoded bytes.
    """
    if value < 0:
        raise ValueError(f"Counter must be non-negative: {value}")
    return value.to_bytes(8, byteorder="big")


def decode_counter(data: bytes) -> int:
    """Decode a counter value from 8-byte big-endian.

    Args:
        data: 8-byte big-endian encoded bytes.

    Returns:
        Decoded counter value.
    """
    return int.from_bytes(data, byteorder="big")


def create_cache_meta(
    snapshot_id: str,
    batch_id: str,
    task_ids: list[str],
    source_fingerprint: str,
) -> CacheMeta:
    """Create cache metadata for a new cache build.

    Args:
        snapshot_id: Snapshot ID.
        batch_id: Batch ID.
        task_ids: List of indexed task IDs.
        source_fingerprint: Source fingerprint.

    Returns:
        CacheMeta instance.
    """
    return CacheMeta(
        cache_schema_version=CACHE_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        batch_id=batch_id,
        tasks_indexed=sorted(task_ids),
        source_fingerprint=source_fingerprint,
        built_at=utc_now_z(),
        producer=PRODUCER,
    )


def is_cache_valid(
    cache_meta: CacheMeta,
    store_root: Path,
    snapshot_id: str,
    batch_id: str,
    task_ids: list[str],
) -> bool:
    """Check if cache metadata matches current sources.

    Args:
        cache_meta: Loaded cache metadata.
        store_root: Root directory of the CodeBatch store.
        snapshot_id: Expected snapshot ID.
        batch_id: Expected batch ID.
        task_ids: Expected task IDs.

    Returns:
        True if cache is valid, False if stale.
    """
    # Check schema version compatibility
    if cache_meta.cache_schema_version != CACHE_SCHEMA_VERSION:
        return False

    # Check identifiers match
    if cache_meta.snapshot_id != snapshot_id:
        return False
    if cache_meta.batch_id != batch_id:
        return False
    if set(cache_meta.tasks_indexed) != set(task_ids):
        return False

    # Check source fingerprint
    current_fingerprint = compute_source_fingerprint(
        store_root, snapshot_id, batch_id, task_ids
    )
    if cache_meta.source_fingerprint != current_fingerprint:
        return False

    return True
