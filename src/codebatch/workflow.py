"""Workflow orchestration for human-friendly batch execution.

This module provides the orchestration layer for running batches without
requiring users to manually invoke per-shard commands. It composes existing
primitives (BatchManager, ShardRunner) to provide a seamless workflow.

Phase 5 rules:
- No new truth stores
- No new state files beyond existing state.json and outputs
- Sequential and deterministic execution
- Purely orchestrating existing primitives
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from .batch import BatchManager, PIPELINES
from .common import object_shard_prefix
from .query import QueryEngine
from .runner import ShardRunner
from .snapshot import SnapshotBuilder
from .tasks import get_executor


@dataclass
class ShardProgress:
    """Progress for a single shard."""

    shard_id: str
    status: str  # ready, running, done, failed
    files_processed: int = 0
    outputs_written: int = 0
    error: Optional[str] = None


@dataclass
class TaskProgress:
    """Progress for a single task."""

    task_id: str
    task_type: str
    status: str  # pending, ready, running, done, failed
    shards_total: int = 0
    shards_done: int = 0
    shards_failed: int = 0
    shards_ready: int = 0


@dataclass
class BatchProgress:
    """Overall batch progress."""

    batch_id: str
    snapshot_id: str
    pipeline: str
    status: str  # pending, running, done, failed
    tasks: list[TaskProgress] = field(default_factory=list)
    total_shards: int = 0
    done_shards: int = 0
    failed_shards: int = 0


@dataclass
class RunResult:
    """Result of running a batch."""

    batch_id: str
    success: bool
    tasks_completed: int = 0
    tasks_failed: int = 0
    shards_completed: int = 0
    shards_failed: int = 0
    error: Optional[str] = None


class WorkflowRunner:
    """Orchestrates batch execution.

    Provides a human-friendly interface for running batches without
    requiring manual shard iteration.
    """

    def __init__(self, store_root: Path):
        """Initialize the workflow runner.

        Args:
            store_root: Path to the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.batch_manager = BatchManager(store_root)
        self.shard_runner = ShardRunner(store_root)
        self.snapshot_builder = SnapshotBuilder(store_root)

    def get_status(self, batch_id: str) -> BatchProgress:
        """Get the current progress of a batch.

        Args:
            batch_id: Batch ID to check.

        Returns:
            BatchProgress with current state of all tasks and shards.
        """
        batch = self.batch_manager.load_batch(batch_id)
        plan = self.batch_manager.load_plan(batch_id)

        progress = BatchProgress(
            batch_id=batch_id,
            snapshot_id=batch["snapshot_id"],
            pipeline=batch["pipeline"],
            status="pending",
        )

        for task_def in plan["tasks"]:
            task_id = task_def["task_id"]
            task_progress = self._get_task_progress(batch_id, task_id, task_def["type"])
            progress.tasks.append(task_progress)
            progress.total_shards += task_progress.shards_total
            progress.done_shards += task_progress.shards_done
            progress.failed_shards += task_progress.shards_failed

        # Determine overall status
        if progress.failed_shards > 0:
            progress.status = "failed"
        elif progress.done_shards == progress.total_shards:
            progress.status = "done"
        elif progress.done_shards > 0:
            progress.status = "running"
        else:
            progress.status = "pending"

        return progress

    def _get_task_progress(
        self, batch_id: str, task_id: str, task_type: str
    ) -> TaskProgress:
        """Get progress for a single task."""
        shards_dir = (
            self.store_root / "batches" / batch_id / "tasks" / task_id / "shards"
        )

        task_progress = TaskProgress(
            task_id=task_id,
            task_type=task_type,
            status="pending",
        )

        if not shards_dir.exists():
            return task_progress

        for shard_dir in shards_dir.iterdir():
            if not shard_dir.is_dir():
                continue

            state_path = shard_dir / "state.json"
            if not state_path.exists():
                continue

            task_progress.shards_total += 1

            import json

            with open(state_path) as f:
                state = json.load(f)

            status = state.get("status", "ready")
            if status == "done":
                task_progress.shards_done += 1
            elif status == "failed":
                task_progress.shards_failed += 1
            elif status == "ready":
                task_progress.shards_ready += 1

        # Determine task status
        if task_progress.shards_failed > 0:
            task_progress.status = "failed"
        elif task_progress.shards_done == task_progress.shards_total:
            task_progress.status = "done"
        elif task_progress.shards_done > 0:
            task_progress.status = "running"
        elif task_progress.shards_ready > 0:
            task_progress.status = "ready"

        return task_progress

    def _get_shards_with_files(self, snapshot_id: str) -> set[str]:
        """Get shard IDs that have files."""
        records = self.snapshot_builder.load_file_index(snapshot_id)
        return set(object_shard_prefix(r["object"]) for r in records)

    def _iter_tasks_in_order(
        self, batch_id: str
    ) -> Iterator[tuple[str, str, list[str]]]:
        """Iterate tasks in dependency order.

        Yields:
            Tuples of (task_id, task_type, depends_on)
        """
        plan = self.batch_manager.load_plan(batch_id)

        # Simple topological sort - assumes tasks are already in order
        for task_def in plan["tasks"]:
            yield (
                task_def["task_id"],
                task_def["type"],
                task_def.get("depends_on", []),
            )

    def _check_deps_complete(
        self, batch_id: str, depends_on: list[str], shard_id: str
    ) -> bool:
        """Check if dependencies are complete for a shard."""
        for dep_task_id in depends_on:
            try:
                state = self.shard_runner._load_state(batch_id, dep_task_id, shard_id)
                if state.get("status") != "done":
                    return False
            except FileNotFoundError:
                return False
        return True

    def run(
        self,
        batch_id: str,
        task_filter: Optional[str] = None,
        on_shard_start: Optional[callable] = None,
        on_shard_complete: Optional[callable] = None,
        max_workers: int = 1,
    ) -> RunResult:
        """Run all tasks and shards in a batch.

        Tasks execute sequentially (respecting dependency order).
        Shards within each task execute in parallel when max_workers > 1.

        Args:
            batch_id: Batch ID to run.
            task_filter: If provided, only run this task.
            on_shard_start: Callback(batch_id, task_id, shard_id) when shard starts.
            on_shard_complete: Callback(batch_id, task_id, shard_id, state) when done.
            max_workers: Maximum parallel shard workers (default 1 = sequential).

        Returns:
            RunResult with execution summary.
        """
        batch = self.batch_manager.load_batch(batch_id)
        shards_with_files = self._get_shards_with_files(batch["snapshot_id"])

        result = RunResult(batch_id=batch_id, success=True)

        for task_id, task_type, depends_on in self._iter_tasks_in_order(batch_id):
            if task_filter and task_id != task_filter:
                continue

            try:
                executor = get_executor(task_id)
            except ValueError as e:
                result.error = str(e)
                result.success = False
                return result

            task_failed = False

            # Collect eligible shards for this task
            eligible_shards = []
            for shard_id in sorted(shards_with_files):
                try:
                    state = self.shard_runner._load_state(batch_id, task_id, shard_id)
                except FileNotFoundError:
                    continue

                if state.get("status") == "done":
                    result.shards_completed += 1
                    continue

                if depends_on and not self._check_deps_complete(
                    batch_id, depends_on, shard_id
                ):
                    continue

                eligible_shards.append(shard_id)

            if max_workers > 1 and len(eligible_shards) > 1:
                # Parallel shard execution
                task_failed = self._run_shards_parallel(
                    batch_id, task_id, executor, eligible_shards,
                    result, on_shard_start, on_shard_complete,
                    max_workers,
                )
            else:
                # Sequential shard execution
                for shard_id in eligible_shards:
                    if on_shard_start:
                        on_shard_start(batch_id, task_id, shard_id)

                    try:
                        final_state = self.shard_runner.run_shard(
                            batch_id, task_id, shard_id, executor
                        )
                    except Exception as e:
                        final_state = {"status": "failed", "error": str(e)}

                    if on_shard_complete:
                        on_shard_complete(batch_id, task_id, shard_id, final_state)

                    if final_state.get("status") == "done":
                        result.shards_completed += 1
                    else:
                        result.shards_failed += 1
                        task_failed = True

            if task_failed:
                result.tasks_failed += 1
            else:
                result.tasks_completed += 1

        result.success = result.tasks_failed == 0
        return result

    def _run_shards_parallel(
        self,
        batch_id: str,
        task_id: str,
        executor: callable,
        shard_ids: list[str],
        result: RunResult,
        on_shard_start: Optional[callable],
        on_shard_complete: Optional[callable],
        max_workers: int,
    ) -> bool:
        """Run shards in parallel using a thread pool.

        Each shard gets its own ShardRunner instance to avoid state conflicts.

        Args:
            batch_id: Batch ID.
            task_id: Task ID.
            executor: Task executor function.
            shard_ids: List of shard IDs to run.
            result: RunResult to update (shards_completed/failed).
            on_shard_start: Optional callback.
            on_shard_complete: Optional callback.
            max_workers: Thread pool size.

        Returns:
            True if any shard failed, False if all succeeded.
        """
        task_failed = False

        def run_one_shard(shard_id: str) -> tuple[str, dict]:
            # Each thread gets its own ShardRunner for isolation
            runner = ShardRunner(self.store_root)
            if on_shard_start:
                on_shard_start(batch_id, task_id, shard_id)
            try:
                final_state = runner.run_shard(
                    batch_id, task_id, shard_id, executor
                )
            except Exception as e:
                final_state = {"status": "failed", "error": str(e)}
            return shard_id, final_state

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(run_one_shard, sid): sid for sid in shard_ids
            }
            for future in as_completed(futures):
                shard_id, final_state = future.result()

                if on_shard_complete:
                    on_shard_complete(batch_id, task_id, shard_id, final_state)

                if final_state.get("status") == "done":
                    result.shards_completed += 1
                else:
                    result.shards_failed += 1
                    task_failed = True

        return task_failed

    def resume(
        self,
        batch_id: str,
        on_shard_start: Optional[callable] = None,
        on_shard_complete: Optional[callable] = None,
        max_workers: int = 1,
    ) -> RunResult:
        """Resume a batch, running only shards not marked done.

        Args:
            batch_id: Batch ID to resume.
            on_shard_start: Callback when shard starts.
            on_shard_complete: Callback when shard completes.
            max_workers: Maximum parallel shard workers (default 1 = sequential).

        Returns:
            RunResult with execution summary.
        """
        # Resume is the same as run - run() already skips done shards
        return self.run(
            batch_id,
            on_shard_start=on_shard_start,
            on_shard_complete=on_shard_complete,
            max_workers=max_workers,
        )


