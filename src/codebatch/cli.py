"""Command-line interface for CodeBatch."""

import argparse
import json
import sys
from pathlib import Path

from .batch import BatchManager, PIPELINES
from .query import QueryEngine
from .runner import ShardRunner
from .snapshot import SnapshotBuilder
from .store import init_store, ensure_store, StoreExistsError, InvalidStoreError


def cmd_init(args: argparse.Namespace) -> int:
    """Handle the init command."""
    store_root = Path(args.store)

    try:
        store_meta = init_store(store_root)
        print(f"Initialized store: {store_root}")
        if args.verbose:
            print(f"  Schema version: {store_meta['schema_version']}")
            print(f"  Created: {store_meta['created_at']}")
        return 0
    except StoreExistsError:
        print(f"Error: Store already exists: {store_root}", file=sys.stderr)
        return 1


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Handle the snapshot command."""
    source_dir = Path(args.source)
    store_root = Path(args.store)

    if not source_dir.is_dir():
        print(f"Error: Source is not a directory: {source_dir}", file=sys.stderr)
        return 1

    # Ensure store is initialized
    try:
        ensure_store(store_root)
    except InvalidStoreError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

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
            print(
                f"{snapshot_id}  files={snapshot['file_count']}  bytes={snapshot['total_bytes']}"
            )
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

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new store")
    init_parser.add_argument("store", help="Store root directory to initialize")
    init_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    init_parser.set_defaults(func=cmd_init)

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Create a snapshot")
    snapshot_parser.add_argument("source", help="Source directory to snapshot")
    snapshot_parser.add_argument("--store", required=True, help="Store root directory")
    snapshot_parser.add_argument(
        "--id", help="Snapshot ID (auto-generated if not provided)"
    )
    snapshot_parser.add_argument("--metadata", help="JSON metadata to include")
    snapshot_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    snapshot_parser.set_defaults(func=cmd_snapshot)

    # snapshot list command
    list_parser = subparsers.add_parser("snapshot-list", help="List snapshots")
    list_parser.add_argument("--store", required=True, help="Store root directory")
    list_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show details"
    )
    list_parser.set_defaults(func=cmd_snapshot_list)

    # snapshot show command
    show_parser = subparsers.add_parser("snapshot-show", help="Show snapshot details")
    show_parser.add_argument("id", help="Snapshot ID")
    show_parser.add_argument("--store", required=True, help="Store root directory")
    show_parser.add_argument("--json", action="store_true", help="Output as JSON")
    show_parser.add_argument(
        "--files", action="store_true", help="List files in snapshot"
    )
    show_parser.set_defaults(func=cmd_snapshot_show)

    # batch init command
    batch_init_parser = subparsers.add_parser("batch", help="Initialize a batch")
    batch_init_parser.add_argument("action", choices=["init"], help="Batch action")
    batch_init_parser.add_argument(
        "--snapshot", required=True, help="Snapshot ID to execute"
    )
    batch_init_parser.add_argument(
        "--pipeline", required=True, help="Pipeline name (e.g., 'parse')"
    )
    batch_init_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    batch_init_parser.add_argument(
        "--id", help="Batch ID (auto-generated if not provided)"
    )
    batch_init_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    batch_init_parser.set_defaults(func=cmd_batch_init)

    # batch list command
    batch_list_parser = subparsers.add_parser("batch-list", help="List batches")
    batch_list_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    batch_list_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show details"
    )
    batch_list_parser.set_defaults(func=cmd_batch_list)

    # batch show command
    batch_show_parser = subparsers.add_parser("batch-show", help="Show batch details")
    batch_show_parser.add_argument("id", help="Batch ID")
    batch_show_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    batch_show_parser.add_argument("--json", action="store_true", help="Output as JSON")
    batch_show_parser.set_defaults(func=cmd_batch_show)

    # run-shard command
    run_shard_parser = subparsers.add_parser("run-shard", help="Run a shard")
    run_shard_parser.add_argument("--batch", required=True, help="Batch ID")
    run_shard_parser.add_argument("--task", required=True, help="Task ID")
    run_shard_parser.add_argument(
        "--shard", required=True, help="Shard ID (e.g., 'ab')"
    )
    run_shard_parser.add_argument("--store", required=True, help="Store root directory")
    run_shard_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    run_shard_parser.set_defaults(func=cmd_run_shard)

    # query diagnostics command
    query_diag_parser = subparsers.add_parser("query", help="Query outputs")
    query_diag_parser.add_argument(
        "query_type", choices=["diagnostics", "outputs", "stats"], help="Query type"
    )
    query_diag_parser.add_argument("--batch", required=True, help="Batch ID")
    query_diag_parser.add_argument("--task", required=True, help="Task ID")
    query_diag_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    query_diag_parser.add_argument(
        "--severity", help="Filter by severity (error, warning, info, hint)"
    )
    query_diag_parser.add_argument("--kind", help="Filter by output kind")
    query_diag_parser.add_argument("--code", help="Filter by diagnostic code")
    query_diag_parser.add_argument("--path", help="Filter by path substring")
    query_diag_parser.add_argument(
        "--group-by",
        choices=["kind", "severity", "code", "lang"],
        default="kind",
        help="Group stats by field",
    )
    query_diag_parser.add_argument("--json", action="store_true", help="Output as JSON")
    query_diag_parser.set_defaults(func=cmd_query)

    # index build command
    index_build_parser = subparsers.add_parser(
        "index-build", help="Build LMDB acceleration cache"
    )
    index_build_parser.add_argument("--batch", required=True, help="Batch ID")
    index_build_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    index_build_parser.add_argument(
        "--rebuild", action="store_true", help="Delete existing cache before building"
    )
    index_build_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify cache against JSONL scan after build",
    )
    index_build_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output"
    )
    index_build_parser.set_defaults(func=cmd_index_build)

    # gate list command
    gate_list_parser = subparsers.add_parser("gate-list", help="List all gates")
    gate_list_parser.add_argument(
        "--status",
        choices=["ENFORCED", "HARNESS", "PLACEHOLDER"],
        help="Filter by status",
    )
    gate_list_parser.add_argument("--tag", help="Filter by tag")
    gate_list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    gate_list_parser.set_defaults(func=cmd_gate_list)

    # gate run command
    gate_run_parser = subparsers.add_parser("gate-run", help="Run a gate")
    gate_run_parser.add_argument("gate_id", help="Gate ID or alias")
    gate_run_parser.add_argument("--store", required=True, help="Store root directory")
    gate_run_parser.add_argument("--batch", help="Batch ID")
    gate_run_parser.add_argument("--json", action="store_true", help="Output as JSON")
    gate_run_parser.set_defaults(func=cmd_gate_run)

    # gate run-bundle command
    gate_bundle_parser = subparsers.add_parser("gate-bundle", help="Run a gate bundle")
    gate_bundle_parser.add_argument(
        "bundle", help="Bundle name (phase1, phase2, phase3, release)"
    )
    gate_bundle_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    gate_bundle_parser.add_argument("--batch", help="Batch ID")
    gate_bundle_parser.add_argument(
        "--fail-fast", action="store_true", help="Stop on first failure"
    )
    gate_bundle_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    gate_bundle_parser.set_defaults(func=cmd_gate_bundle)

    # gate explain command
    gate_explain_parser = subparsers.add_parser("gate-explain", help="Explain a gate")
    gate_explain_parser.add_argument("gate_id", help="Gate ID or alias")
    gate_explain_parser.set_defaults(func=cmd_gate_explain)

    # ========== Phase 5 Workflow Commands ==========

    # run command - run all tasks/shards in a batch
    run_parser = subparsers.add_parser(
        "run", help="Run all tasks and shards in a batch"
    )
    run_parser.add_argument("--batch", required=True, help="Batch ID to run")
    run_parser.add_argument("--task", help="Run only this task (optional)")
    run_parser.add_argument("--store", required=True, help="Store root directory")
    run_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show progress"
    )
    run_parser.add_argument("--json", action="store_true", help="Output as JSON")
    run_parser.set_defaults(func=cmd_run)

    # resume command - run only incomplete shards
    resume_parser = subparsers.add_parser(
        "resume", help="Resume batch, running only incomplete shards"
    )
    resume_parser.add_argument("--batch", required=True, help="Batch ID to resume")
    resume_parser.add_argument("--store", required=True, help="Store root directory")
    resume_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show progress"
    )
    resume_parser.add_argument("--json", action="store_true", help="Output as JSON")
    resume_parser.set_defaults(func=cmd_resume)

    # status command - show batch progress
    status_parser = subparsers.add_parser("status", help="Show batch progress")
    status_parser.add_argument("--batch", required=True, help="Batch ID")
    status_parser.add_argument("--store", required=True, help="Store root directory")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")
    status_parser.set_defaults(func=cmd_status)

    # summary command - human summary of outputs
    summary_parser = subparsers.add_parser(
        "summary", help="Show human summary of batch outputs"
    )
    summary_parser.add_argument("--batch", required=True, help="Batch ID")
    summary_parser.add_argument("--task", help="Filter by task")
    summary_parser.add_argument("--store", required=True, help="Store root directory")
    summary_parser.add_argument("--json", action="store_true", help="Output as JSON")
    summary_parser.set_defaults(func=cmd_summary)

    # pipelines command - list available pipelines
    pipelines_parser = subparsers.add_parser(
        "pipelines", help="List available pipelines"
    )
    pipelines_parser.add_argument("--json", action="store_true", help="Output as JSON")
    pipelines_parser.set_defaults(func=cmd_pipelines)

    # pipeline show command
    pipeline_show_parser = subparsers.add_parser(
        "pipeline", help="Show pipeline details"
    )
    pipeline_show_parser.add_argument("name", help="Pipeline name")
    pipeline_show_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    pipeline_show_parser.set_defaults(func=cmd_pipeline_show)

    # tasks command - list tasks in a batch
    tasks_parser = subparsers.add_parser("tasks", help="List tasks in a batch")
    tasks_parser.add_argument("--batch", required=True, help="Batch ID")
    tasks_parser.add_argument("--store", required=True, help="Store root directory")
    tasks_parser.add_argument("--json", action="store_true", help="Output as JSON")
    tasks_parser.set_defaults(func=cmd_tasks)

    # shards command - list shards for a task
    shards_parser = subparsers.add_parser("shards", help="List shards for a task")
    shards_parser.add_argument("--batch", required=True, help="Batch ID")
    shards_parser.add_argument("--task", required=True, help="Task ID")
    shards_parser.add_argument("--store", required=True, help="Store root directory")
    shards_parser.add_argument(
        "--status", choices=["ready", "done", "failed"], help="Filter by status"
    )
    shards_parser.add_argument("--json", action="store_true", help="Output as JSON")
    shards_parser.set_defaults(func=cmd_shards)

    # errors command - alias for query diagnostics with severity=error
    errors_parser = subparsers.add_parser(
        "errors", help="Show errors from a batch (alias)"
    )
    errors_parser.add_argument("--batch", required=True, help="Batch ID")
    errors_parser.add_argument("--task", help="Filter by task")
    errors_parser.add_argument("--store", required=True, help="Store root directory")
    errors_parser.add_argument(
        "--limit", type=int, default=50, help="Max errors to show"
    )
    errors_parser.add_argument("--json", action="store_true", help="Output as JSON")
    errors_parser.set_defaults(func=cmd_errors)

    # files command - list files in a snapshot/batch
    files_parser = subparsers.add_parser("files", help="List files in a snapshot")
    files_parser.add_argument("--snapshot", help="Snapshot ID")
    files_parser.add_argument("--batch", help="Batch ID (uses batch's snapshot)")
    files_parser.add_argument("--store", required=True, help="Store root directory")
    files_parser.add_argument(
        "--limit", type=int, default=100, help="Max files to show"
    )
    files_parser.add_argument("--json", action="store_true", help="Output as JSON")
    files_parser.set_defaults(func=cmd_files)

    # top command - top outputs by count
    top_parser = subparsers.add_parser("top", help="Show top output kinds/severities")
    top_parser.add_argument("--batch", required=True, help="Batch ID")
    top_parser.add_argument("--task", help="Filter by task")
    top_parser.add_argument("--store", required=True, help="Store root directory")
    top_parser.add_argument(
        "--by", choices=["kind", "severity", "code"], default="kind", help="Group by"
    )
    top_parser.add_argument(
        "--limit", type=int, default=10, help="Number of top entries"
    )
    top_parser.add_argument("--json", action="store_true", help="Output as JSON")
    top_parser.set_defaults(func=cmd_top)

    # ========== Phase 6 Commands ==========

    # inspect command - file drilldown
    inspect_parser = subparsers.add_parser(
        "inspect", help="Show all outputs for a file"
    )
    inspect_parser.add_argument("path", help="File path to inspect")
    inspect_parser.add_argument("--batch", required=True, help="Batch ID")
    inspect_parser.add_argument("--store", required=True, help="Store root directory")
    inspect_parser.add_argument(
        "--kinds", help="Filter by output kinds (comma-separated)"
    )
    inspect_parser.add_argument("--json", action="store_true", help="Output as JSON")
    inspect_parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    inspect_parser.add_argument(
        "--explain", action="store_true", help="Show data sources instead of data"
    )
    inspect_parser.set_defaults(func=cmd_inspect)

    # explain command - show data sources for a view
    explain_parser = subparsers.add_parser(
        "explain", help="Show data sources for a command"
    )
    explain_parser.add_argument(
        "subcommand", help="Command to explain (e.g., 'inspect', 'diff')"
    )
    explain_parser.add_argument("--json", action="store_true", help="Output as JSON")
    explain_parser.set_defaults(func=cmd_explain)

    # diff command - compare two batches
    diff_parser = subparsers.add_parser(
        "diff", help="Compare outputs between two batches"
    )
    diff_parser.add_argument("batch_a", help="First batch ID (before/baseline)")
    diff_parser.add_argument("batch_b", help="Second batch ID (after/current)")
    diff_parser.add_argument("--store", required=True, help="Store root directory")
    diff_parser.add_argument("--kind", help="Filter by output kind")
    diff_parser.add_argument("--json", action="store_true", help="Output as JSON")
    diff_parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    diff_parser.add_argument(
        "--explain", action="store_true", help="Show data sources instead of data"
    )
    diff_parser.set_defaults(func=cmd_diff)

    # regressions command - show diagnostics that worsened
    regressions_parser = subparsers.add_parser(
        "regressions", help="Show diagnostics that worsened between batches"
    )
    regressions_parser.add_argument("batch_a", help="First batch ID (before/baseline)")
    regressions_parser.add_argument("batch_b", help="Second batch ID (after/current)")
    regressions_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    regressions_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    regressions_parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    regressions_parser.add_argument(
        "--explain", action="store_true", help="Show data sources instead of data"
    )
    regressions_parser.set_defaults(func=cmd_regressions)

    # improvements command - show diagnostics that improved
    improvements_parser = subparsers.add_parser(
        "improvements", help="Show diagnostics that improved between batches"
    )
    improvements_parser.add_argument("batch_a", help="First batch ID (before/baseline)")
    improvements_parser.add_argument("batch_b", help="Second batch ID (after/current)")
    improvements_parser.add_argument(
        "--store", required=True, help="Store root directory"
    )
    improvements_parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    improvements_parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    improvements_parser.add_argument(
        "--explain", action="store_true", help="Show data sources instead of data"
    )
    improvements_parser.set_defaults(func=cmd_improvements)

    # ========== Phase 7 Integration API Commands ==========

    # api command - show API capabilities
    api_parser = subparsers.add_parser("api", help="Show API capabilities and metadata")
    api_parser.add_argument(
        "--json", action="store_true", help="Output as JSON (recommended)"
    )
    api_parser.set_defaults(func=cmd_api)

    # diagnose command - verify store integrity
    diagnose_parser = subparsers.add_parser(
        "diagnose", help="Verify store integrity and compatibility"
    )
    diagnose_parser.add_argument("--store", required=True, help="Store root directory")
    diagnose_parser.add_argument("--json", action="store_true", help="Output as JSON")
    diagnose_parser.set_defaults(func=cmd_diagnose)

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
            print(
                f"{batch_id}  snapshot={batch['snapshot_id']}  pipeline={batch['pipeline']}  status={batch['status']}"
            )
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


def cmd_run_shard(args: argparse.Namespace) -> int:
    """Handle the run-shard command."""
    store_root = Path(args.store)
    batch_id = args.batch
    task_id = args.task
    shard_id = args.shard

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    runner = ShardRunner(store_root)

    # Check current state
    try:
        state = runner._load_state(batch_id, task_id, shard_id)
    except FileNotFoundError:
        print(
            f"Error: Shard not found: {batch_id}/{task_id}/{shard_id}", file=sys.stderr
        )
        return 1

    if state["status"] == "done":
        print(f"Shard {shard_id} already done, skipping.")
        return 0

    # Import the task executor
    from .tasks import get_executor

    try:
        executor = get_executor(task_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Running shard {shard_id} for task {task_id}...")

    final_state = runner.run_shard(batch_id, task_id, shard_id, executor)

    if final_state["status"] == "done":
        print(
            f"Shard completed: {final_state['stats']['files_processed']} files, {final_state['stats']['outputs_written']} outputs"
        )
        return 0
    else:
        print(
            f"Shard failed: {final_state.get('error', {}).get('message', 'Unknown error')}"
        )
        return 1


def cmd_query(args: argparse.Namespace) -> int:
    """Handle query commands."""
    store_root = Path(args.store)
    batch_id = args.batch
    task_id = args.task
    query_type = args.query_type

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    engine = QueryEngine(store_root)

    if query_type == "diagnostics":
        results = engine.query_diagnostics(
            batch_id,
            task_id,
            severity=args.severity,
            code=args.code,
            path_pattern=args.path,
        )

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print("No diagnostics found.")
            else:
                for diag in results:
                    sev = diag.get("severity", "?")
                    code = diag.get("code", "?")
                    path = diag.get("path", "?")
                    line = diag.get("line", "?")
                    msg = diag.get("message", "")
                    print(f"[{sev.upper()}] {path}:{line} {code}: {msg}")

    elif query_type == "outputs":
        results = engine.query_outputs(
            batch_id,
            task_id,
            kind=args.kind,
            path_pattern=args.path,
        )

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print("No outputs found.")
            else:
                for output in results:
                    kind = output.get("kind", "?")
                    path = output.get("path", "?")
                    obj = (
                        output.get("object", "")[:12] + "..."
                        if output.get("object")
                        else ""
                    )
                    print(f"{kind:15} {path} {obj}")

    elif query_type == "stats":
        stats = engine.query_stats(batch_id, task_id, group_by=args.group_by)

        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            if not stats:
                print("No outputs found.")
            else:
                print(f"Stats grouped by {args.group_by}:")
                for key, count in sorted(stats.items(), key=lambda x: -x[1]):
                    print(f"  {key}: {count}")

    return 0


def cmd_index_build(args: argparse.Namespace) -> int:
    """Handle the index build command."""
    store_root = Path(args.store)
    batch_id = args.batch

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .index_build import build_index

    try:
        print(f"Building index for batch {batch_id}...")
        stats = build_index(
            store_root,
            batch_id,
            rebuild=args.rebuild,
            verify=args.verify,
        )

        print("Index built successfully:")
        print(f"  Files indexed: {stats['files_indexed']}")
        print(f"  Outputs indexed: {stats['outputs_indexed']}")
        print(f"  Diagnostics indexed: {stats['diagnostics_indexed']}")

        if args.verbose:
            print(f"  Snapshot: {stats['snapshot_id']}")
            print(f"  Batch: {stats['batch_id']}")
            print(f"  Tasks: {', '.join(stats['tasks'])}")
            print(f"  Fingerprint: {stats['source_fingerprint']}")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error building index: {e}", file=sys.stderr)
        return 1


def cmd_gate_list(args: argparse.Namespace) -> int:
    """Handle the gate list command."""
    from .gates.registry import get_registry
    from .gates.result import GateStatus

    registry = get_registry()
    gates = registry.list_all()

    # Apply filters
    if args.status:
        status = GateStatus(args.status)
        gates = [g for g in gates if g.status == status]

    if args.tag:
        gates = [g for g in gates if args.tag in g.tags]

    if not gates:
        print("No gates found.")
        return 0

    if args.json:
        import json

        print(json.dumps([g.to_dict() for g in gates], indent=2))
    else:
        # Print table header
        print(f"{'ID':<15} {'STATUS':<12} {'TITLE':<40}")
        print("-" * 70)
        for gate in sorted(gates, key=lambda g: g.gate_id):
            {
                GateStatus.ENFORCED: "\u2705",  # checkmark
                GateStatus.HARNESS: "\u2699\ufe0f",  # gear
                GateStatus.PLACEHOLDER: "\u23f3",  # hourglass
            }.get(gate.status, "")
            print(f"{gate.gate_id:<15} {gate.status.value:<12} {gate.title:<40}")

        print(f"\nTotal: {len(gates)} gates")

    return 0


def cmd_gate_run(args: argparse.Namespace) -> int:
    """Handle the gate run command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .gates.runner import run_gate

    try:
        result = run_gate(
            store_root=store_root,
            gate_id=args.gate_id,
            batch_id=args.batch,
        )

        if args.json:
            print(result.to_json())
        else:
            status_icon = "\u2705" if result.passed else "\u274c"
            print(f"{status_icon} Gate: {result.gate_id}")
            print(f"   Status: {result.status.value}")
            print(f"   Passed: {result.passed}")
            print(f"   Duration: {result.duration_ms}ms")

            if result.details:
                print("   Details:")
                for k, v in result.details.items():
                    print(f"     {k}: {v}")

            if result.failures:
                print("   Failures:")
                for f in result.failures:
                    print(f"     - {f.message}")
                    if f.suggestion:
                        print(f"       Suggestion: {f.suggestion}")

        # Exit code based on enforcement
        if not result.passed and result.status.value == "ENFORCED":
            return 1
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error running gate: {e}", file=sys.stderr)
        return 2


