"""Common utilities and constants for CodeBatch.

This module defines contract-level constants and helpers used across all components.
"""

from datetime import datetime, timezone
from typing import Tuple

# Schema version as integer per contract
SCHEMA_VERSION = 1

# Producer info - identifies the implementation that created records
PRODUCER = {
    "name": "codebatch",
    "version": "0.1.0",
}


def utc_now_z() -> str:
    """Return current UTC time in RFC3339 format with Z suffix.

    Returns:
        ISO8601/RFC3339 timestamp ending in Z (e.g., "2025-02-02T12:00:00Z").
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_object_ref(object_ref: str) -> Tuple[str, str]:
    """Parse an object reference into algorithm and hex hash.

    Args:
        object_ref: Object reference in format "sha256:<hex>" or bare hex.

    Returns:
        Tuple of (algorithm, hex_hash).

    Raises:
        ValueError: If format is invalid.
    """
    if ":" in object_ref:
        parts = object_ref.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid object ref format: {object_ref}")
        algo, hex_hash = parts
        if algo != "sha256":
            raise ValueError(f"Unsupported algorithm: {algo}")
    else:
        # Legacy bare hex format
        algo = "sha256"
        hex_hash = object_ref

    # Validate hex
    if len(hex_hash) != 64:
        raise ValueError(f"Invalid hash length: {len(hex_hash)} (expected 64)")

    try:
        int(hex_hash, 16)
    except ValueError:
        raise ValueError(f"Invalid hex characters in hash: {hex_hash}")

    return algo, hex_hash


def make_object_ref(hex_hash: str) -> str:
    """Create a canonical object reference from a hex hash.

    Args:
        hex_hash: SHA-256 hex hash (64 characters).

    Returns:
        Canonical object reference in format "sha256:<hex>".
    """
    if len(hex_hash) != 64:
        raise ValueError(f"Invalid hash length: {len(hex_hash)}")
    return f"sha256:{hex_hash}"


def object_shard_prefix(object_ref: str) -> str:
    """Get the shard prefix (first byte hex) from an object reference.

    Args:
        object_ref: Object reference (sha256:<hex> or bare hex).

    Returns:
        Two-character hex string (e.g., "ab").
    """
    _, hex_hash = parse_object_ref(object_ref)
    return hex_hash[:2]


class SnapshotExistsError(Exception):
    """Raised when attempting to create a snapshot that already exists."""

    def __init__(self, snapshot_id: str):
        self.snapshot_id = snapshot_id
        super().__init__(f"Snapshot already exists: {snapshot_id}")


class BatchExistsError(Exception):
    """Raised when attempting to create a batch that already exists."""

    def __init__(self, batch_id: str):
        self.batch_id = batch_id
        super().__init__(f"Batch already exists: {batch_id}")
