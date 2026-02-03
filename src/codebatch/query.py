"""Query engine for output indexes.

Answers questions from JSONL scans without requiring a database:
- Which files produced diagnostics?
- Which outputs exist for a given task?
- Which files failed a given task?
- Aggregate counts by kind, severity, or language
"""

import json
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional


class QueryEngine:
    """Query engine for batch output indexes."""

    def __init__(self, store_root: Path):
        """Initialize the query engine.

        Args:
            store_root: Root directory of the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.batches_dir = self.store_root / "batches"

    def _iter_shard_outputs(
        self, batch_id: str, task_id: str
    ) -> Iterator[dict]:
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

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            severity: Filter by severity (error, warning, info, hint).
            code: Filter by diagnostic code.
            path_pattern: Filter by path substring.

        Returns:
            List of diagnostic records.
        """
        results = []

        for record in self._iter_shard_outputs(batch_id, task_id):
            if record.get("kind") != "diagnostic":
                continue

            if severity and record.get("severity") != severity:
                continue

            if code and record.get("code") != code:
                continue

            if path_pattern and path_pattern.lower() not in record.get("path", "").lower():
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

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            kind: Filter by output kind (ast, diagnostic, metric, etc.).
            path_pattern: Filter by path substring.

        Returns:
            List of output records.
        """
        results = []

        for record in self._iter_shard_outputs(batch_id, task_id):
            if kind and record.get("kind") != kind:
                continue

            if path_pattern and path_pattern.lower() not in record.get("path", "").lower():
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

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            group_by: Field to group by (kind, severity, code, lang).

        Returns:
            Dict mapping group values to counts.
        """
        counter: Counter[str] = Counter()

        for record in self._iter_shard_outputs(batch_id, task_id):
            if group_by == "kind":
                value = record.get("kind", "unknown")
            elif group_by == "severity":
                value = record.get("severity", "none")
            elif group_by == "code":
                value = record.get("code", "none")
            elif group_by == "lang":
                # Extract language from path extension
                path = record.get("path", "")
                ext = path.rsplit(".", 1)[-1] if "." in path else "none"
                value = ext
            else:
                value = record.get(group_by, "unknown")

            counter[value] += 1

        return dict(counter)

    def query_failed_files(
        self, batch_id: str, task_id: str
    ) -> list[str]:
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
