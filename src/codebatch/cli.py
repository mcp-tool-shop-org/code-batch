"""Command-line interface for CodeBatch."""

import argparse
import json
import sys
from pathlib import Path

from .batch import BatchManager, PIPELINES
from .snapshot import SnapshotBuilder


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Handle the snapshot command."""
    source_dir = Path(args.source)
    store_root = Path(args.store)

    if not source_dir.is_dir():
        print(f"Error: Source is not a directory: {source_dir}", file=sys.stderr)
        return 1

    # Create store root if needed
    store_root.mkdir(parents=True, exist_ok=True)

    builder = SnapshotBuilder(store_root)

    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON metadata: {e}", file=sys.stderr)
            return 1

    snapshot_id = builder.build(
        source_dir,
        snapshot_id=args.id,
        metadata=metadata,
    )

    print(f"Created snapshot: {snapshot_id}")

    if args.verbose:
        snapshot = builder.load_snapshot(snapshot_id)
        print(f"  Files: {snapshot['file_count']}")
        print(f"  Total bytes: {snapshot['total_bytes']}")

    return 0


def cmd_snapshot_list(args: argparse.Namespace) -> int:
    """Handle the snapshot list command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    builder = SnapshotBuilder(store_root)
    snapshots = builder.list_snapshots()

    if not snapshots:
        print("No snapshots found.")
        return 0

    for snapshot_id in sorted(snapshots):
        if args.verbose:
            snapshot = builder.load_snapshot(snapshot_id)
            print(f"{snapshot_id}  files={snapshot['file_count']}  bytes={snapshot['total_bytes']}")
        else:
            print(snapshot_id)

    return 0


def cmd_snapshot_show(args: argparse.Namespace) -> int:
    """Handle the snapshot show command."""
    store_root = Path(args.store)
    snapshot_id = args.id

    builder = SnapshotBuilder(store_root)

    try:
        snapshot = builder.load_snapshot(snapshot_id)
    except FileNotFoundError:
        print(f"Error: Snapshot not found: {snapshot_id}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(snapshot, indent=2))
    else:
        print(f"Snapshot: {snapshot_id}")
        print(f"  Created: {snapshot['created_at']}")
        print(f"  Source: {snapshot['source']['path']}")
        print(f"  Files: {snapshot['file_count']}")
        print(f"  Total bytes: {snapshot['total_bytes']}")

    if args.files:
        print("\nFiles:")
        records = builder.load_file_index(snapshot_id)
        for record in records:
            lang = f" [{record['lang_hint']}]" if record.get("lang_hint") else ""
            print(f"  {record['path']} ({record['size']} bytes){lang}")

    return 0


def main(argv: list[str] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="codebatch",
        description="Content-addressed batch execution engine",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Create a snapshot")
    snapshot_parser.add_argument("source", help="Source directory to snapshot")
    snapshot_parser.add_argument("--store", required=True, help="Store root directory")
    snapshot_parser.add_argument("--id", help="Snapshot ID (auto-generated if not provided)")
    snapshot_parser.add_argument("--metadata", help="JSON metadata to include")
    snapshot_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    snapshot_parser.set_defaults(func=cmd_snapshot)

    # snapshot list command
    list_parser = subparsers.add_parser("snapshot-list", help="List snapshots")
    list_parser.add_argument("--store", required=True, help="Store root directory")
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Show details")
    list_parser.set_defaults(func=cmd_snapshot_list)

    # snapshot show command
    show_parser = subparsers.add_parser("snapshot-show", help="Show snapshot details")
    show_parser.add_argument("id", help="Snapshot ID")
    show_parser.add_argument("--store", required=True, help="Store root directory")
    show_parser.add_argument("--json", action="store_true", help="Output as JSON")
    show_parser.add_argument("--files", action="store_true", help="List files in snapshot")
    show_parser.set_defaults(func=cmd_snapshot_show)

    # batch init command
    batch_init_parser = subparsers.add_parser("batch", help="Initialize a batch")
    batch_init_parser.add_argument("action", choices=["init"], help="Batch action")
    batch_init_parser.add_argument("--snapshot", required=True, help="Snapshot ID to execute")
    batch_init_parser.add_argument("--pipeline", required=True, help="Pipeline name (e.g., 'parse')")
    batch_init_parser.add_argument("--store", required=True, help="Store root directory")
    batch_init_parser.add_argument("--id", help="Batch ID (auto-generated if not provided)")
    batch_init_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    batch_init_parser.set_defaults(func=cmd_batch_init)

    # batch list command
    batch_list_parser = subparsers.add_parser("batch-list", help="List batches")
    batch_list_parser.add_argument("--store", required=True, help="Store root directory")
    batch_list_parser.add_argument("-v", "--verbose", action="store_true", help="Show details")
    batch_list_parser.set_defaults(func=cmd_batch_list)

    # batch show command
    batch_show_parser = subparsers.add_parser("batch-show", help="Show batch details")
    batch_show_parser.add_argument("id", help="Batch ID")
    batch_show_parser.add_argument("--store", required=True, help="Store root directory")
    batch_show_parser.add_argument("--json", action="store_true", help="Output as JSON")
    batch_show_parser.set_defaults(func=cmd_batch_show)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


def cmd_batch_init(args: argparse.Namespace) -> int:
    """Handle the batch init command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    manager = BatchManager(store_root)

    try:
        batch_id = manager.init_batch(
            snapshot_id=args.snapshot,
            pipeline=args.pipeline,
            batch_id=args.id,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Created batch: {batch_id}")

    if args.verbose:
        batch = manager.load_batch(batch_id)
        plan = manager.load_plan(batch_id)
        print(f"  Snapshot: {batch['snapshot_id']}")
        print(f"  Pipeline: {batch['pipeline']}")
        print(f"  Tasks: {len(plan['tasks'])}")
        for task in plan["tasks"]:
            print(f"    - {task['task_id']} ({task['type']})")

    return 0


def cmd_batch_list(args: argparse.Namespace) -> int:
    """Handle the batch list command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    manager = BatchManager(store_root)
    batches = manager.list_batches()

    if not batches:
        print("No batches found.")
        return 0

    for batch_id in sorted(batches):
        if args.verbose:
            batch = manager.load_batch(batch_id)
            print(f"{batch_id}  snapshot={batch['snapshot_id']}  pipeline={batch['pipeline']}  status={batch['status']}")
        else:
            print(batch_id)

    return 0


def cmd_batch_show(args: argparse.Namespace) -> int:
    """Handle the batch show command."""
    store_root = Path(args.store)
    batch_id = args.id

    manager = BatchManager(store_root)

    try:
        batch = manager.load_batch(batch_id)
    except FileNotFoundError:
        print(f"Error: Batch not found: {batch_id}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(batch, indent=2))
    else:
        print(f"Batch: {batch_id}")
        print(f"  Snapshot: {batch['snapshot_id']}")
        print(f"  Pipeline: {batch['pipeline']}")
        print(f"  Status: {batch['status']}")
        print(f"  Created: {batch['created_at']}")

        plan = manager.load_plan(batch_id)
        print(f"\nTasks ({len(plan['tasks'])}):")
        for task_def in plan["tasks"]:
            task = manager.load_task(batch_id, task_def["task_id"])
            print(f"  {task['task_id']}: {task['type']} [{task['status']}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
