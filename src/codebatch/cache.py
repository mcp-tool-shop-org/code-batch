"""LMDB-based acceleration cache for CodeBatch queries.

The cache is derived, rebuildable, never truth. It accelerates queries
by indexing authoritative JSONL sources into LMDB.

Environment layout:
    <store>/indexes/lmdb/
        data.mdb
        lock.mdb
        cache_meta.json
"""

import json
import shutil
from pathlib import Path
from typing import Iterator, Optional

import lmdb
import msgpack

from .cache_meta import (
    CACHE_SCHEMA_VERSION,
    CacheMeta,
    compute_source_fingerprint,
    create_cache_meta,
    is_cache_valid,
    make_cache_key,
    parse_cache_key,
    encode_counter,
    decode_counter,
)


# DBI names
DBI_META = b"meta"
DBI_FILES_BY_PATH = b"files_by_path"
DBI_OUTPUTS_BY_KIND = b"outputs_by_kind"
DBI_DIAGS_BY_SEV = b"diags_by_sev"
DBI_DIAGS_BY_CODE = b"diags_by_code"
DBI_STATS = b"stats"

# All DBIs for creation
ALL_DBIS = [
    DBI_META,
    DBI_FILES_BY_PATH,
    DBI_OUTPUTS_BY_KIND,
    DBI_DIAGS_BY_SEV,
    DBI_DIAGS_BY_CODE,
    DBI_STATS,
]

# Default LMDB map size (1GB - should be enough for most use cases)
DEFAULT_MAP_SIZE = 1024 * 1024 * 1024


class CacheEnv:
    """LMDB environment wrapper for the acceleration cache."""

    def __init__(self, store_root: Path, readonly: bool = True):
        """Initialize cache environment.

        Args:
            store_root: Root directory of the CodeBatch store.
            readonly: Open in read-only mode (default True for queries).
        """
        self.store_root = Path(store_root)
        self.cache_dir = self.store_root / "indexes" / "lmdb"
        self.meta_path = self.cache_dir / "cache_meta.json"
        self.readonly = readonly
        self._env: Optional[lmdb.Environment] = None
        self._dbis: dict[bytes, lmdb._Database] = {}

    @property
    def exists(self) -> bool:
        """Check if cache directory exists."""
        return self.cache_dir.exists() and (self.cache_dir / "data.mdb").exists()

    def open(self) -> None:
        """Open the LMDB environment."""
        if self._env is not None:
            return

        if not self.exists and self.readonly:
            raise FileNotFoundError(f"Cache not found: {self.cache_dir}")

        # Ensure directory exists for write mode
        if not self.readonly:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._env = lmdb.open(
            str(self.cache_dir),
            map_size=DEFAULT_MAP_SIZE,
            max_dbs=len(ALL_DBIS),
            readonly=self.readonly,
            create=not self.readonly,
            subdir=True,
        )

        # Open all named databases
        for dbi_name in ALL_DBIS:
            self._dbis[dbi_name] = self._env.open_db(
                dbi_name,
                create=not self.readonly,
            )

    def close(self) -> None:
        """Close the LMDB environment."""
        if self._env is not None:
            self._env.close()
            self._env = None
            self._dbis.clear()

    def __enter__(self) -> "CacheEnv":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def get_dbi(self, name: bytes) -> lmdb._Database:
        """Get a named database.

        Args:
            name: DBI name (e.g., DBI_FILES_BY_PATH).

        Returns:
            LMDB database handle.
        """
        if name not in self._dbis:
            raise ValueError(f"Unknown DBI: {name}")
        return self._dbis[name]

    @property
    def is_open(self) -> bool:
        """Check if the environment is open."""
        return self._env is not None

    @property
    def env(self) -> lmdb.Environment:
        """Get the LMDB environment."""
        if self._env is None:
            raise RuntimeError("Cache not open")
        return self._env

    def begin(self, write: bool = False) -> lmdb.Transaction:
        """Begin a transaction.

        Args:
            write: Whether this is a write transaction.

        Returns:
            LMDB transaction.
        """
        return self.env.begin(write=write)

    def load_meta(self) -> Optional[CacheMeta]:
        """Load cache metadata from file.

        Returns:
            CacheMeta if exists, None otherwise.
        """
        if not self.meta_path.exists():
            return None
        with open(self.meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CacheMeta.from_dict(data)

    def save_meta(self, meta: CacheMeta) -> None:
        """Save cache metadata to file.

        Args:
            meta: Cache metadata to save.
        """
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

    def delete(self) -> None:
        """Delete the entire cache directory."""
        self.close()
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)


