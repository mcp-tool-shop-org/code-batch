"""Index build command for LMDB acceleration cache.

Command: codebatch index build --store <root> --batch <id> [--rebuild]

Behavior:
1. Resolve snapshot_id from batch.json
2. Create fresh LMDB env (wipe if --rebuild)
3. Ingest snapshot files.index.jsonl -> files_by_path
4. For each task, for each shard:
   - Read outputs.index.jsonl
   - Write to outputs_by_kind
   - If kind=diagnostic: write to diags_by_sev, diags_by_code
   - Update stats counters (including lang join)
5. Write cache_meta.json with fingerprint
"""

import json
from pathlib import Path
from typing import Iterator

from .batch import BatchManager
from .cache import CacheEnv, CacheWriter
from .cache_meta import (
    compute_source_fingerprint,
    create_cache_meta,
)
from .common import object_shard_prefix
from .snapshot import SnapshotBuilder


def iter_shard_outputs(store_root: Path, batch_id: str, task_id: str) -> Iterator[dict]:
    """Iterate all outputs across all shards for a task.

    Args:
        store_root: Root directory of the CodeBatch store.
        batch_id: Batch ID.
        task_id: Task ID.

    Yields:
        Output records from all shards.
    """
    shards_dir = store_root / "batches" / batch_id / "tasks" / task_id / "shards"
    if not shards_dir.exists():
        return

    for shard_dir in sorted(shards_dir.iterdir()):
        if not shard_dir.is_dir():
            continue
        outputs_path = shard_dir / "outputs.index.jsonl"
        if not outputs_path.exists():
            continue

        shard_id = shard_dir.name
        with open(outputs_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["shard_id"] = shard_id
                yield record


def build_index(
    store_root: Path,
    batch_id: str,
    rebuild: bool = False,
    verify: bool = False,
) -> dict:
    """Build the LMDB acceleration cache for a batch.

    Args:
        store_root: Root directory of the CodeBatch store.
        batch_id: Batch ID.
        rebuild: If True, delete existing cache before building.
        verify: If True, verify cache after build (compare to scan).

    Returns:
        Build statistics dict.
    """
    store_root = Path(store_root)

    # Load batch metadata
    batch_manager = BatchManager(store_root)
    batch = batch_manager.load_batch(batch_id)
    plan = batch_manager.load_plan(batch_id)

    snapshot_id = batch["snapshot_id"]
    task_ids = [t["task_id"] for t in plan["tasks"]]

    # Initialize cache environment
    env = CacheEnv(store_root, readonly=False)

    # Delete existing cache if rebuild
    if rebuild and env.exists:
        env.delete()

    # Open environment (creates if needed)
    env.open()

    try:
        writer = CacheWriter(env)

        # Stats for reporting
        stats = {
            "files_indexed": 0,
            "outputs_indexed": 0,
            "diagnostics_indexed": 0,
        }

        # 1. Ingest snapshot files.index.jsonl -> files_by_path
        snapshot_builder = SnapshotBuilder(store_root)
        for record in snapshot_builder.iter_file_index(snapshot_id):
            path = record["path"]
            lang_hint = record.get("lang_hint", "unknown")
            size = record.get("size", 0)
            path_key = record.get("path_key", path)
            obj_prefix = object_shard_prefix(record["object"])

            writer.put_file(
                snapshot_id=snapshot_id,
                path=path,
                lang_hint=lang_hint,
                size=size,
                path_key=path_key,
                obj_prefix=obj_prefix,
            )
            stats["files_indexed"] += 1

        # Build a path -> lang_hint map for stats joins
        lang_by_path = {}
        for record in snapshot_builder.iter_file_index(snapshot_id):
            lang_by_path[record["path"]] = record.get("lang_hint", "unknown")

        # 2. Ingest outputs for each task
        for task_id in task_ids:
            for record in iter_shard_outputs(store_root, batch_id, task_id):
                kind = record.get("kind", "unknown")
                path = record.get("path", "")
                object_ref = record.get("object")
                fmt = record.get("format")

                # Build extra fields for storage (metric name, value, etc.)
                extra = {}
                if kind == "metric":
                    if "metric" in record:
                        extra["metric"] = record["metric"]
                    if "value" in record:
                        extra["value"] = record["value"]

                # Add to outputs_by_kind
                writer.put_output(
                    snapshot_id=snapshot_id,
                    batch_id=batch_id,
                    task_id=task_id,
                    kind=kind,
                    path=path,
                    object_ref=object_ref,
                    fmt=fmt,
                    extra=extra if extra else None,
                )
                stats["outputs_indexed"] += 1

                # Update kind stats
                writer.increment_stat(snapshot_id, batch_id, task_id, "kind", kind)

                # Update lang stats (join with snapshot)
                lang = lang_by_path.get(path, "unknown")
                writer.increment_stat(snapshot_id, batch_id, task_id, "lang", lang)

                # Handle diagnostics
                if kind == "diagnostic":
                    severity = record.get("severity", "unknown")
                    code = record.get("code", "unknown")
                    line = record.get("line", 0)
                    col = record.get("col", 0) or record.get("column", 0)
                    message = record.get("message", "")

                    writer.put_diagnostic(
                        snapshot_id=snapshot_id,
                        batch_id=batch_id,
                        task_id=task_id,
                        severity=severity,
                        code=code,
                        path=path,
                        line=line or 0,
                        col=col or 0,
                        message=message,
                    )
                    stats["diagnostics_indexed"] += 1

                    # Update diagnostic stats
                    writer.increment_stat(
                        snapshot_id, batch_id, task_id, "severity", severity
                    )
                    writer.increment_stat(snapshot_id, batch_id, task_id, "code", code)

        # Flush accumulated stats counters
        writer.flush_stats()

        # 3. Compute source fingerprint and save metadata
        source_fingerprint = compute_source_fingerprint(
            store_root, snapshot_id, batch_id, task_ids
        )

        meta = create_cache_meta(
            snapshot_id=snapshot_id,
            batch_id=batch_id,
            task_ids=task_ids,
            source_fingerprint=source_fingerprint,
        )
        env.save_meta(meta)

        stats["snapshot_id"] = snapshot_id
        stats["batch_id"] = batch_id
        stats["tasks"] = task_ids
        stats["source_fingerprint"] = source_fingerprint[:16] + "..."

        return stats

    finally:
        env.close()