def cmd_gate_bundle(args: argparse.Namespace) -> int:
    """Handle the gate bundle command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .gates.runner import run_bundle

    try:
        result = run_bundle(
            store_root=store_root,
            bundle_name=args.bundle,
            batch_id=args.batch,
            fail_fast=args.fail_fast,
        )

        if args.json:
            print(result.to_json())
        else:
            status_icon = "\u2705" if result.passed else "\u274c"
            print(f"{status_icon} Bundle: {result.bundle_name}")
            print(f"   Total: {result.total}")
            print(f"   Passed: {result.passed_count}")
            print(f"   Failed: {result.failed_count}")
            print(f"   Skipped: {result.skipped_count}")
            print(f"   Duration: {result.duration_ms}ms")

            if result.results:
                print("\n   Results:")
                for r in result.results:
                    icon = "\u2705" if r.passed else "\u274c"
                    print(f"     {icon} {r.gate_id} ({r.status.value})")
                    if not r.passed and r.failures:
                        for f in r.failures:
                            print(f"        - {f.message}")

        # Exit code 1 if any ENFORCED gates failed
        if not result.passed:
            return 1
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error running bundle: {e}", file=sys.stderr)
        return 2


def cmd_gate_explain(args: argparse.Namespace) -> int:
    """Handle the gate explain command."""
    from .gates.registry import get_registry

    registry = get_registry()
    gate = registry.get(args.gate_id)

    if gate is None:
        suggestions = registry.suggest_similar(args.gate_id)
        print(f"Error: Unknown gate '{args.gate_id}'", file=sys.stderr)
        if suggestions:
            print(f"Did you mean: {', '.join(suggestions)}?", file=sys.stderr)
        return 1

    print(f"Gate: {gate.gate_id}")
    print(f"Title: {gate.title}")
    print(f"Status: {gate.status.value}")
    print("\nDescription:")
    print(f"  {gate.description}")
    print(f"\nRequired Inputs: {', '.join(gate.required_inputs)}")
    print(f"Tags: {', '.join(gate.tags)}")
    if gate.aliases:
        print(f"Aliases: {', '.join(gate.aliases)}")

    return 0


# ========== Phase 5 Command Handlers ==========


def cmd_run(args: argparse.Namespace) -> int:
    """Handle the run command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        print("  Hint: Run 'codebatch init <store>' to create a store", file=sys.stderr)
        return 1

    from .workflow import WorkflowRunner

    runner = WorkflowRunner(store_root)

    # Progress callbacks for verbose mode
    def on_shard_start(batch_id, task_id, shard_id):
        if args.verbose:
            print(f"  Running {task_id}/{shard_id}...", end="", flush=True)

    def on_shard_complete(batch_id, task_id, shard_id, state):
        if args.verbose:
            status = state.get("status", "unknown")
            stats = state.get("stats", {})
            outputs = stats.get("outputs_written", 0)
            if status == "done":
                print(f" done ({outputs} outputs)")
            else:
                error = state.get("error", {}).get("message", "Unknown error")
                print(f" FAILED: {error}")

    print(f"Running batch {args.batch}...")

    try:
        result = runner.run(
            args.batch,
            task_filter=args.task,
            on_shard_start=on_shard_start,
            on_shard_complete=on_shard_complete,
        )
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        print(
            "  Hint: Run 'codebatch batch-list --store <store>' to see batches",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "batch_id": result.batch_id,
                    "success": result.success,
                    "tasks_completed": result.tasks_completed,
                    "tasks_failed": result.tasks_failed,
                    "shards_completed": result.shards_completed,
                    "shards_failed": result.shards_failed,
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        if result.success:
            print("\nOK: Batch completed successfully")
            print(f"  Tasks: {result.tasks_completed} completed")
            print(f"  Shards: {result.shards_completed} completed")
            print("\nNext steps:")
            print(f"  codebatch summary --batch {args.batch} --store {args.store}")
        else:
            print("\nFAIL: Batch completed with failures")
            print(
                f"  Tasks: {result.tasks_completed} completed, {result.tasks_failed} failed"
            )
            print(
                f"  Shards: {result.shards_completed} completed, {result.shards_failed} failed"
            )
            if result.error:
                print(f"  Error: {result.error}")
            print("\nNext steps:")
            print(f"  codebatch errors --batch {args.batch} --store {args.store}")

    return 0 if result.success else 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Handle the resume command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .workflow import WorkflowRunner

    runner = WorkflowRunner(store_root)

    # Progress callbacks
    def on_shard_start(batch_id, task_id, shard_id):
        if args.verbose:
            print(f"  Running {task_id}/{shard_id}...", end="", flush=True)

    def on_shard_complete(batch_id, task_id, shard_id, state):
        if args.verbose:
            status = state.get("status", "unknown")
            if status == "done":
                print(" done")
            else:
                print(" FAILED")

    print(f"Resuming batch {args.batch}...")

    try:
        result = runner.resume(
            args.batch,
            on_shard_start=on_shard_start,
            on_shard_complete=on_shard_complete,
        )
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "batch_id": result.batch_id,
                    "success": result.success,
                    "shards_completed": result.shards_completed,
                    "shards_failed": result.shards_failed,
                },
                indent=2,
            )
        )
    else:
        if result.success:
            print("\nOK: Batch resumed successfully")
            print(f"  Shards: {result.shards_completed} completed")
        else:
            print("\nFAIL: Batch has failures")
            print(
                f"  Shards: {result.shards_completed} completed, {result.shards_failed} failed"
            )

    return 0 if result.success else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Handle the status command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .workflow import WorkflowRunner

    runner = WorkflowRunner(store_root)

    try:
        progress = runner.get_status(args.batch)
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "batch_id": progress.batch_id,
                    "snapshot_id": progress.snapshot_id,
                    "pipeline": progress.pipeline,
                    "status": progress.status,
                    "total_shards": progress.total_shards,
                    "done_shards": progress.done_shards,
                    "failed_shards": progress.failed_shards,
                    "tasks": [
                        {
                            "task_id": t.task_id,
                            "task_type": t.task_type,
                            "status": t.status,
                            "shards_total": t.shards_total,
                            "shards_done": t.shards_done,
                            "shards_failed": t.shards_failed,
                        }
                        for t in progress.tasks
                    ],
                },
                indent=2,
            )
        )
    else:
        # Status icon (ASCII-safe)
        icon = {
            "done": "[DONE]",
            "running": "[...]",
            "failed": "[FAIL]",
            "pending": "[ ]",
        }.get(progress.status, "[?]")

        print(f"Batch: {progress.batch_id}")
        print(f"Pipeline: {progress.pipeline}")
        print(f"Status: {icon} {progress.status.upper()}")
        print()

        # Progress bar (ASCII-safe)
        if progress.total_shards > 0:
            pct = int(100 * progress.done_shards / progress.total_shards)
            bar_width = 40
            filled = int(bar_width * progress.done_shards / progress.total_shards)
            bar = "#" * filled + "-" * (bar_width - filled)
            print(f"Progress: [{bar}] {pct}%")
            print(f"  Shards: {progress.done_shards}/{progress.total_shards} done")
            if progress.failed_shards > 0:
                print(f"  Failed: {progress.failed_shards}")
        print()

        # Task breakdown
        print(f"{'TASK':<15} {'TYPE':<10} {'STATUS':<10} {'PROGRESS':<15}")
        print("-" * 55)
        for task in progress.tasks:
            task_icon = {"done": "*", "running": "~", "failed": "!"}.get(
                task.status, " "
            )
            prog = f"{task.shards_done}/{task.shards_total}"
            print(
                f"{task.task_id:<15} {task.task_type:<10} {task_icon} {task.status:<8} {prog:<15}"
            )

    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Handle the summary command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .workflow import get_output_summary

    try:
        summary = get_output_summary(store_root, args.batch, task_filter=args.task)
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Batch Summary: {summary['batch_id']}")
        print()

        totals = summary["totals"]
        print("Totals:")
        print(f"  Outputs: {totals['outputs']}")
        print(f"  Diagnostics: {totals['diagnostics']}")
        if totals["errors"] > 0:
            print(f"  Errors: {totals['errors']} (!)")
        if totals["warnings"] > 0:
            print(f"  Warnings: {totals['warnings']}")
        print()

        for task_id, task_summary in summary["tasks"].items():
            print(f"Task: {task_id}")
            print(f"  Total outputs: {task_summary['total_outputs']}")

            if task_summary["outputs_by_kind"]:
                print("  By kind:")
                for kind, count in sorted(
                    task_summary["outputs_by_kind"].items(), key=lambda x: -x[1]
                ):
                    print(f"    {kind}: {count}")

            if task_summary["diagnostics_by_severity"]:
                print("  Diagnostics:")
                for sev, count in task_summary["diagnostics_by_severity"].items():
                    print(f"    {sev}: {count}")
            print()

    return 0


