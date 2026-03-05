---
title: Commands
description: Low-level CLI commands for fine-grained control over shards, queries, and indexing.
sidebar:
  order: 3
---

In addition to the high-level workflow commands covered in [Getting Started](/code-batch/handbook/getting-started/) and [Usage](/code-batch/handbook/usage/), Code Batch exposes low-level primitives for fine-grained control. These are useful for custom scripts, debugging, and advanced workflows.

## High-level commands (Phase 5)

These compose the low-level primitives into human-friendly workflows:

| Command | Description |
|---------|-------------|
| `codebatch init <path>` | Initialize a filesystem store at the given path |
| `codebatch snapshot <dir> --store <path>` | Create an immutable content-addressed snapshot of a directory |
| `codebatch pipelines` | List all available pipelines |
| `codebatch pipeline <name>` | Show details for a specific pipeline |
| `codebatch batch init --snapshot <id> --pipeline <name> --store <path>` | Initialize a batch from a snapshot and pipeline |
| `codebatch run --batch <id> --store <path>` | Run all tasks and shards in a batch |
| `codebatch resume --batch <id> --store <path>` | Resume an interrupted batch from where it stopped |
| `codebatch status --batch <id> --store <path>` | Show per-shard progress across all tasks |
| `codebatch summary --batch <id> --store <path>` | Show a high-level output summary |

## Discoverability commands

| Command | Description |
|---------|-------------|
| `codebatch tasks --batch <id> --store <path>` | List tasks in a batch |
| `codebatch shards --batch <id> --task <name> --store <path>` | List shards for a specific task |

## Query aliases

| Command | Description |
|---------|-------------|
| `codebatch errors --batch <id> --store <path>` | Show all error-kind outputs |
| `codebatch files --batch <id> --store <path>` | List files in the batch's snapshot |
| `codebatch top --batch <id> --store <path>` | Ranked count of output kinds |

## Exploration and comparison (Phase 6)

| Command | Description |
|---------|-------------|
| `codebatch inspect <file> --batch <id> --store <path>` | Inspect all outputs for a specific file |
| `codebatch inspect <file> --batch <id> --store <path> --explain` | Same as inspect, with data source annotations |
| `codebatch diff <batchA> <batchB> --store <path>` | Compare outputs between two batches |
| `codebatch regressions <batchA> <batchB> --store <path>` | Show new or worsened diagnostics |
| `codebatch improvements <batchA> <batchB> --store <path>` | Show fixed or improved diagnostics |

## Low-level commands

These are the underlying primitives that the high-level commands compose. Use them when you need exact control over execution.

### Run a single shard

Execute one specific shard of one specific task:

```bash
codebatch run-shard --batch <id> --task 01_parse --shard ab --store ./store
```

This is the atomic unit of execution. The high-level `run` command calls `run-shard` for every shard in every task, in pipeline order. Running shards individually is useful for:

- **Debugging** a specific shard that failed
- **Parallel execution** using external orchestration (e.g. GNU parallel, CI matrix jobs)
- **Selective re-runs** when only one shard needs to be re-executed

### Query outputs

Query structured output records from completed shards:

```bash
codebatch query outputs --batch <id> --task 01_parse --store ./store
```

This returns raw JSON output records for the specified task. You can filter by task to narrow the scope. The query aliases (`errors`, `files`, `top`) are built on top of this primitive.

### Query diagnostics

Query diagnostic-kind output records specifically:

```bash
codebatch query diagnostics --batch <id> --task 01_parse --store ./store
```

Diagnostics include warnings, errors, hints, and informational messages produced by analysis tasks.

### Build LMDB acceleration index

For large stores with many batches and outputs, build an LMDB index to accelerate queries:

```bash
codebatch index-build --batch <id> --store ./store
```

The LMDB index is optional. Without it, Code Batch scans the filesystem directly, which is fine for small to medium stores. The index becomes valuable when you have:

- Thousands of output records per batch
- Frequent queries against the same batch
- Multiple users querying the same store

The index is a cache — it can be rebuilt at any time from the filesystem records.

## Spec versioning

The Code Batch specification uses semantic versioning with draft/stable markers. Key points:

- Each version is tagged in git (e.g. `spec-v1.0-draft`)
- Breaking changes increment the major version
- Implementations should declare which spec version they target
- Unknown fields should be tolerated for forward compatibility

This means you can upgrade Code Batch and continue reading stores written by older versions. New fields may appear in output records, but existing fields retain their meaning.

## Common flags

Most commands share these flags:

| Flag | Description |
|------|-------------|
| `--store <path>` | Path to the filesystem store (required for most commands) |
| `--batch <id>` | Batch ID to operate on |
| `--task <name>` | Task name within a batch (e.g. `01_parse`) |
| `--explain` | Annotate output with source task, shard, and record path |

## Next steps

- Review [project structure and security scope](/code-batch/handbook/reference/)
- Return to the [handbook index](/code-batch/handbook/)