class CacheWriter:
    """Writer for building the LMDB cache."""

    def __init__(self, env: CacheEnv):
        """Initialize cache writer.

        Args:
            env: Cache environment (must be opened in write mode).
        """
        self.env = env
        self._stats_counters: dict[bytes, int] = {}

    def put_file(
        self,
        snapshot_id: str,
        path: str,
        lang_hint: str,
        size: int,
        path_key: str,
        obj_prefix: str,
    ) -> None:
        """Add a file to the files_by_path index.

        Args:
            snapshot_id: Snapshot ID.
            path: File path.
            lang_hint: Language hint.
            size: File size in bytes.
            path_key: Canonical path key.
            obj_prefix: First 2 hex chars of object hash.
        """
        key = make_cache_key(snapshot_id, path)
        value = msgpack.packb({
            "lang": lang_hint,
            "size": size,
            "path_key": path_key,
            "obj_prefix": obj_prefix,
        })

        with self.env.begin(write=True) as txn:
            txn.put(key, value, db=self.env.get_dbi(DBI_FILES_BY_PATH))

    def put_output(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        kind: str,
        path: str,
        object_ref: Optional[str] = None,
        fmt: Optional[str] = None,
    ) -> None:
        """Add an output to the outputs_by_kind index.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            kind: Output kind.
            path: File path.
            object_ref: Object reference (optional).
            fmt: Format (optional).
        """
        key = make_cache_key(snapshot_id, batch_id, task_id, kind, path)
        value = msgpack.packb({
            "object": object_ref,
            "format": fmt,
        })

        with self.env.begin(write=True) as txn:
            txn.put(key, value, db=self.env.get_dbi(DBI_OUTPUTS_BY_KIND))

    def put_diagnostic(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        severity: str,
        code: str,
        path: str,
        line: int,
        col: int,
        message: str,
    ) -> None:
        """Add a diagnostic to both severity and code indexes.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            severity: Diagnostic severity.
            code: Diagnostic code.
            path: File path.
            line: Line number.
            col: Column number.
            message: Diagnostic message.
        """
        value = msgpack.packb({"message": message})

        # Index by severity
        key_sev = make_cache_key(
            snapshot_id, batch_id, task_id, severity, code, path,
            str(line), str(col)
        )

        # Index by code
        key_code = make_cache_key(
            snapshot_id, batch_id, task_id, code, severity, path,
            str(line), str(col)
        )

        with self.env.begin(write=True) as txn:
            txn.put(key_sev, value, db=self.env.get_dbi(DBI_DIAGS_BY_SEV))
            txn.put(key_code, value, db=self.env.get_dbi(DBI_DIAGS_BY_CODE))

    def increment_stat(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        group: str,
        value: str,
    ) -> None:
        """Increment a stats counter.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            group: Stat group (e.g., "kind", "severity", "code", "lang").
            value: Stat value (e.g., "ast", "warning", "L001", "python").
        """
        key = make_cache_key(snapshot_id, batch_id, task_id, "count", group, value)
        self._stats_counters[key] = self._stats_counters.get(key, 0) + 1

    def flush_stats(self) -> None:
        """Write all accumulated stats counters to the database."""
        with self.env.begin(write=True) as txn:
            for key, count in self._stats_counters.items():
                txn.put(key, encode_counter(count), db=self.env.get_dbi(DBI_STATS))
        self._stats_counters.clear()