def get_shards_for_task(
    store_root: Path, batch_id: str, task_id: str
) -> list[ShardProgress]:
    """Get shard details for a task.

    Args:
        store_root: Path to store.
        batch_id: Batch ID.
        task_id: Task ID.

    Returns:
        List of ShardProgress for each shard.
    """
    import json

    shards_dir = store_root / "batches" / batch_id / "tasks" / task_id / "shards"

    if not shards_dir.exists():
        return []

    shards = []
    for shard_dir in sorted(shards_dir.iterdir()):
        if not shard_dir.is_dir():
            continue

        state_path = shard_dir / "state.json"
        if not state_path.exists():
            continue

        with open(state_path) as f:
            state = json.load(f)

        progress = ShardProgress(
            shard_id=shard_dir.name,
            status=state.get("status", "unknown"),
        )

        if "stats" in state:
            progress.files_processed = state["stats"].get("files_processed", 0)
            progress.outputs_written = state["stats"].get("outputs_written", 0)

        if "error" in state:
            progress.error = state["error"].get("message", "Unknown error")

        shards.append(progress)

    return shards


def get_output_summary(
    store_root: Path, batch_id: str, task_filter: Optional[str] = None
) -> dict:
    """Get a summary of outputs for a batch.

    Args:
        store_root: Path to store.
        batch_id: Batch ID.
        task_filter: Optional task to filter by.

    Returns:
        Summary dict with counts by kind, severity, etc.
    """
    engine = QueryEngine(store_root)
    manager = BatchManager(store_root)

    plan = manager.load_plan(batch_id)
    task_ids = [t["task_id"] for t in plan["tasks"]]

    if task_filter:
        task_ids = [t for t in task_ids if t == task_filter]

    summary = {
        "batch_id": batch_id,
        "tasks": {},
        "totals": {
            "outputs": 0,
            "diagnostics": 0,
            "errors": 0,
            "warnings": 0,
        },
    }

    for task_id in task_ids:
        # Get output stats
        stats = engine.query_stats(batch_id, task_id, group_by="kind")

        # Get diagnostic stats
        diag_stats = engine.query_stats(batch_id, task_id, group_by="severity")

        task_summary = {
            "outputs_by_kind": stats,
            "diagnostics_by_severity": diag_stats,
            "total_outputs": sum(stats.values()),
        }

        summary["tasks"][task_id] = task_summary
        summary["totals"]["outputs"] += task_summary["total_outputs"]

        for sev, count in diag_stats.items():
            if sev == "error":
                summary["totals"]["errors"] += count
            elif sev == "warning":
                summary["totals"]["warnings"] += count
            summary["totals"]["diagnostics"] += count

    return summary


def list_pipelines() -> list[dict]:
    """List available pipelines.

    Returns:
        List of pipeline info dicts.
    """
    result = []
    for name, config in PIPELINES.items():
        result.append(
            {
                "name": name,
                "description": config.get("description", ""),
                "tasks": [t["task_id"] for t in config["tasks"]],
            }
        )
    return result


def get_pipeline_details(pipeline_name: str) -> Optional[dict]:
    """Get details for a pipeline.

    Args:
        pipeline_name: Pipeline name.

    Returns:
        Pipeline config or None if not found.
    """
    if pipeline_name not in PIPELINES:
        return None

    config = PIPELINES[pipeline_name]
    return {
        "name": pipeline_name,
        "description": config.get("description", ""),
        "tasks": config["tasks"],
    }