def cmd_pipelines(args: argparse.Namespace) -> int:
    """Handle the pipelines command."""
    from .workflow import list_pipelines

    pipelines = list_pipelines()

    if args.json:
        print(json.dumps(pipelines, indent=2))
    else:
        print(f"{'NAME':<15} {'DESCRIPTION':<40} {'TASKS'}")
        print("-" * 70)
        for p in pipelines:
            tasks = ", ".join(p["tasks"])
            print(f"{p['name']:<15} {p['description']:<40} {tasks}")

    return 0


def cmd_pipeline_show(args: argparse.Namespace) -> int:
    """Handle the pipeline show command."""
    from .workflow import get_pipeline_details

    details = get_pipeline_details(args.name)

    if details is None:
        print(f"Error: Unknown pipeline '{args.name}'", file=sys.stderr)
        print(
            "  Hint: Run 'codebatch pipelines' to see available pipelines",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(details, indent=2))
    else:
        print(f"Pipeline: {details['name']}")
        print(f"Description: {details['description']}")
        print()
        print("Tasks:")
        for task in details["tasks"]:
            deps = ", ".join(task.get("depends_on", [])) or "none"
            print(f"  {task['task_id']} ({task['type']})")
            print(f"    Depends on: {deps}")

    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    """Handle the tasks command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    manager = BatchManager(store_root)

    try:
        plan = manager.load_plan(args.batch)
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    tasks_info = []
    for task_def in plan["tasks"]:
        task_id = task_def["task_id"]
        task = manager.load_task(args.batch, task_id)
        tasks_info.append(
            {
                "task_id": task_id,
                "type": task_def["type"],
                "status": task.get("status", "ready"),
                "depends_on": task_def.get("depends_on", []),
            }
        )

    if args.json:
        print(json.dumps(tasks_info, indent=2))
    else:
        print(f"{'TASK':<15} {'TYPE':<12} {'STATUS':<10} {'DEPENDS ON'}")
        print("-" * 60)
        for t in tasks_info:
            deps = ", ".join(t["depends_on"]) or "-"
            print(f"{t['task_id']:<15} {t['type']:<12} {t['status']:<10} {deps}")

    return 0


def cmd_shards(args: argparse.Namespace) -> int:
    """Handle the shards command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    from .workflow import get_shards_for_task

    shards = get_shards_for_task(store_root, args.batch, args.task)

    if not shards:
        print(f"No shards found for task {args.task}", file=sys.stderr)
        return 1

    # Filter by status if requested
    if args.status:
        shards = [s for s in shards if s.status == args.status]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "shard_id": s.shard_id,
                        "status": s.status,
                        "files_processed": s.files_processed,
                        "outputs_written": s.outputs_written,
                        "error": s.error,
                    }
                    for s in shards
                ],
                indent=2,
            )
        )
    else:
        print(f"{'SHARD':<8} {'STATUS':<10} {'FILES':<8} {'OUTPUTS':<10} {'ERROR'}")
        print("-" * 60)
        for s in shards:
            error = (
                (s.error[:30] + "...")
                if s.error and len(s.error) > 30
                else (s.error or "")
            )
            print(
                f"{s.shard_id:<8} {s.status:<10} {s.files_processed:<8} {s.outputs_written:<10} {error}"
            )

        # Summary
        done = sum(1 for s in shards if s.status == "done")
        failed = sum(1 for s in shards if s.status == "failed")
        print(f"\nTotal: {len(shards)} shards ({done} done, {failed} failed)")

    return 0


