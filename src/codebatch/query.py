"""Query engine for output indexes.

Answers questions from JSONL scans without requiring a database:
- Which files produced diagnostics?
- Which outputs exist for a given task?
- Which files failed a given task?
- Aggregate counts by kind, severity, or language

With LMDB acceleration (Phase 3):
- If a valid cache exists, uses it for faster queries
- Falls back to JSONL scan if cache is missing or stale
"""

import json
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import CacheReader


class QueryEngine:
    """Query engine for batch output indexes."""

    def __init__(self, store_root: Path, use_cache: bool = True):
        """Initialize the query engine.

        Args:
            store_root: Root directory of the CodeBatch store.
            use_cache: Whether to attempt using LMDB cache (default True).
        """
        self.store_root = Path(store_root)
        self.batches_dir = self.store_root / "batches"
        self.use_cache = use_cache
        self._cache_reader: Optional["CacheReader"] = None
        self._cache_batch_id: Optional[str] = None

    def close(self) -> None:
        """Close any open cache connections.

        Call this before deleting the cache directory.
        """
        if self._cache_reader is not None:
            try:
                self._cache_reader.env.close()
            except Exception:
                pass
            self._cache_reader = None
            self._cache_batch_id = None

    def __enter__(self) -> "QueryEngine":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _get_cache_reader(self, batch_id: str) -> Optional["CacheReader"]:
        """Get a cache reader for a batch, if available.

        Args:
            batch_id: Batch ID.

        Returns:
            CacheReader if cache is valid, None otherwise.
        """
        if not self.use_cache:
            return None

        # Return cached reader if for same batch
        if self._cache_reader is not None and self._cache_batch_id == batch_id:
            return self._cache_reader

        # Try to open cache
        try:
            from .cache import try_open_cache

            reader = try_open_cache(self.store_root, batch_id)
            if reader is not None:
                self._cache_reader = reader
                self._cache_batch_id = batch_id
            return reader
        except Exception:
            return None

    def _get_snapshot_id(self, batch_id: str) -> Optional[str]:
        """Get snapshot ID for a batch.

        Args:
            batch_id: Batch ID.

        Returns:
            Snapshot ID or None if batch not found.
        """
        batch_path = self.batches_dir / batch_id / "batch.json"
        if not batch_path.exists():
            return None
        with open(batch_path, "r", encoding="utf-8") as f:
            batch = json.load(f)
        return batch.get("snapshot_id")

    def _iter_shard_outputs(self, batch_id: str, task_id: str) -> Iterator[dict]:
        """Iterate over all output records for a task.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.

        Yields:
            Output record dicts.
        """
        shards_dir = self.batches_dir / batch_id / "tasks" / task_id / "shards"

        if not shards_dir.exists():
            return

        for shard_dir in sorted(shards_dir.iterdir()):
            if not shard_dir.is_dir():
                continue

            outputs_path = shard_dir / "outputs.index.jsonl"
            if not outputs_path.exists():
                continue

            with open(outputs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)

    def query_diagnostics(
        self,
        batch_id: str,
        task_id: str,
        severity: Optional[str] = None,
        code: Optional[str] = None,
        path_pattern: Optional[str] = None,
    ) -> list[dict]:
        """Query diagnostic outputs.

        Uses LMDB cache if available, falls back to JSONL scan.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            severity: Filter by severity (error, warning, info, hint).
            code: Filter by diagnostic code.
            path_pattern: Filter by path substring.

        Returns:
            List of diagnostic records.
        """
        # Try cache first
        cache_reader = self._get_cache_reader(batch_id)
        if cache_reader is not None:
            return self._query_diagnostics_cached(
                cache_reader, batch_id, task_id, severity, code, path_pattern
            )

        # Fall back to JSONL scan
        return self._query_diagnostics_scan(
            batch_id, task_id, severity, code, path_pattern
        )

    def _query_diagnostics_cached(
        self,
        cache_reader: "CacheReader",
        batch_id: str,
        task_id: str,
        severity: Optional[str],
        code: Optional[str],
        path_pattern: Optional[str],
    ) -> list[dict]:
        """Query diagnostics from LMDB cache."""
        snapshot_id = self._get_snapshot_id(batch_id)
        if snapshot_id is None:
            return []

        results = []
        for record in cache_reader.iter_diagnostics_by_severity(
            snapshot_id, batch_id, task_id, severity
        ):
            if code and record.get("code") != code:
                continue
            if (
                path_pattern
                and path_pattern.lower() not in record.get("path", "").lower()
            ):
                continue
            results.append(record)
        return results

    def _query_diagnostics_scan(
        self,
        batch_id: str,
        task_id: str,
        severity: Optional[str],
        code: Optional[str],
        path_pattern: Optional[str],
    ) -> list[dict]:
        """Query diagnostics from JSONL scan (fallback)."""
        results = []

        for record in self._iter_shard_outputs(batch_id, task_id):
            if record.get("kind") != "diagnostic":
                continue

            if severity and record.get("severity") != severity:
                continue

            if code and record.get("code") != code:
                continue

            if (
                path_pattern
                and path_pattern.lower() not in record.get("path", "").lower()
            ):
                continue

            results.append(record)

        return results

    def query_outputs(
        self,
        batch_id: str,
        task_id: str,
        kind: Optional[str] = None,
        path_pattern: Optional[str] = None,
    ) -> list[dict]:
        """Query output records.

        Uses LMDB cache if available, falls back to JSONL scan.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            kind: Filter by output kind (ast, diagnostic, metric, etc.).
            path_pattern: Filter by path substring.

        Returns:
            List of output records.
        """
        # Try cache first
        cache_reader = self._get_cache_reader(batch_id)
        if cache_reader is not None:
            return self._query_outputs_cached(
                cache_reader, batch_id, task_id, kind, path_pattern
            )

        # Fall back to JSONL scan
        return self._query_outputs_scan(batch_id, task_id, kind, path_pattern)

    def _query_outputs_cached(
        self,
        cache_reader: "CacheReader",
        batch_id: str,
        task_id: str,
        kind: Optional[str],
        path_pattern: Optional[str],
    ) -> list[dict]:
        """Query outputs from LMDB cache."""
        snapshot_id = self._get_snapshot_id(batch_id)
        if snapshot_id is None:
            return []

        results = []
        for record in cache_reader.iter_outputs_by_kind(
            snapshot_id, batch_id, task_id, kind
        ):
            if (
                path_pattern
                and path_pattern.lower() not in record.get("path", "").lower()
            ):
                continue
            results.append(record)
        return results

    def _query_outputs_scan(
        self,
        batch_id: str,
        task_id: str,
        kind: Optional[str],
        path_pattern: Optional[str],
    ) -> list[dict]:
        """Query outputs from JSONL scan (fallback)."""
        results = []

        for record in self._iter_shard_outputs(batch_id, task_id):
            if kind and record.get("kind") != kind:
                continue

            if (
                path_pattern
                and path_pattern.lower() not in record.get("path", "").lower()
            ):
                continue

            results.append(record)

        return results

    def query_stats(
        self,
        batch_id: str,
        task_id: str,
        group_by: str = "kind",
    ) -> dict[str, int]:
        """Get aggregate statistics.

        Uses LMDB cache if available (pre-aggregated), falls back to JSONL scan.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            group_by: Field to group by (kind, severity, code, lang).

        Returns:
            Dict mapping group values to counts.
        """
        # Try cache first (has pre-aggregated stats)
        cache_reader = self._get_cache_reader(batch_id)
        if cache_reader is not None:
            return self._query_stats_cached(cache_reader, batch_id, task_id, group_by)

        # Fall back to JSONL scan
        return self._query_stats_scan(batch_id, task_id, group_by)

    def _query_stats_cached(
        self,
        cache_reader: "CacheReader",
        batch_id: str,
        task_id: str,
        group_by: str,
    ) -> dict[str, int]:
        """Query stats from LMDB cache (pre-aggregated)."""
        snapshot_id = self._get_snapshot_id(batch_id)
        if snapshot_id is None:
            return {}

        result = {}
        for value, count in cache_reader.iter_stats(
            snapshot_id, batch_id, task_id, group_by
        ):
            result[value] = count
        return result

    def _get_lang_by_path(self, batch_id: str) -> dict[str, str]:
        """Load lang_hint mapping from snapshot for a batch.

        Args:
            batch_id: Batch ID.

        Returns:
            Dict mapping path to lang_hint.
        """
        snapshot_id = self._get_snapshot_id(batch_id)
        if snapshot_id is None:
            return {}

        from .snapshot import SnapshotBuilder

        builder = SnapshotBuilder(self.store_root)
        lang_map = {}
        try:
            for record in builder.iter_file_index(snapshot_id):
                lang_map[record["path"]] = record.get("lang_hint", "unknown")
        except Exception:
            pass
        return lang_map

    def _query_stats_scan(
        self,
        batch_id: str,
        task_id: str,
        group_by: str,
    ) -> dict[str, int]:
        """Query stats from JSONL scan (fallback)."""
        counter: Counter[str] = Counter()

        # Load lang mapping for lang stats (to match cache behavior)
        lang_by_path: Optional[dict[str, str]] = None
        if group_by == "lang":
            lang_by_path = self._get_lang_by_path(batch_id)

        for record in self._iter_shard_outputs(batch_id, task_id):
            if group_by == "kind":
                value = record.get("kind", "unknown")
            elif group_by == "severity":
                value = record.get("severity", "none")
            elif group_by == "code":
                value = record.get("code", "none")
            elif group_by == "lang":
                # Use lang_hint from snapshot (same as cache)
                path = record.get("path", "")
                if lang_by_path is not None:
                    value = lang_by_path.get(path, "unknown")
                else:
                    value = "unknown"
            else:
                value = record.get(group_by, "unknown")

            counter[value] += 1

        return dict(counter)

    def query_failed_files(self, batch_id: str, task_id: str) -> list[str]:
        """Get paths of files that produced error diagnostics.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.

        Returns:
            List of file paths with errors.
        """
        failed_paths = set()

        for record in self._iter_shard_outputs(batch_id, task_id):
            if record.get("kind") == "diagnostic" and record.get("severity") == "error":
                failed_paths.add(record.get("path", ""))

        return sorted(failed_paths)

    def query_files_with_outputs(
        self, batch_id: str, task_id: str, kind: str
    ) -> list[str]:
        """Get paths of files that produced outputs of a given kind.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            kind: Output kind to filter by.

        Returns:
            List of file paths.
        """
        paths = set()

        for record in self._iter_shard_outputs(batch_id, task_id):
            if record.get("kind") == kind:
                paths.add(record.get("path", ""))

        return sorted(paths)

    def get_task_summary(self, batch_id: str, task_id: str) -> dict:
        """Get a summary of task outputs.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.

        Returns:
            Summary dict with counts.
        """
        total = 0
        by_kind: Counter[str] = Counter()
        by_severity: Counter[str] = Counter()
        files_with_outputs: set[str] = set()
        files_with_errors: set[str] = set()

        for record in self._iter_shard_outputs(batch_id, task_id):
            total += 1
            kind = record.get("kind", "unknown")
            by_kind[kind] += 1

            if kind == "diagnostic":
                severity = record.get("severity", "unknown")
                by_severity[severity] += 1
                if severity == "error":
                    files_with_errors.add(record.get("path", ""))

            files_with_outputs.add(record.get("path", ""))

        return {
            "total_outputs": total,
            "by_kind": dict(by_kind),
            "by_severity": dict(by_severity),
            "files_with_outputs": len(files_with_outputs),
            "files_with_errors": len(files_with_errors),
        }
