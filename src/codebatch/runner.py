"""Shard runner with state machine and atomic index commit.

Shard execution follows a monotonic state machine:
  ready -> running -> done|failed

State transitions are atomic and never corrupt prior results.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .batch import BatchManager
from .cas import ObjectStore
from .snapshot import SnapshotBuilder


class ShardRunner:
    """Runs individual shards with state management and atomic output commits."""

    SCHEMA_VERSION = "1.0"

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

        # Atomic write via temp file
        temp_path = state_path.with_suffix(".tmp")
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
            "schema_version": self.SCHEMA_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(),
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
        records = self.snapshot_builder.load_file_index(snapshot_id)
        return [r for r in records if r["object"][:2] == shard_id]

    def run_shard(
        self,
        batch_id: str,
        task_id: str,
        shard_id: str,
        executor: Callable[[dict, list[dict], "ShardRunner"], list[dict]],
    ) -> dict:
        """Run a shard with the given executor.

        The executor receives:
          - task config dict
          - list of file records for this shard
          - this runner instance (for CAS access)

        The executor should return a list of output records.

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

        # Increment attempt counter
        state["attempt"] = state.get("attempt", 0) + 1
        attempt = state["attempt"]

        # Transition to running
        state["status"] = "running"
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        self._save_state(batch_id, task_id, shard_id, state)

        # Log shard_started event
        self._append_event(
            task_events_path,
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

            # Get files for this shard
            shard_files = self._get_shard_files(snapshot_id, shard_id)

            # Execute
            output_records = executor(task["config"], shard_files, self)

            # Write outputs atomically
            outputs_path = shard_dir / "outputs.index.jsonl"
            temp_outputs_path = outputs_path.with_suffix(".tmp")

            with open(temp_outputs_path, "w", encoding="utf-8") as f:
                for record in output_records:
                    # Ensure required fields
                    record.setdefault("schema_version", self.SCHEMA_VERSION)
                    record.setdefault("snapshot_id", snapshot_id)
                    record.setdefault("batch_id", batch_id)
                    record.setdefault("task_id", task_id)
                    record.setdefault("shard_id", shard_id)
                    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
                    f.write(json.dumps(record, separators=(",", ":")))
                    f.write("\n")

            # Atomic rename (use replace for Windows compatibility)
            temp_outputs_path.replace(outputs_path)

            # Calculate duration
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Transition to done
            state["status"] = "done"
            state["completed_at"] = end_time.isoformat()
            state["stats"] = {
                "files_processed": len(shard_files),
                "outputs_written": len(output_records),
            }
            self._save_state(batch_id, task_id, shard_id, state)

            # Log shard_completed event
            self._append_event(
                task_events_path,
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
            state["completed_at"] = end_time.isoformat()
            state["error"] = error_info
            self._save_state(batch_id, task_id, shard_id, state)

            # Log shard_failed event
            self._append_event(
                task_events_path,
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
            "schema_version": self.SCHEMA_VERSION,
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
