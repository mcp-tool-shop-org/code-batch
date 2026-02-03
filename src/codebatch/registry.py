"""Command and task registry for integration API.

This module provides metadata for CLI commands and tasks that can be
introspected by the `api` command. Metadata is defined statically to
ensure deterministic, byte-stable output.

Phase 7: Integration API
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class CommandMeta:
    """Metadata for a CLI command.

    Attributes:
        name: Command name as used on CLI.
        description: Short description of what the command does.
        read_only: True if command never modifies the store.
        supports_json: True if command has --json output.
        supports_explain: True if command has --explain flag.
        requires_store: True if command needs --store argument.
        requires_batch: True if command needs --batch argument.
        since: Version when command was introduced.
        group: Command group for organization.
    """

    name: str
    description: str
    read_only: bool = False
    supports_json: bool = False
    supports_explain: bool = False
    requires_store: bool = False
    requires_batch: bool = False
    since: str = "0.1.0"
    group: str = "core"


@dataclass(frozen=True)
class TaskMeta:
    """Metadata for a task executor.

    Attributes:
        task_id: Unique task identifier (e.g., '01_parse').
        task_type: Task type (parse, analyze, symbols, lint).
        description: Short description of what the task does.
        kinds_out: Output kinds this task produces.
        deps: Task IDs this task depends on (empty for root tasks).
    """

    task_id: str
    task_type: str
    description: str
    kinds_out: tuple[str, ...]
    deps: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputKindMeta:
    """Metadata for an output kind.

    Attributes:
        kind: Output kind name.
        description: Short description.
        canonical_key: Fields that uniquely identify a record of this kind.
    """

    kind: str
    description: str
    canonical_key: tuple[str, ...]


# =============================================================================
# Command Registry
# =============================================================================

# Commands sorted alphabetically by dot-path name for deterministic output
# Command names use dot-delimited format: "group.action" or just "action"
# This is the canonical naming for integration clients.
COMMANDS: tuple[CommandMeta, ...] = (
    # API command (Phase 7)
    CommandMeta(
        name="api",
        description="Show API capabilities and metadata",
        read_only=True,
        supports_json=True,
        requires_store=False,
        since="0.7.0",
        group="api",
    ),
    # Batch commands
    CommandMeta(
        name="batch.init",
        description="Initialize a batch from a snapshot",
        read_only=False,
        supports_json=False,
        requires_store=True,
        since="0.1.0",
        group="batch",
    ),
    CommandMeta(
        name="batch.list",
        description="List batches in store",
        read_only=True,
        supports_json=False,
        requires_store=True,
        since="0.1.0",
        group="batch",
    ),
    CommandMeta(
        name="batch.show",
        description="Show batch details",
        read_only=True,
        supports_json=True,
        requires_store=True,
        since="0.1.0",
        group="batch",
    ),
    # Diff/comparison commands (Phase 6)
    CommandMeta(
        name="diff",
        description="Compare outputs between two batches",
        read_only=True,
        supports_json=True,
        supports_explain=True,
        requires_store=True,
        since="0.6.0",
        group="ui",
    ),
    # Errors command
    CommandMeta(
        name="errors",
        description="Show errors from a batch",
        read_only=True,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="workflow",
    ),
    # Explain command (Phase 6)
    CommandMeta(
        name="explain",
        description="Show data sources for a command",
        read_only=True,
        supports_json=True,
        requires_store=False,
        since="0.6.0",
        group="ui",
    ),
    # Files command
    CommandMeta(
        name="files",
        description="List files in a snapshot",
        read_only=True,
        supports_json=True,
        requires_store=True,
        since="0.5.0",
        group="workflow",
    ),
    # Gate commands
    CommandMeta(
        name="gate.bundle",
        description="Run a gate bundle",
        read_only=True,
        supports_json=True,
        requires_store=True,
        since="0.3.0",
        group="gate",
    ),
    CommandMeta(
        name="gate.explain",
        description="Explain a gate",
        read_only=True,
        supports_json=False,
        requires_store=False,
        since="0.3.0",
        group="gate",
    ),
    CommandMeta(
        name="gate.list",
        description="List all gates",
        read_only=True,
        supports_json=True,
        requires_store=False,
        since="0.3.0",
        group="gate",
    ),
    CommandMeta(
        name="gate.run",
        description="Run a gate",
        read_only=True,
        supports_json=True,
        requires_store=True,
        since="0.3.0",
        group="gate",
    ),
    # Improvements command (Phase 6)
    CommandMeta(
        name="improvements",
        description="Show diagnostics that improved between batches",
        read_only=True,
        supports_json=True,
        supports_explain=True,
        requires_store=True,
        since="0.6.0",
        group="ui",
    ),
    # Index commands
    CommandMeta(
        name="index.build",
        description="Build LMDB acceleration cache",
        read_only=False,
        supports_json=False,
        requires_store=True,
        requires_batch=True,
        since="0.3.0",
        group="index",
    ),
    # Init command
    CommandMeta(
        name="init",
        description="Initialize a new store",
        read_only=False,
        supports_json=False,
        requires_store=False,
        since="0.1.0",
        group="store",
    ),
    # Inspect command (Phase 6)
    CommandMeta(
        name="inspect",
        description="Show all outputs for a file",
        read_only=True,
        supports_json=True,
        supports_explain=True,
        requires_store=True,
        requires_batch=True,
        since="0.6.0",
        group="ui",
    ),
    # Pipeline commands
    CommandMeta(
        name="pipeline.list",
        description="List available pipelines",
        read_only=True,
        supports_json=True,
        requires_store=False,
        since="0.5.0",
        group="pipeline",
    ),
    CommandMeta(
        name="pipeline.show",
        description="Show pipeline details",
        read_only=True,
        supports_json=True,
        requires_store=False,
        since="0.5.0",
        group="pipeline",
    ),
    # Query command
    CommandMeta(
        name="query",
        description="Query outputs from a batch",
        read_only=True,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.1.0",
        group="query",
    ),
    # Regressions command (Phase 6)
    CommandMeta(
        name="regressions",
        description="Show diagnostics that worsened between batches",
        read_only=True,
        supports_json=True,
        supports_explain=True,
        requires_store=True,
        since="0.6.0",
        group="ui",
    ),
    # Resume command
    CommandMeta(
        name="resume",
        description="Resume batch, running only incomplete shards",
        read_only=False,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="workflow",
    ),
    # Run command
    CommandMeta(
        name="run",
        description="Run all tasks and shards in a batch",
        read_only=False,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="workflow",
    ),
    # Shard commands
    CommandMeta(
        name="shard.list",
        description="List shards for a task",
        read_only=True,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="shard",
    ),
    CommandMeta(
        name="shard.run",
        description="Run a single shard",
        read_only=False,
        supports_json=False,
        requires_store=True,
        requires_batch=True,
        since="0.1.0",
        group="shard",
    ),
    # Snapshot commands
    CommandMeta(
        name="snapshot.create",
        description="Create a snapshot from source directory",
        read_only=False,
        supports_json=False,
        requires_store=True,
        since="0.1.0",
        group="snapshot",
    ),
    CommandMeta(
        name="snapshot.list",
        description="List snapshots in store",
        read_only=True,
        supports_json=False,
        requires_store=True,
        since="0.1.0",
        group="snapshot",
    ),
    CommandMeta(
        name="snapshot.show",
        description="Show snapshot details",
        read_only=True,
        supports_json=True,
        requires_store=True,
        since="0.1.0",
        group="snapshot",
    ),
    # Status command
    CommandMeta(
        name="status",
        description="Show batch progress",
        read_only=True,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="workflow",
    ),
    # Summary command
    CommandMeta(
        name="summary",
        description="Show human summary of batch outputs",
        read_only=True,
        supports_json=True,
        supports_explain=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="workflow",
    ),
    # Task commands
    CommandMeta(
        name="task.list",
        description="List tasks in a batch",
        read_only=True,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="task",
    ),
    # Top command
    CommandMeta(
        name="top",
        description="Show top output kinds/severities",
        read_only=True,
        supports_json=True,
        requires_store=True,
        requires_batch=True,
        since="0.5.0",
        group="workflow",
    ),
    # Diagnose command (Phase 7)
    CommandMeta(
        name="diagnose",
        description="Verify store integrity and compatibility",
        read_only=True,
        supports_json=True,
        requires_store=True,
        since="0.7.0",
        group="api",
    ),
)

# =============================================================================
# Task Registry
# =============================================================================

TASKS: tuple[TaskMeta, ...] = (
    TaskMeta(
        task_id="01_parse",
        task_type="parse",
        description="Parse source files and emit AST + diagnostics",
        kinds_out=("ast", "diagnostic"),
        deps=(),
    ),
    TaskMeta(
        task_id="02_analyze",
        task_type="analyze",
        description="Analyze source files for metrics",
        kinds_out=("metric",),
        deps=("01_parse",),
    ),
    TaskMeta(
        task_id="03_symbols",
        task_type="symbols",
        description="Extract symbol definitions",
        kinds_out=("symbol",),
        deps=("01_parse",),
    ),
    TaskMeta(
        task_id="04_lint",
        task_type="lint",
        description="Run lint checks",
        kinds_out=("diagnostic",),
        deps=("01_parse",),
    ),
)


# =============================================================================
# Output Kind Registry
# =============================================================================

OUTPUT_KINDS: tuple[OutputKindMeta, ...] = (
    OutputKindMeta(
        kind="ast",
        description="Parsed AST representation",
        canonical_key=("kind", "path", "object"),
    ),
    OutputKindMeta(
        kind="diagnostic",
        description="Diagnostic message (error, warning, etc.)",
        canonical_key=("kind", "path", "line", "col", "code"),
    ),
    OutputKindMeta(
        kind="metric",
        description="Code metric (bytes, LOC, etc.)",
        canonical_key=("kind", "path", "metric"),
    ),
    OutputKindMeta(
        kind="symbol",
        description="Symbol definition (function, class, etc.)",
        canonical_key=("kind", "path", "name", "line"),
    ),
)


# =============================================================================
# Lookup Functions
# =============================================================================


def get_command(name: str) -> Optional[CommandMeta]:
    """Get command metadata by name.

    Args:
        name: Command name.

    Returns:
        CommandMeta if found, None otherwise.
    """
    for cmd in COMMANDS:
        if cmd.name == name:
            return cmd
    return None


def get_task(task_id: str) -> Optional[TaskMeta]:
    """Get task metadata by ID.

    Args:
        task_id: Task ID.

    Returns:
        TaskMeta if found, None otherwise.
    """
    for task in TASKS:
        if task.task_id == task_id:
            return task
    return None


def get_output_kind(kind: str) -> Optional[OutputKindMeta]:
    """Get output kind metadata by name.

    Args:
        kind: Output kind name.

    Returns:
        OutputKindMeta if found, None otherwise.
    """
    for ok in OUTPUT_KINDS:
        if ok.kind == kind:
            return ok
    return None


def list_commands(group: Optional[str] = None) -> list[CommandMeta]:
    """List commands, optionally filtered by group.

    Args:
        group: Filter by group name (optional).

    Returns:
        List of CommandMeta sorted by name.
    """
    cmds = list(COMMANDS)
    if group:
        cmds = [c for c in cmds if c.group == group]
    return sorted(cmds, key=lambda c: c.name)


def list_tasks() -> list[TaskMeta]:
    """List all tasks sorted by task_id.

    Returns:
        List of TaskMeta sorted by task_id.
    """
    return sorted(TASKS, key=lambda t: t.task_id)


def list_output_kinds() -> list[OutputKindMeta]:
    """List all output kinds sorted by kind name.

    Returns:
        List of OutputKindMeta sorted by kind.
    """
    return sorted(OUTPUT_KINDS, key=lambda o: o.kind)
