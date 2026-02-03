"""Shard runner with state machine and atomic index commit.

Shard execution follows a monotonic state machine:
  ready -> running -> done|failed

State transitions are atomic and never corrupt prior results.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Union

from .batch import BatchManager
from .cas import ObjectStore
from .common import SCHEMA_VERSION, PRODUCER, utc_now_z, object_shard_prefix
from .snapshot import SnapshotBuilder


class _CountingIterator:
    """Iterator wrapper that counts items as they're yielded."""

    def __init__(self, iterable: Iterable):
        self._iterator = iter(iterable)
        self.count = 0

    def __iter__(self):
        return self

    def __next__(self):
        item = next(self._iterator)
        self.count += 1
        return item


class ShardRunner:
    """Runs individual shards with state management and atomic output commits."""

    def __init__(self, store_root: Path):
        """Initialize the shard runner.

        Args:
            store_root: Root directory of the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.batch_manager = BatchManager(store_root)
        self.snapshot_builder = SnapshotBuilder(store_root)
        self.object_store = ObjectStore(store_root)

    def _shard_dir(self, batch_id: str, task_id: str, shard_id: str) -> Path:
        """Get the shard directory path."""
        return self.store_root / "batches" / batch_id / "tasks" / task_id / "shards" / shard_id

    def _load_state(self, batch_id: str, task_id: str, shard_id: str) -> dict:
        """Load shard state."""
        state_path = self._shard_dir(batch_id, task_id, shard_id) / "state.json"
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self, batch_id: str, task_id: str, shard_id: str, state: dict) -> None:
        """Save shard state atomically."""
        shard_dir = self._shard_dir(batch_id, task_id, shard_id)
        state_path = shard_dir / "state.json"

        # Atomic write via temp file with PID for race safety
        temp_path = state_path.with_suffix(f".tmp.{os.getpid()}")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        # On Windows, rename fails if target exists; use replace instead
        temp_path.replace(state_path)

    def _append_event(
        self,
        events_path: Path,
        event: str,
        batch_id: str,
        task_id: str = None,
        shard_id: str = None,
        attempt: int = None,
        duration_ms: int = None,
        error: dict = None,
        stats: dict = None,
    ) -> None:
        """Append an event record to events.jsonl."""
        record = {
            "schema_version": SCHEMA_VERSION,
            "ts": utc_now_z(),
            "event": event,
            "batch_id": batch_id,
        }
        if task_id:
            record["task_id"] = task_id
        if shard_id:
            record["shard_id"] = shard_id
        if attempt is not None:
            record["attempt"] = attempt
        if duration_ms is not None:
            record["duration_ms"] = duration_ms
        if error:
            record["error"] = error
        if stats:
            record["stats"] = stats

        with open(events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")))
            f.write("\n")

    def _iter_shard_files(
        self, snapshot_id: str, shard_id: str
    ) -> Iterator[dict]:
        """Stream files assigned to a shard based on hash prefix.

        Files are assigned to shards based on the first two hex chars of their object hash.
        Uses streaming to avoid loading entire index into memory.

        Args:
            snapshot_id: Snapshot ID.
            shard_id: Shard ID (two hex chars, e.g., 'ab').

        Yields:
            File index records assigned to this shard.
        """
        for record in self.snapshot_builder.iter_file_index(snapshot_id):
            # Extract shard prefix from object ref (handles both sha256:<hex> and bare hex)
            obj_shard = object_shard_prefix(record["object"])
            if obj_shard == shard_id:
                yield record

    def _get_shard_files(
        self, snapshot_id: str, shard_id: str
    ) -> list[dict]:
        """Get files assigned to a shard based on hash prefix.

        Files are assigned to shards based on the first two hex chars of their object hash.

        Args:
            snapshot_id: Snapshot ID.
            shard_id: Shard ID (two hex chars, e.g., 'ab').

        Returns:
            List of file index records assigned to this shard.
        """
        return list(self._iter_shard_files(snapshot_id, shard_id))

    def run_shard(
        self,
        batch_id: str,
        task_id: str,
        shard_id: str,
        executor: Callable[[dict, Iterable[dict], "ShardRunner"], Iterable[dict]],
    ) -> dict:
        """Run a shard with the given executor.

        The executor receives:
          - task config dict
          - iterable of file records for this shard (may be iterator or list)
          - this runner instance (for CAS access)

        The executor should return an iterable of output records.
        Executors that need random access can call list() on the input.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            shard_id: Shard ID.
            executor: Function that processes files and returns output records.

        Returns:
            Final shard state.
        """
        shard_dir = self._shard_dir(batch_id, task_id, shard_id)
        task_events_path = shard_dir.parent.parent / "events.jsonl"
        batch_events_path = shard_dir.parent.parent.parent.parent / "events.jsonl"

        # Load current state
        state = self._load_state(batch_id, task_id, shard_id)

        # Check if already done
        if state["status"] == "done":
            return state

        # Enforce dependency completion (Phase 2 requirement)
        deps_ok, incomplete = self.check_deps_complete(batch_id, task_id, shard_id)
        if not deps_ok:
            raise ValueError(
                f"Cannot run task '{task_id}' shard '{shard_id}': "
                f"dependencies not complete: {incomplete}"
            )

        # Increment attempt counter
        state["attempt"] = state.get("attempt", 0) + 1
        attempt = state["attempt"]

        # Transition to running
        state["status"] = "running"
        state["started_at"] = utc_now_z()
        self._save_state(batch_id, task_id, shard_id, state)

        # Log shard_started event to both task and batch
        for events_path in [task_events_path, batch_events_path]:
            self._append_event(
                events_path,
                "shard_started",
                batch_id,
                task_id=task_id,
                shard_id=shard_id,
                attempt=attempt,
            )

        start_time = datetime.now(timezone.utc)

        try:
            # Load task config
            task = self.batch_manager.load_task(batch_id, task_id)
            batch = self.batch_manager.load_batch(batch_id)
            snapshot_id = batch["snapshot_id"]

            # Get files for this shard as streaming iterator with counting
            # Executors that need random access should materialize with list()
            shard_files = _CountingIterator(self._iter_shard_files(snapshot_id, shard_id))

            # Enrich config with execution context for tasks that need it
            # (e.g., symbols task needs batch_id/shard_id for iter_prior_outputs)
            exec_config = dict(task["config"])
            exec_config["_batch_id"] = batch_id
            exec_config["_task_id"] = task_id
            exec_config["_shard_id"] = shard_id
            exec_config["_snapshot_id"] = snapshot_id

            # Execute - output_records may be iterator or list
            output_records = executor(exec_config, shard_files, self)

            # Write outputs atomically, counting as we go
            outputs_path = shard_dir / "outputs.index.jsonl"
            temp_outputs_path = outputs_path.with_suffix(f".tmp.{os.getpid()}")
            outputs_written = 0

            with open(temp_outputs_path, "w", encoding="utf-8") as f:
                for record in output_records:
                    # Ensure required fields
                    record.setdefault("schema_version", SCHEMA_VERSION)
                    record.setdefault("snapshot_id", snapshot_id)
                    record.setdefault("batch_id", batch_id)
                    record.setdefault("task_id", task_id)
                    record.setdefault("shard_id", shard_id)
                    record.setdefault("ts", utc_now_z())
                    f.write(json.dumps(record, separators=(",", ":")))
                    f.write("\n")
                    outputs_written += 1

            # Atomic rename (use replace for Windows compatibility)
            temp_outputs_path.replace(outputs_path)

            # Calculate duration
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Transition to done
            state["status"] = "done"
            state["completed_at"] = utc_now_z()
            state["stats"] = {
                "files_processed": shard_files.count,
                "outputs_written": outputs_written,
            }
            self._save_state(batch_id, task_id, shard_id, state)

            # Log shard_completed event to both task and batch
            for events_path in [task_events_path, batch_events_path]:
                self._append_event(
                    events_path,
                    "shard_completed",
                    batch_id,
                    task_id=task_id,
                    shard_id=shard_id,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    stats=state["stats"],
                )

        except Exception as e:
            # Calculate duration
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Transition to failed
            error_info = {
                "code": type(e).__name__,
                "message": str(e),
            }
            state["status"] = "failed"
            state["completed_at"] = utc_now_z()
            state["error"] = error_info
            self._save_state(batch_id, task_id, shard_id, state)

            # Log shard_failed event to both task and batch
            for events_path in [task_events_path, batch_events_path]:
                self._append_event(
                    events_path,
                    "shard_failed",
                    batch_id,
                    task_id=task_id,
                    shard_id=shard_id,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error=error_info,
                )

        return state

    def reset_shard(self, batch_id: str, task_id: str, shard_id: str) -> dict:
        """Reset a shard to ready state for retry.

        Only failed shards can be reset.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            shard_id: Shard ID.

        Returns:
            New shard state.

        Raises:
            ValueError: If shard is not in failed state.
        """
        state = self._load_state(batch_id, task_id, shard_id)

        if state["status"] != "failed":
            raise ValueError(f"Can only reset failed shards, current status: {state['status']}")

        # Keep attempt counter for tracking
        attempt = state.get("attempt", 0)

        # Reset to ready
        new_state = {
            "schema_name": "codebatch.shard_state",
            "schema_version": SCHEMA_VERSION,
            "producer": PRODUCER,
            "shard_id": shard_id,
            "task_id": task_id,
            "batch_id": batch_id,
            "status": "ready",
            "attempt": attempt,  # Preserve attempt count
        }
        self._save_state(batch_id, task_id, shard_id, new_state)

        # Log retry event
        task_events_path = self._shard_dir(batch_id, task_id, shard_id).parent.parent / "events.jsonl"
        self._append_event(
            task_events_path,
            "shard_retrying",
            batch_id,
            task_id=task_id,
            shard_id=shard_id,
            attempt=attempt + 1,
        )

        return new_state

    def get_shard_outputs(self, batch_id: str, task_id: str, shard_id: str) -> list[dict]:
        """Get output records for a shard.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            shard_id: Shard ID.

        Returns:
            List of output records.
        """
        outputs_path = self._shard_dir(batch_id, task_id, shard_id) / "outputs.index.jsonl"
        if not outputs_path.exists():
            return []

        records = []
        with open(outputs_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def iter_prior_outputs(
        self,
        batch_id: str,
        task_id: str,
        shard_id: str,
        kind: Optional[str] = None,
    ) -> Iterator[dict]:
        """Stream output records from a prior task in the same shard.

        This is the approved mechanism for tasks to consume outputs from
        their dependencies. Tasks may only read from their own shard.

        Args:
            batch_id: Batch ID.
            task_id: Task ID of the dependency (e.g., "01_parse").
            shard_id: Shard ID (must match current shard).
            kind: Optional filter by output kind (e.g., "ast", "diagnostic").

        Yields:
            Output records from the prior task, optionally filtered by kind.

        Raises:
            FileNotFoundError: If the dependency task shard doesn't exist.
        """
        outputs_path = self._shard_dir(batch_id, task_id, shard_id) / "outputs.index.jsonl"
        if not outputs_path.exists():
            return

        with open(outputs_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if kind is None or record.get("kind") == kind:
                    yield record

    def write_shard_outputs(
        self,
        batch_id: str,
        task_id: str,
        shard_id: str,
        records: Iterable[dict],
        snapshot_id: str,
    ) -> int:
        """Write shard outputs atomically with per-shard replacement.

        This is the ONLY approved mechanism for writing outputs.index.jsonl.
        Tasks should use this helper rather than writing directly.

        The write is atomic: temp file -> replace. This enforces the
        per-shard replacement policy (no appending).

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            shard_id: Shard ID.
            records: Iterable of output records.
            snapshot_id: Snapshot ID for record enrichment.

        Returns:
            Number of records written.
        """
        shard_dir = self._shard_dir(batch_id, task_id, shard_id)
        outputs_path = shard_dir / "outputs.index.jsonl"
        temp_outputs_path = outputs_path.with_suffix(f".tmp.{os.getpid()}")

        outputs_written = 0
        with open(temp_outputs_path, "w", encoding="utf-8") as f:
            for record in records:
                # Ensure required fields
                record.setdefault("schema_version", SCHEMA_VERSION)
                record.setdefault("snapshot_id", snapshot_id)
                record.setdefault("batch_id", batch_id)
                record.setdefault("task_id", task_id)
                record.setdefault("shard_id", shard_id)
                record.setdefault("ts", utc_now_z())
                f.write(json.dumps(record, separators=(",", ":")))
                f.write("\n")
                outputs_written += 1

        # Atomic replace (not append!)
        temp_outputs_path.replace(outputs_path)
        return outputs_written

    def check_deps_complete(self, batch_id: str, task_id: str, shard_id: str) -> tuple[bool, list[str]]:
        """Check if all dependencies for a task are complete in this shard.

        Args:
            batch_id: Batch ID.
            task_id: Task ID to check.
            shard_id: Shard ID.

        Returns:
            Tuple of (all_complete, incomplete_task_ids).
        """
        task = self.batch_manager.load_task(batch_id, task_id)
        deps = task.get("inputs", {}).get("tasks", [])

        if not deps:
            return True, []

        incomplete = []
        for dep_task_id in deps:
            try:
                state = self._load_state(batch_id, dep_task_id, shard_id)
                if state.get("status") != "done":
                    incomplete.append(dep_task_id)
            except FileNotFoundError:
                incomplete.append(dep_task_id)

        return len(incomplete) == 0, incomplete