class CacheReader:
    """Reader for querying the LMDB cache."""

    def __init__(self, env: CacheEnv):
        """Initialize cache reader.

        Args:
            env: Cache environment (opened in read-only mode).
        """
        self.env = env

    def get_file(self, snapshot_id: str, path: str) -> Optional[dict]:
        """Get file info from the cache.

        Args:
            snapshot_id: Snapshot ID.
            path: File path.

        Returns:
            File info dict or None if not found.
        """
        key = make_cache_key(snapshot_id, path)
        with self.env.begin() as txn:
            value = txn.get(key, db=self.env.get_dbi(DBI_FILES_BY_PATH))
            if value is None:
                return None
            return msgpack.unpackb(value)

    def iter_outputs_by_kind(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        kind: Optional[str] = None,
    ) -> Iterator[dict]:
        """Iterate outputs, optionally filtered by kind.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            kind: Optional kind filter.

        Yields:
            Output records with path, kind, object, format.
        """
        if kind:
            prefix = make_cache_key(snapshot_id, batch_id, task_id, kind)
        else:
            prefix = make_cache_key(snapshot_id, batch_id, task_id)

        with self.env.begin() as txn:
            cursor = txn.cursor(db=self.env.get_dbi(DBI_OUTPUTS_BY_KIND))
            if not cursor.set_range(prefix):
                return

            for key, value in cursor:
                if not key.startswith(prefix):
                    break
                parts = parse_cache_key(key)
                # parts: [snapshot_id, batch_id, task_id, kind, path]
                if len(parts) >= 5:
                    data = msgpack.unpackb(value)
                    yield {
                        "snapshot_id": parts[0],
                        "batch_id": parts[1],
                        "task_id": parts[2],
                        "kind": parts[3],
                        "path": parts[4],
                        "object": data.get("object"),
                        "format": data.get("format"),
                    }

    def iter_diagnostics_by_severity(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        severity: Optional[str] = None,
    ) -> Iterator[dict]:
        """Iterate diagnostics, optionally filtered by severity.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            severity: Optional severity filter.

        Yields:
            Diagnostic records.
        """
        if severity:
            prefix = make_cache_key(snapshot_id, batch_id, task_id, severity)
        else:
            prefix = make_cache_key(snapshot_id, batch_id, task_id)

        with self.env.begin() as txn:
            cursor = txn.cursor(db=self.env.get_dbi(DBI_DIAGS_BY_SEV))
            if not cursor.set_range(prefix):
                return

            for key, value in cursor:
                if not key.startswith(prefix):
                    break
                parts = parse_cache_key(key)
                # parts: [snapshot_id, batch_id, task_id, severity, code, path, line, col]
                if len(parts) >= 8:
                    data = msgpack.unpackb(value)
                    yield {
                        "snapshot_id": parts[0],
                        "batch_id": parts[1],
                        "task_id": parts[2],
                        "severity": parts[3],
                        "code": parts[4],
                        "path": parts[5],
                        "line": int(parts[6]),
                        "col": int(parts[7]),
                        "message": data.get("message", ""),
                        "kind": "diagnostic",
                    }

    def get_stat(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        group: str,
        value: str,
    ) -> int:
        """Get a specific stat counter.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            group: Stat group.
            value: Stat value.

        Returns:
            Counter value (0 if not found).
        """
        key = make_cache_key(snapshot_id, batch_id, task_id, "count", group, value)
        with self.env.begin() as txn:
            data = txn.get(key, db=self.env.get_dbi(DBI_STATS))
            if data is None:
                return 0
            return decode_counter(data)

    def iter_stats(
        self,
        snapshot_id: str,
        batch_id: str,
        task_id: str,
        group: str,
    ) -> Iterator[tuple[str, int]]:
        """Iterate stats for a group.

        Args:
            snapshot_id: Snapshot ID.
            batch_id: Batch ID.
            task_id: Task ID.
            group: Stat group (e.g., "kind", "severity").

        Yields:
            Tuples of (value, count).
        """
        prefix = make_cache_key(snapshot_id, batch_id, task_id, "count", group)

        with self.env.begin() as txn:
            cursor = txn.cursor(db=self.env.get_dbi(DBI_STATS))
            if not cursor.set_range(prefix):
                return

            for key, value in cursor:
                if not key.startswith(prefix):
                    break
                parts = parse_cache_key(key)
                # parts: [snapshot_id, batch_id, task_id, "count", group, stat_value]
                if len(parts) >= 6:
                    stat_value = parts[5]
                    count = decode_counter(value)
                    yield (stat_value, count)


def try_open_cache(store_root: Path, batch_id: str) -> Optional[CacheReader]:
    """Try to open a valid cache for a batch.

    Args:
        store_root: Root directory of the CodeBatch store.
        batch_id: Batch ID.

    Returns:
        CacheReader if cache exists and is valid, None otherwise.
    """
    env = CacheEnv(store_root, readonly=True)

    if not env.exists:
        return None

    try:
        env.open()
        meta = env.load_meta()
        if meta is None:
            env.close()
            return None

        # Load batch info to get snapshot and tasks
        batch_path = store_root / "batches" / batch_id / "batch.json"
        if not batch_path.exists():
            env.close()
            return None

        with open(batch_path, "r", encoding="utf-8") as f:
            batch = json.load(f)

        snapshot_id = batch["snapshot_id"]

        # Get task IDs from plan
        plan_path = store_root / "batches" / batch_id / "plan.json"
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        task_ids = [t["task_id"] for t in plan["tasks"]]

        # Check validity
        if not is_cache_valid(meta, store_root, snapshot_id, batch_id, task_ids):
            env.close()
            return None

        return CacheReader(env)

    except Exception:
        env.close()
        return None
