"""Store initialization and validation.

A CodeBatch store is a directory with a specific layout:
    <store_root>/
      store.json       # Store metadata
      objects/         # Content-addressed objects
      snapshots/       # Frozen input state
      batches/         # Execution attempts
      indexes/         # Optional acceleration (not required for correctness)
"""

import json
from pathlib import Path
from typing import Optional

from .common import SCHEMA_VERSION, PRODUCER, utc_now_z


class StoreExistsError(Exception):
    """Raised when attempting to initialize a store that already exists."""

    def __init__(self, store_root: Path):
        self.store_root = store_root
        super().__init__(f"Store already exists: {store_root}")


class InvalidStoreError(Exception):
    """Raised when a store is missing or invalid."""

    def __init__(self, store_root: Path, reason: str):
        self.store_root = store_root
        self.reason = reason
        super().__init__(f"Invalid store at {store_root}: {reason}")


def init_store(store_root: Path, *, allow_reinit: bool = False) -> dict:
    """Initialize a new CodeBatch store.

    Creates the directory structure and store.json file.

    Args:
        store_root: Root directory for the store.
        allow_reinit: If True, allow re-initialization of existing empty store.

    Returns:
        The store metadata dict.

    Raises:
        StoreExistsError: If store already exists (and not empty or allow_reinit=False).
    """
    store_root = Path(store_root)
    store_json_path = store_root / "store.json"

    # Check if store already exists
    if store_json_path.exists():
        raise StoreExistsError(store_root)

    # If directory exists but is not a valid store, check if it's empty
    if store_root.exists():
        contents = list(store_root.iterdir())
        if contents and not allow_reinit:
            raise StoreExistsError(store_root)

    # Create directory structure
    store_root.mkdir(parents=True, exist_ok=True)
    (store_root / "objects" / "sha256").mkdir(parents=True, exist_ok=True)
    (store_root / "snapshots").mkdir(exist_ok=True)
    (store_root / "batches").mkdir(exist_ok=True)

    # Create store.json
    store_meta = {
        "schema_name": "codebatch.store",
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER.copy(),
        "created_at": utc_now_z(),
    }

    with open(store_json_path, "w", encoding="utf-8") as f:
        json.dump(store_meta, f, indent=2)
        f.write("\n")

    return store_meta


def load_store(store_root: Path) -> dict:
    """Load and validate store metadata.

    Args:
        store_root: Root directory of the store.

    Returns:
        The store metadata dict.

    Raises:
        InvalidStoreError: If store is missing or invalid.
    """
    store_root = Path(store_root)
    store_json_path = store_root / "store.json"

    if not store_root.exists():
        raise InvalidStoreError(store_root, "directory does not exist")

    if not store_json_path.exists():
        raise InvalidStoreError(store_root, "missing store.json")

    try:
        with open(store_json_path, "r", encoding="utf-8") as f:
            store_meta = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidStoreError(store_root, f"invalid JSON in store.json: {e}")

    # Validate required fields
    if store_meta.get("schema_name") != "codebatch.store":
        raise InvalidStoreError(
            store_root,
            f"invalid schema_name: {store_meta.get('schema_name')}"
        )

    if not isinstance(store_meta.get("schema_version"), int):
        raise InvalidStoreError(
            store_root,
            f"invalid schema_version: {store_meta.get('schema_version')}"
        )

    return store_meta


def ensure_store(store_root: Path) -> dict:
    """Ensure a store exists, initializing if necessary.

    This is the recommended way to get a store reference when you
    don't care if it's new or existing.

    Args:
        store_root: Root directory for the store.

    Returns:
        The store metadata dict.
    """
    store_root = Path(store_root)
    store_json_path = store_root / "store.json"

    if store_json_path.exists():
        return load_store(store_root)
    else:
        return init_store(store_root)


def is_valid_store(store_root: Path) -> bool:
    """Check if a directory is a valid CodeBatch store.

    Args:
        store_root: Root directory to check.

    Returns:
        True if valid store, False otherwise.
    """
    try:
        load_store(store_root)
        return True
    except (InvalidStoreError, FileNotFoundError):
        return False
