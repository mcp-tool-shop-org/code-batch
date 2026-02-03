"""Batch and task scaffolding generator.

A batch represents one execution attempt over a snapshot.
Batches are isolated, repeatable, and discardable.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .snapshot import SnapshotBuilder


def generate_batch_id() -> str:
    """Generate a unique batch ID.

    Returns:
        Batch ID in format: batch-YYYYMMDD-HHMMSS-XXXX
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"batch-{timestamp}-{suffix}"


# Pipeline definitions
PIPELINES = {
    "parse": {
        "description": "Parse source files and emit AST + diagnostics",
        "tasks": [
            {
                "task_id": "01_parse",
                "type": "parse",
                "config": {
                    "languages": ["python", "javascript", "typescript"],
                    "emit_ast": True,
                    "emit_diagnostics": True,
                },
            }
        ],
    },
    "analyze": {
        "description": "Parse and analyze source files",
        "tasks": [
            {
                "task_id": "01_parse",
                "type": "parse",
                "config": {
                    "languages": ["python", "javascript", "typescript"],
                    "emit_ast": True,
                    "emit_diagnostics": True,
                },
            },
            {
                "task_id": "02_analyze",
                "type": "analyze",
                "depends_on": ["01_parse"],
                "config": {},
            },
        ],
    },
}


class BatchManager:
    """Manages batch creation and execution scaffolding."""

    SCHEMA_VERSION = "1.0"
    SHARD_COUNT = 256  # 00-ff

    def __init__(self, store_root: Path):
        """Initialize the batch manager.

        Args:
            store_root: Root directory of the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.batches_dir = self.store_root / "batches"
        self.snapshot_builder = SnapshotBuilder(store_root)

    def _generate_shard_ids(self) -> list[str]:
        """Generate all shard IDs (00-ff).

        Returns:
            List of 256 shard IDs.
        """
        return [f"{i:02x}" for i in range(256)]

    def init_batch(
        self,
        snapshot_id: str,
        pipeline: str,
        batch_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Initialize a new batch with complete skeleton.

        Args:
            snapshot_id: Snapshot ID to execute against.
            pipeline: Pipeline name (e.g., 'parse', 'analyze').
            batch_id: Optional batch ID (auto-generated if not provided).
            metadata: Optional user metadata.

        Returns:
            The batch ID.

        Raises:
            ValueError: If snapshot or pipeline doesn't exist.
        """
        # Verify snapshot exists
        try:
            self.snapshot_builder.load_snapshot(snapshot_id)
        except FileNotFoundError:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        # Verify pipeline exists
        if pipeline not in PIPELINES:
            raise ValueError(f"Unknown pipeline: {pipeline}. Available: {list(PIPELINES.keys())}")

        if batch_id is None:
            batch_id = generate_batch_id()

        pipeline_def = PIPELINES[pipeline]
        shard_ids = self._generate_shard_ids()

        # Create batch directory
        batch_dir = self.batches_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        # Write batch.json
        batch_meta = {
            "schema_name": "codebatch.batch",
            "schema_version": self.SCHEMA_VERSION,
            "batch_id": batch_id,
            "snapshot_id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": pipeline,
            "status": "pending",
        }
        if metadata:
            batch_meta["metadata"] = metadata

        with open(batch_dir / "batch.json", "w", encoding="utf-8") as f:
            json.dump(batch_meta, f, indent=2)

        # Write plan.json
        plan = {
            "schema_name": "codebatch.plan",
            "schema_version": self.SCHEMA_VERSION,
            "batch_id": batch_id,
            "tasks": pipeline_def["tasks"],
        }

        with open(batch_dir / "plan.json", "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

        # Create empty events.jsonl
        (batch_dir / "events.jsonl").touch()

        # Create tasks directory and task scaffolding
        tasks_dir = batch_dir / "tasks"
        tasks_dir.mkdir(exist_ok=True)

        for task_def in pipeline_def["tasks"]:
            task_id = task_def["task_id"]
            task_dir = tasks_dir / task_id
            task_dir.mkdir(exist_ok=True)

            # Write task.json
            task_meta = {
                "schema_name": "codebatch.task",
                "schema_version": self.SCHEMA_VERSION,
                "task_id": task_id,
                "batch_id": batch_id,
                "type": task_def["type"],
                "sharding": {
                    "strategy": "hash_prefix",
                    "shard_count": self.SHARD_COUNT,
                    "shard_ids": shard_ids,
                },
                "inputs": {
                    "snapshot": True,
                    "tasks": task_def.get("depends_on", []),
                },
                "config": task_def.get("config", {}),
                "status": "pending",
            }

            with open(task_dir / "task.json", "w", encoding="utf-8") as f:
                json.dump(task_meta, f, indent=2)

            # Create empty events.jsonl
            (task_dir / "events.jsonl").touch()

            # Create shards directory with all shard subdirectories
            shards_dir = task_dir / "shards"
            shards_dir.mkdir(exist_ok=True)

            for shard_id in shard_ids:
                shard_dir = shards_dir / shard_id
                shard_dir.mkdir(exist_ok=True)

                # Write initial state.json
                state = {
                    "schema_name": "codebatch.shard_state",
                    "schema_version": self.SCHEMA_VERSION,
                    "shard_id": shard_id,
                    "task_id": task_id,
                    "batch_id": batch_id,
                    "status": "ready",
                    "attempt": 0,
                }

                with open(shard_dir / "state.json", "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)

                # Create empty outputs.index.jsonl
                (shard_dir / "outputs.index.jsonl").touch()

        return batch_id

    def load_batch(self, batch_id: str) -> dict:
        """Load batch metadata.

        Args:
            batch_id: Batch ID to load.

        Returns:
            Batch metadata dict.

        Raises:
            FileNotFoundError: If batch doesn't exist.
        """
        batch_path = self.batches_dir / batch_id / "batch.json"
        with open(batch_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_plan(self, batch_id: str) -> dict:
        """Load batch execution plan.

        Args:
            batch_id: Batch ID to load.

        Returns:
            Plan dict.

        Raises:
            FileNotFoundError: If batch doesn't exist.
        """
        plan_path = self.batches_dir / batch_id / "plan.json"
        with open(plan_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_task(self, batch_id: str, task_id: str) -> dict:
        """Load task metadata.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.

        Returns:
            Task metadata dict.
        """
        task_path = self.batches_dir / batch_id / "tasks" / task_id / "task.json"
        with open(task_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_shard_state(self, batch_id: str, task_id: str, shard_id: str) -> dict:
        """Load shard state.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            shard_id: Shard ID.

        Returns:
            Shard state dict.
        """
        state_path = (
            self.batches_dir / batch_id / "tasks" / task_id / "shards" / shard_id / "state.json"
        )
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_batches(self) -> list[str]:
        """List all batch IDs.

        Returns:
            List of batch IDs.
        """
        if not self.batches_dir.exists():
            return []

        return [
            d.name
            for d in self.batches_dir.iterdir()
            if d.is_dir() and (d / "batch.json").exists()
        ]

    def get_task_ids(self, batch_id: str) -> list[str]:
        """Get task IDs for a batch.

        Args:
            batch_id: Batch ID.

        Returns:
            List of task IDs.
        """
        tasks_dir = self.batches_dir / batch_id / "tasks"
        if not tasks_dir.exists():
            return []

        return [
            d.name
            for d in tasks_dir.iterdir()
            if d.is_dir() and (d / "task.json").exists()
        ]
