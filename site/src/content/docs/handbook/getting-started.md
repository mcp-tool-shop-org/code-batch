---
title: Getting Started
description: Install Code Batch, create a store, snapshot a project, and run your first batch.
sidebar:
  order: 1
---

This page walks you through installing Code Batch and running a complete batch workflow from scratch.

## Installation

Code Batch is distributed as a Python package:

```bash
pip install codebatch
```

Verify the installation:

```bash
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

Snapshots are **immutable**. Once created, a snapshot never changes. You can safely reference it weeks or months later and know it points to the exact same code.

## Choose a pipeline

Pipelines define what work to perform on a snapshot. List the available pipelines:

```bash
codebatch pipelines
```

Inspect a specific pipeline to see its tasks:

```bash
codebatch pipeline full
```

The `full` pipeline is the default and includes tasks like parsing, analysis, symbol extraction, and linting. Each task runs in order, and each task is sharded across the files in your snapshot.

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

This is the Phase 5 high-level command. It iterates through every task in pipeline order, executes each shard, and writes structured output records. You do not need to manage individual shards manually.

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