def cmd_errors(args: argparse.Namespace) -> int:
    """Handle the errors command (alias)."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    engine = QueryEngine(store_root)
    manager = BatchManager(store_root)

    try:
        plan = manager.load_plan(args.batch)
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    task_ids = [t["task_id"] for t in plan["tasks"]]
    if args.task:
        task_ids = [t for t in task_ids if t == args.task]

    all_errors = []
    for task_id in task_ids:
        errors = engine.query_diagnostics(args.batch, task_id, severity="error")
        for e in errors:
            e["task_id"] = task_id
        all_errors.extend(errors)

    # Limit results
    if len(all_errors) > args.limit:
        all_errors = all_errors[: args.limit]
        truncated = True
    else:
        truncated = False

    if args.json:
        print(json.dumps(all_errors, indent=2))
    else:
        if not all_errors:
            print("No errors found.")
            return 0

        for e in all_errors:
            path = e.get("path", "?")
            line = e.get("line", "?")
            code = e.get("code", "?")
            msg = e.get("message", "")
            print(f"[ERROR] {path}:{line} ({code})")
            print(f"  {msg}")
            print()

        if truncated:
            print(f"(Showing first {args.limit} errors, use --limit to see more)")

    return 0


def cmd_files(args: argparse.Namespace) -> int:
    """Handle the files command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    snapshot_id = args.snapshot

    # If batch provided, get snapshot from batch
    if args.batch and not snapshot_id:
        manager = BatchManager(store_root)
        try:
            batch = manager.load_batch(args.batch)
            snapshot_id = batch["snapshot_id"]
        except FileNotFoundError:
            print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
            return 1

    if not snapshot_id:
        print("Error: Must provide --snapshot or --batch", file=sys.stderr)
        return 1

    builder = SnapshotBuilder(store_root)

    try:
        records = builder.load_file_index(snapshot_id)
    except FileNotFoundError:
        print(f"Error: Snapshot not found: {snapshot_id}", file=sys.stderr)
        return 1

    # Limit results
    total = len(records)
    if total > args.limit:
        records = records[: args.limit]
        truncated = True
    else:
        truncated = False

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(f"{'PATH':<50} {'SIZE':<10} {'LANG'}")
        print("-" * 70)
        for r in records:
            lang = r.get("lang_hint", "-")
            print(f"{r['path']:<50} {r['size']:<10} {lang}")

        print(f"\nTotal: {total} files")
        if truncated:
            print(f"(Showing first {args.limit} files, use --limit to see more)")

    return 0


