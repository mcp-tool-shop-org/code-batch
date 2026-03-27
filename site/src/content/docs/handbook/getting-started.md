---
title: Getting Started
description: Install Code Batch, create a store, snapshot a project, and run your first batch.
sidebar:
  order: 1
---

This page walks you through installing Code Batch and running a complete batch workflow from scratch.

## Installation

Code Batch requires **Python 3.10 or later** and is distributed as a Python package:

```bash
pip install codebatch
```

For optional tree-sitter-based parsing (JavaScript/TypeScript AST support), install with extras:

```bash
pip install codebatch[treesitter]
```

Verify the installation:

```bash
codebatch --version
codebatch --help
```

## Create a store

A **store** is the root directory where Code Batch keeps all snapshots, batches, outputs, and indexes. Initialize one with:

```bash
codebatch init ./store
```

This creates the store structure on disk. You can place the store anywhere — next to your project, in a shared location, or on a separate volume. All subsequent commands reference this store with the `--store` flag.

## Snapshot a project

A **snapshot** captures the exact state of a source directory. Every file is content-addressed using SHA-256, so the resulting snapshot ID is deterministic — the same directory contents always produce the same ID.

```bash
codebatch snapshot ./my-project --store ./store
```

The command prints the snapshot ID. Save this — you will use it to initialize batches.

You can optionally provide a custom snapshot ID with `--id` or attach JSON metadata with `--metadata`:

```bash
codebatch snapshot ./my-project --store ./store --id my-release-v2 --metadata '{"branch": "main"}'
```

Snapshots are **immutable**. Once created, a snapshot never changes. You can safely reference it weeks or months later and know it points to the exact same code.

To list or inspect existing snapshots:

```bash
codebatch snapshot-list --store ./store
codebatch snapshot-show <id> --store ./store --files
```

## Choose a pipeline

Pipelines define what work to perform on a snapshot. List the available pipelines:

```bash
codebatch pipelines
```

Inspect a specific pipeline to see its tasks:

```bash
codebatch pipeline full
```

Code Batch ships with three built-in pipelines:

- **`parse`** — Parse source files and emit AST and diagnostics
- **`analyze`** — Parse and analyze source files (parse + analysis)
- **`full`** — Complete pipeline: parse, analyze, symbols, and lint

Each task runs in order, respecting dependencies, and each task is sharded across the files in your snapshot.

## Initialize a batch

A **batch** pairs a snapshot with a pipeline. Initialize one:

```bash
codebatch batch init --snapshot <id> --pipeline full --store ./store
```

Replace `<id>` with your snapshot ID. This creates the batch structure — task directories, shard assignments — but does not execute anything yet.

## Run the batch

Execute all tasks and shards:

```bash
codebatch run --batch <id> --store ./store
```

This iterates through every task in pipeline order, executes each shard, and writes structured output records. You do not need to manage individual shards manually.

To run only a specific task within the batch:

```bash
codebatch run --batch <id> --task 01_parse --store ./store
```

## Check progress

While a batch is running (or after it completes), check progress:

```bash
codebatch status --batch <id> --store ./store
```

This shows per-shard progress across all tasks — how many shards are pending, running, completed, or failed.

## View the summary

After a batch completes, get a high-level summary:

```bash
codebatch summary --batch <id> --store ./store
```

The summary includes total counts by output kind, timing information, and any failures.

## Resume an interrupted batch

If a batch is interrupted (Ctrl+C, crash, machine restart), resume it from exactly where it stopped:

```bash
codebatch resume --batch <id> --store ./store
```

Completed shards are skipped. Only pending and failed shards are re-executed. Because sharding is deterministic, the resumed execution produces the same results as an uninterrupted run.

## Complete workflow example

Here is the full sequence from install to query:

```bash
# Install
pip install codebatch

# Initialize store
codebatch init ./store

# Snapshot your project
codebatch snapshot ./my-project --store ./store
# → prints snapshot ID, e.g. abc123

# See available pipelines
codebatch pipelines

# Create a batch
codebatch batch init --snapshot abc123 --pipeline full --store ./store
# → prints batch ID, e.g. batch-001

# Run everything
codebatch run --batch batch-001 --store ./store

# Check progress
codebatch status --batch batch-001 --store ./store

# View summary
codebatch summary --batch batch-001 --store ./store

# Query errors
codebatch errors --batch batch-001 --store ./store
```

## Next steps

- Learn about [discoverability, query aliases, and batch comparison](/code-batch/handbook/usage/)
- See the full [CLI command reference](/code-batch/handbook/commands/)
- Understand [project structure and security scope](/code-batch/handbook/reference/)
- New to batch processing? Read the [Beginners guide](/code-batch/handbook/beginners/)