def cmd_top(args: argparse.Namespace) -> int:
    """Handle the top command."""
    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    engine = QueryEngine(store_root)
    manager = BatchManager(store_root)

    try:
        plan = manager.load_plan(args.batch)
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    task_ids = [t["task_id"] for t in plan["tasks"]]
    if args.task:
        task_ids = [t for t in task_ids if t == args.task]

    # Aggregate stats across tasks
    combined = {}
    for task_id in task_ids:
        stats = engine.query_stats(args.batch, task_id, group_by=args.by)
        for key, count in stats.items():
            combined[key] = combined.get(key, 0) + count

    # Sort and limit
    sorted_items = sorted(combined.items(), key=lambda x: -x[1])[: args.limit]

    if args.json:
        print(json.dumps(dict(sorted_items), indent=2))
    else:
        print(f"Top {args.limit} by {args.by}:")
        print()
        print(f"{'VALUE':<30} {'COUNT':<10}")
        print("-" * 45)
        for key, count in sorted_items:
            print(f"{key:<30} {count:<10}")

    return 0


# ========== Phase 6 Command Handlers ==========


def cmd_inspect(args: argparse.Namespace) -> int:
    """Handle the inspect command (Phase 6).

    Shows all outputs for a specific file path, grouped by kind/task.
    Read-only: does not modify the store.
    """
    from .ui import ColorMode, render_json

    # Handle --explain mode
    if getattr(args, "explain", False):
        explanation = get_explain_info("inspect")
        if args.json:
            print(render_json(explanation))
        else:
            print_explain(explanation)
        return 0

    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    # Determine color mode
    from .ui import render_table, Column

    color_mode = ColorMode.NEVER if args.no_color else ColorMode.AUTO

    engine = QueryEngine(store_root)
    manager = BatchManager(store_root)

    try:
        plan = manager.load_plan(args.batch)
    except FileNotFoundError:
        print(f"Error: Batch not found: {args.batch}", file=sys.stderr)
        return 1

    # Normalize path (strip leading ./ or /)
    target_path = args.path.lstrip("./").lstrip("/")

    # Parse kinds filter
    kinds_filter = None
    if args.kinds:
        kinds_filter = set(k.strip() for k in args.kinds.split(","))

    # Collect all outputs for this path across all tasks
    all_outputs = []
    task_ids = [t["task_id"] for t in plan["tasks"]]

    for task_id in task_ids:
        outputs = engine.query_outputs(args.batch, task_id, path_pattern=target_path)
        for output in outputs:
            # Exact path match (not substring)
            output_path = output.get("path", "").lstrip("./").lstrip("/")
            if output_path != target_path:
                continue

            # Apply kinds filter
            if kinds_filter and output.get("kind") not in kinds_filter:
                continue

            output["task_id"] = task_id
            all_outputs.append(output)

    if not all_outputs:
        print(f"No outputs found for: {args.path}")
        return 0

    # Sort outputs deterministically by (task_id, kind, then stable key)
    def sort_key(o):
        return (
            o.get("task_id", ""),
            o.get("kind", ""),
            o.get("severity", ""),
            o.get("code", ""),
            o.get("line", 0),
        )

    all_outputs.sort(key=sort_key)

    if args.json:
        # JSON output with stable key ordering
        print(render_json(all_outputs))
    else:
        # Group by kind for human display
        from collections import defaultdict

        by_kind = defaultdict(list)
        for output in all_outputs:
            by_kind[output.get("kind", "unknown")].append(output)

        print(f"Inspect: {args.path}")
        print(f"Batch: {args.batch}")
        print(f"Total outputs: {len(all_outputs)}")
        print()

        for kind in sorted(by_kind.keys()):
            outputs = by_kind[kind]
            print(f"--- {kind.upper()} ({len(outputs)}) ---")
            print()

            if kind == "diagnostic":
                # Show diagnostics with severity, code, message
                columns = [
                    Column(name="task_id", header="TASK", width=12),
                    Column(name="severity", header="SEV", width=8),
                    Column(name="code", header="CODE", width=10),
                    Column(name="line", header="LINE", width=6, align="right"),
                    Column(name="message", header="MESSAGE"),
                ]
                print(
                    render_table(
                        outputs, columns, sort_key=sort_key, color_mode=color_mode
                    )
                )
            elif kind == "metric":
                # Show metrics with name, value
                columns = [
                    Column(name="task_id", header="TASK", width=12),
                    Column(name="name", header="NAME", width=20),
                    Column(name="value", header="VALUE", width=15, align="right"),
                ]
                print(
                    render_table(
                        outputs, columns, sort_key=sort_key, color_mode=color_mode
                    )
                )
            elif kind == "symbol":
                # Show symbols with name, type
                columns = [
                    Column(name="task_id", header="TASK", width=12),
                    Column(name="name", header="NAME", width=30),
                    Column(name="type", header="TYPE", width=15),
                    Column(name="line", header="LINE", width=6, align="right"),
                ]
                print(
                    render_table(
                        outputs, columns, sort_key=sort_key, color_mode=color_mode
                    )
                )
            else:
                # Generic output display
                columns = [
                    Column(name="task_id", header="TASK", width=12),
                    Column(name="kind", header="KIND", width=15),
                ]
                print(
                    render_table(
                        outputs, columns, sort_key=sort_key, color_mode=color_mode
                    )
                )

            print()

    return 0


# --- Explain system ---

# Command metadata for explain functionality
_COMMAND_EXPLAIN_INFO = {
    "inspect": {
        "description": "Show all outputs for a specific file path",
        "data_sources": [
            "outputs.index.jsonl (per shard)",
        ],
        "output_kinds_used": ["diagnostic", "metric", "symbol", "ast"],
        "tasks_referenced": "all tasks in batch plan",
        "filters": ["path (exact match)", "kinds (optional)"],
        "grouping": "by output kind",
        "notes": [
            "Reads from batch outputs only",
            "Does NOT use events",
            "Does NOT modify the store",
        ],
    },
    "diff": {
        "description": "Compare outputs between two batches",
        "data_sources": [
            "outputs.index.jsonl (per shard, both batches)",
        ],
        "output_kinds_used": ["diagnostic", "metric", "symbol"],
        "tasks_referenced": "all tasks in both batch plans",
        "filters": ["kind (optional)"],
        "grouping": "by change type (added/removed/changed)",
        "notes": [
            "Pure set math on output records",
            "Does NOT use events",
            "Does NOT modify the store",
        ],
    },
    "regressions": {
        "description": "Show diagnostics that worsened between batches",
        "data_sources": [
            "outputs.index.jsonl (diagnostics only)",
        ],
        "output_kinds_used": ["diagnostic"],
        "tasks_referenced": "all tasks in both batch plans",
        "filters": ["severity comparison"],
        "grouping": "by file path",
        "notes": [
            "Regression = diagnostic added or severity increased",
            "Does NOT use events",
            "Does NOT modify the store",
        ],
    },
    "improvements": {
        "description": "Show diagnostics that improved between batches",
        "data_sources": [
            "outputs.index.jsonl (diagnostics only)",
        ],
        "output_kinds_used": ["diagnostic"],
        "tasks_referenced": "all tasks in both batch plans",
        "filters": ["severity comparison"],
        "grouping": "by file path",
        "notes": [
            "Improvement = diagnostic removed or severity decreased",
            "Does NOT use events",
            "Does NOT modify the store",
        ],
    },
    "summary": {
        "description": "Show human summary of batch outputs",
        "data_sources": [
            "outputs.index.jsonl (per shard)",
        ],
        "output_kinds_used": ["diagnostic", "metric", "symbol"],
        "tasks_referenced": "all tasks (or filtered by --task)",
        "filters": ["task (optional)"],
        "grouping": "by output kind",
        "notes": [
            "Aggregates counts by kind",
            "Does NOT use events",
            "Does NOT modify the store",
        ],
    },
}


def get_explain_info(command: str) -> dict:
    """Get explain information for a command.

    Args:
        command: Command name (e.g., 'inspect', 'diff').

    Returns:
        Dict with explain information.
    """
    if command in _COMMAND_EXPLAIN_INFO:
        info = _COMMAND_EXPLAIN_INFO[command].copy()
        info["command"] = command
        return info

    return {
        "command": command,
        "description": f"Unknown command: {command}",
        "data_sources": [],
        "output_kinds_used": [],
        "tasks_referenced": "unknown",
        "filters": [],
        "grouping": "unknown",
        "notes": [],
    }


def print_explain(info: dict) -> None:
    """Print explain information in human-readable format.

    Args:
        info: Explain info dict.
    """
    print(f"Command: {info['command']}")
    print(f"Description: {info['description']}")
    print()
    print("Data Sources:")
    for src in info.get("data_sources", []):
        print(f"  - {src}")
    print()
    print("Output Kinds Used:")
    for kind in info.get("output_kinds_used", []):
        print(f"  - {kind}")
    print()
    print(f"Tasks Referenced: {info.get('tasks_referenced', 'unknown')}")
    print()
    print("Filters/Parameters:")
    for f in info.get("filters", []):
        print(f"  - {f}")
    print()
    print(f"Grouping: {info.get('grouping', 'none')}")
    print()
    print("Notes:")
    for note in info.get("notes", []):
        print(f"  - {note}")


def cmd_explain(args: argparse.Namespace) -> int:
    """Handle the explain command (Phase 6).

    Shows data sources and processing logic for a command.
    """
    from .ui import render_json

    info = get_explain_info(args.subcommand)

    if args.json:
        print(render_json(info))
    else:
        print_explain(info)

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Handle the diff command (Phase 6).

    Compares outputs between two batches.
    Read-only: does not modify the store.
    """
    from .ui import ColorMode, render_json, render_table, Column
    from .ui.diff import diff_batches

    # Handle --explain mode
    if getattr(args, "explain", False):
        info = get_explain_info("diff")
        if args.json:
            print(render_json(info))
        else:
            print_explain(info)
        return 0

    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    color_mode = ColorMode.NEVER if args.no_color else ColorMode.AUTO

    try:
        result = diff_batches(
            store_root,
            args.batch_a,
            args.batch_b,
            kind_filter=args.kind,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(render_json(result.to_dict()))
    else:
        print(f"Diff: {args.batch_a} -> {args.batch_b}")
        print()
        print(f"  Added:   {len(result.added)}")
        print(f"  Removed: {len(result.removed)}")
        print(f"  Changed: {len(result.changed)}")
        print()

        if result.added:
            print("--- ADDED ---")
            columns = [
                Column(name="kind", header="KIND", width=12),
                Column(name="path", header="PATH"),
            ]
            print(
                render_table(
                    result.added, columns, sort_key="path", color_mode=color_mode
                )
            )
            print()

        if result.removed:
            print("--- REMOVED ---")
            columns = [
                Column(name="kind", header="KIND", width=12),
                Column(name="path", header="PATH"),
            ]
            print(
                render_table(
                    result.removed, columns, sort_key="path", color_mode=color_mode
                )
            )
            print()

        if result.changed:
            print("--- CHANGED ---")
            # Show changed items (flatten to show new values)
            changed_rows = [new for old, new in result.changed]
            columns = [
                Column(name="kind", header="KIND", width=12),
                Column(name="path", header="PATH"),
            ]
            print(
                render_table(
                    changed_rows, columns, sort_key="path", color_mode=color_mode
                )
            )
            print()

    return 0


def cmd_regressions(args: argparse.Namespace) -> int:
    """Handle the regressions command (Phase 6).

    Shows diagnostics that worsened between batches.
    Read-only: does not modify the store.
    """
    from .ui import ColorMode, render_json, render_table, Column
    from .ui.diff import diff_diagnostics

    # Handle --explain mode
    if getattr(args, "explain", False):
        info = get_explain_info("regressions")
        if args.json:
            print(render_json(info))
        else:
            print_explain(info)
        return 0

    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    color_mode = ColorMode.NEVER if args.no_color else ColorMode.AUTO

    try:
        delta = diff_diagnostics(store_root, args.batch_a, args.batch_b)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(
            render_json(
                {
                    "regressions": delta.regressions,
                    "count": len(delta.regressions),
                }
            )
        )
    else:
        print(f"Regressions: {args.batch_a} -> {args.batch_b}")
        print()

        if not delta.regressions:
            print("No regressions found.")
        else:
            print(f"Found {len(delta.regressions)} regressions:")
            print()
            columns = [
                Column(name="severity", header="SEV", width=8),
                Column(name="code", header="CODE", width=10),
                Column(name="path", header="PATH"),
                Column(name="line", header="LINE", width=6, align="right"),
            ]
            print(
                render_table(
                    delta.regressions, columns, sort_key="path", color_mode=color_mode
                )
            )

    return 0


def cmd_improvements(args: argparse.Namespace) -> int:
    """Handle the improvements command (Phase 6).

    Shows diagnostics that improved between batches.
    Read-only: does not modify the store.
    """
    from .ui import ColorMode, render_json, render_table, Column
    from .ui.diff import diff_diagnostics

    # Handle --explain mode
    if getattr(args, "explain", False):
        info = get_explain_info("improvements")
        if args.json:
            print(render_json(info))
        else:
            print_explain(info)
        return 0

    store_root = Path(args.store)

    if not store_root.exists():
        print(f"Error: Store does not exist: {store_root}", file=sys.stderr)
        return 1

    color_mode = ColorMode.NEVER if args.no_color else ColorMode.AUTO

    try:
        delta = diff_diagnostics(store_root, args.batch_a, args.batch_b)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(
            render_json(
                {
                    "improvements": delta.improvements,
                    "count": len(delta.improvements),
                }
            )
        )
    else:
        print(f"Improvements: {args.batch_a} -> {args.batch_b}")
        print()

        if not delta.improvements:
            print("No improvements found.")
        else:
            print(f"Found {len(delta.improvements)} improvements:")
            print()
            columns = [
                Column(name="severity", header="SEV", width=8),
                Column(name="code", header="CODE", width=10),
                Column(name="path", header="PATH"),
                Column(name="line", header="LINE", width=6, align="right"),
            ]
            print(
                render_table(
                    delta.improvements, columns, sort_key="path", color_mode=color_mode
                )
            )

    return 0


# =============================================================================
# Phase 7: Integration API
# =============================================================================


def get_api_info() -> dict:
    """Get API capability information.

    Returns a deterministic, byte-stable representation of CodeBatch
    capabilities for integration purposes.

    Returns:
        API info dict with schema_name, schema_version, producer, build,
        commands, pipelines, tasks, and output_kinds.
    """
    import platform
    import sys as _sys

    from .common import VERSION, SCHEMA_VERSION
    from .registry import (
        list_commands,
        list_tasks,
        list_output_kinds,
    )

    # Detect available features (semi-dynamic)
    features = {}

    # Phase 5 workflow
    try:
        import importlib.util
        if importlib.util.find_spec("codebatch.workflow"):
            features["phase5_workflow"] = True
        else:
            features["phase5_workflow"] = False
    except ImportError:
        features["phase5_workflow"] = False

    # Phase 6 UI
    try:
        import importlib.util
        if importlib.util.find_spec("codebatch.ui"):
            features["phase6_ui"] = True
        else:
            features["phase6_ui"] = False
    except ImportError:
        features["phase6_ui"] = False

    # Diff engine
    try:
        import importlib.util
        if importlib.util.find_spec("codebatch.ui.diff"):
            features["diff"] = True
        else:
            features["diff"] = False
    except ImportError:
        features["diff"] = False

    # Cache (future)
    try:
        import importlib.util
        if importlib.util.find_spec("codebatch.cache"):
            features["cache"] = True
        else:
            features["cache"] = False
    except ImportError:
        features["cache"] = False

    # Build commands list (sorted by name)
    commands = []
    for cmd in list_commands():
        commands.append(
            {
                "name": cmd.name,
                "description": cmd.description,
                "read_only": cmd.read_only,
                "supports_json": cmd.supports_json,
                "supports_explain": cmd.supports_explain,
                "requires_store": cmd.requires_store,
                "requires_batch": cmd.requires_batch,
                "since": cmd.since,
                "group": cmd.group,
            }
        )

    # Build pipelines list (sorted by name)
    pipelines = []
    for name in sorted(PIPELINES.keys()):
        pipeline_def = PIPELINES[name]
        tasks_list = []
        for task_def in pipeline_def["tasks"]:
            tasks_list.append(
                {
                    "task_id": task_def["task_id"],
                    "deps": task_def.get("depends_on", []),
                }
            )
        pipelines.append(
            {
                "name": name,
                "description": pipeline_def.get("description", ""),
                "tasks": tasks_list,
            }
        )

    # Build tasks list (sorted by task_id)
    tasks = []
    for task in list_tasks():
        tasks.append(
            {
                "task_id": task.task_id,
                "type": task.task_type,
                "description": task.description,
                "kinds_out": list(task.kinds_out),
                "deps": list(task.deps),
            }
        )

    # Build output kinds list (sorted by kind)
    output_kinds = []
    for ok in list_output_kinds():
        output_kinds.append(
            {
                "kind": ok.kind,
                "description": ok.description,
                "canonical_key": list(ok.canonical_key),
            }
        )

    return {
        "schema_name": "codebatch.api",
        "schema_version": 1,
        "producer": {
            "name": "codebatch",
            "version": VERSION,
        },
        "build": {
            "platform": _sys.platform,
            "python": platform.python_version(),
            "schema_version": SCHEMA_VERSION,
            "features": features,
        },
        "commands": commands,
        "pipelines": pipelines,
        "tasks": tasks,
        "output_kinds": output_kinds,
    }


def cmd_api(args: argparse.Namespace) -> int:
    """Handle the api command (Phase 7).

    Shows API capabilities and metadata for integration.
    Read-only: does not require or modify the store.
    No side effects: works without any arguments.
    """
    info = get_api_info()

    if args.json:
        # Use sorted keys for deterministic output
        print(json.dumps(info, indent=2, sort_keys=False))
    else:
        # Human-readable output
        print(f"CodeBatch API v{info['schema_version']}")
        print(f"Producer: {info['producer']['name']} {info['producer']['version']}")
        print(f"Platform: {info['build']['platform']}")
        print(f"Python: {info['build']['python']}")
        print()

        # Features
        print("Features:")
        for feat, enabled in sorted(info["build"]["features"].items()):
            status = "[x]" if enabled else "[ ]"
            print(f"  {status} {feat}")
        print()

        # Commands
        print(f"Commands ({len(info['commands'])}):")
        for cmd in info["commands"][:10]:  # Show first 10
            flags = []
            if cmd["read_only"]:
                flags.append("RO")
            if cmd["supports_json"]:
                flags.append("JSON")
            flag_str = f" [{','.join(flags)}]" if flags else ""
            print(f"  {cmd['name']:<20} {cmd['description'][:40]}{flag_str}")
        if len(info["commands"]) > 10:
            print(f"  ... and {len(info['commands']) - 10} more")
        print()

        # Pipelines
        print(f"Pipelines ({len(info['pipelines'])}):")
        for pipeline in info["pipelines"]:
            task_ids = [t["task_id"] for t in pipeline["tasks"]]
            print(f"  {pipeline['name']:<15} {' -> '.join(task_ids)}")
        print()

        # Output kinds
        print(f"Output Kinds ({len(info['output_kinds'])}):")
        for ok in info["output_kinds"]:
            print(f"  {ok['kind']:<12} {ok['description']}")
        print()

        print("Tip: Use --json for machine-readable output")

    return 0


def get_diagnose_info(store_root: Path) -> dict:
    """Get diagnostic information about a store.

    Verifies:
    - Store structure is valid
    - Schema version is compatible
    - Snapshots are accessible
    - Batches are accessible

    Returns:
        Diagnostic info dict with checks and results.
    """
    from .common import VERSION, SCHEMA_VERSION
    from .batch import BatchManager
    from .snapshot import SnapshotBuilder

    checks = []
    issues = []
    warnings = []

    # Check 1: Store exists
    store_exists = store_root.exists()
    checks.append(
        {
            "name": "store_exists",
            "passed": store_exists,
            "message": "Store directory exists"
            if store_exists
            else "Store directory not found",
        }
    )

    if not store_exists:
        return {
            "schema_name": "codebatch.diagnose",
            "schema_version": 1,
            "store": str(store_root),
            "status": "error",
            "checks": checks,
            "issues": [
                {"severity": "error", "message": f"Store not found: {store_root}"}
            ],
            "warnings": [],
            "summary": {"total_checks": 1, "passed": 0, "failed": 1},
        }

    # Check 2: store.json exists and is valid
    store_json = store_root / "store.json"
    store_json_valid = False
    store_meta = None

    if store_json.exists():
        try:
            with open(store_json) as f:
                store_meta = json.load(f)
            store_json_valid = True
        except (json.JSONDecodeError, OSError):
            pass

    checks.append(
        {
            "name": "store_json_valid",
            "passed": store_json_valid,
            "message": "store.json is valid"
            if store_json_valid
            else "store.json is missing or invalid",
        }
    )

    if not store_json_valid:
        issues.append(
            {"severity": "error", "message": "store.json is missing or invalid"}
        )

    # Check 3: Schema version compatibility
    schema_compatible = False
    if store_meta:
        store_schema = store_meta.get("schema_version", 0)
        schema_compatible = store_schema == SCHEMA_VERSION
        if not schema_compatible:
            issues.append(
                {
                    "severity": "error",
                    "message": f"Schema version mismatch: store has {store_schema}, expected {SCHEMA_VERSION}",
                }
            )

    checks.append(
        {
            "name": "schema_compatible",
            "passed": schema_compatible,
            "message": f"Schema version {SCHEMA_VERSION}"
            if schema_compatible
            else "Schema version mismatch",
        }
    )

    # Check 4: Required directories exist
    required_dirs = ["objects", "snapshots", "batches"]
    dirs_exist = all((store_root / d).is_dir() for d in required_dirs)

    checks.append(
        {
            "name": "required_dirs_exist",
            "passed": dirs_exist,
            "message": "Required directories exist"
            if dirs_exist
            else "Missing required directories",
        }
    )

    if not dirs_exist:
        missing = [d for d in required_dirs if not (store_root / d).is_dir()]
        issues.append(
            {
                "severity": "error",
                "message": f"Missing directories: {', '.join(missing)}",
            }
        )

    # Check 5: Snapshots accessible
    snapshots_ok = False
    snapshot_count = 0
    try:
        builder = SnapshotBuilder(store_root)
        snapshots = builder.list_snapshots()
        snapshot_count = len(snapshots)
        snapshots_ok = True
    except Exception as e:
        issues.append({"severity": "warning", "message": f"Cannot list snapshots: {e}"})

    checks.append(
        {
            "name": "snapshots_accessible",
            "passed": snapshots_ok,
            "message": f"Found {snapshot_count} snapshots"
            if snapshots_ok
            else "Cannot access snapshots",
        }
    )

    # Check 6: Batches accessible
    batches_ok = False
    batch_count = 0
    try:
        manager = BatchManager(store_root)
        batches = manager.list_batches()
        batch_count = len(batches)
        batches_ok = True
    except Exception as e:
        issues.append({"severity": "warning", "message": f"Cannot list batches: {e}"})

    checks.append(
        {
            "name": "batches_accessible",
            "passed": batches_ok,
            "message": f"Found {batch_count} batches"
            if batches_ok
            else "Cannot access batches",
        }
    )

    # Summary
    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed

    status = "ok" if failed == 0 else ("warning" if not issues else "error")

    return {
        "schema_name": "codebatch.diagnose",
        "schema_version": 1,
        "store": str(store_root),
        "status": status,
        "codebatch_version": VERSION,
        "store_schema_version": store_meta.get("schema_version")
        if store_meta
        else None,
        "expected_schema_version": SCHEMA_VERSION,
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
        "summary": {
            "total_checks": len(checks),
            "passed": passed,
            "failed": failed,
            "snapshots": snapshot_count,
            "batches": batch_count,
        },
    }


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Handle the diagnose command (Phase 7).

    Verifies store integrity and compatibility.
    Read-only: does not modify the store.
    """
    store_root = Path(args.store)

    info = get_diagnose_info(store_root)

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        # Human-readable output
        status_icon = {
            "ok": "[OK]",
            "warning": "[WARN]",
            "error": "[FAIL]",
        }.get(info["status"], "[?]")

        print(f"Diagnose: {info['store']}")
        print(f"Status: {status_icon} {info['status'].upper()}")
        print()

        print("Checks:")
        for check in info["checks"]:
            icon = "[x]" if check["passed"] else "[ ]"
            print(f"  {icon} {check['name']}: {check['message']}")
        print()

        if info["issues"]:
            print("Issues:")
            for issue in info["issues"]:
                sev = issue["severity"].upper()
                print(f"  [{sev}] {issue['message']}")
            print()

        summary = info["summary"]
        print(f"Summary: {summary['passed']}/{summary['total_checks']} checks passed")
        if summary.get("snapshots") is not None:
            print(f"  Snapshots: {summary['snapshots']}")
        if summary.get("batches") is not None:
            print(f"  Batches: {summary['batches']}")

    # Return non-zero if there are errors
    return 0 if info["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
