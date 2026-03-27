---
title: Beginners
description: New to Code Batch? Start here for a gentle introduction, prerequisites, and your first steps.
sidebar:
  order: 99
---

This page is written for developers who have never used Code Batch before. It covers what the tool does, who it is for, how to get started in under five minutes, and common pitfalls to avoid.

## What is this tool?

Code Batch is a command-line tool that runs deterministic analysis pipelines over your source code. You point it at a directory, it snapshots every file using content-addressed hashing (SHA-256), then runs a series of analysis tasks -- parsing, static analysis, symbol extraction, and linting -- across deterministic shards of those files. Every output is a structured JSON record that you can query, compare, and audit.

The key guarantee is **reproducibility**: the same source files, run through the same pipeline, always produce byte-identical results. There is no database, no server process, and no network dependency. Everything lives on your filesystem as plain files and directories.

Code Batch is useful when you need to:

- Analyze a codebase and get structured, queryable results instead of log files
- Compare analysis results across different versions of your code
- Build CI gates that detect regressions between builds
- Run batch transformations that can be interrupted and resumed without losing progress

## Who is this for?

Code Batch is designed for:

- **Backend and infrastructure developers** who build or maintain code analysis pipelines
- **CI/CD engineers** who need deterministic, diffable quality gates
- **Team leads** tracking code quality trends across releases
- **Tool builders** who want a structured substrate for custom code analysis

You do **not** need Code Batch if you only need a single linter or formatter. Tools like ESLint, Ruff, or Prettier are better for that. Code Batch is for when you need to orchestrate multiple analysis steps, track results over time, and compare runs systematically.

## Prerequisites

Before installing Code Batch, make sure you have:

- **Python 3.10 or later** — Check with `python --version` or `python3 --version`
- **pip** — The Python package installer (ships with Python)
- **A terminal** — Any shell (bash, zsh, PowerShell, cmd) works
- **Disk space** — Code Batch copies source files into the store during snapshotting. Budget roughly 2x the size of your source directory for the store.

Optional:

- **tree-sitter bindings** — For JavaScript/TypeScript AST parsing, install with `pip install codebatch[treesitter]`
- **LMDB** — The `lmdb` Python package is a required dependency and is installed automatically

## Your first 5 minutes

Follow these steps to go from zero to your first batch result.

### 1. Install Code Batch

```bash
pip install codebatch
codebatch --version
```

### 2. Create a store

A store is where Code Batch keeps all its data. Pick any empty directory:

```bash
codebatch init ./my-store
```

### 3. Snapshot a project

Point Code Batch at any source directory. It hashes every file and creates an immutable snapshot:

```bash
codebatch snapshot ./my-project --store ./my-store
```

The command prints a snapshot ID (e.g. `snap-20260326-143022-a1b2c3d4`). Copy this -- you need it next.

### 4. Create and run a batch

A batch pairs a snapshot with a pipeline. Start with the `parse` pipeline (fastest):

```bash
codebatch batch init --snapshot <your-snapshot-id> --pipeline parse --store ./my-store
```

This prints a batch ID. Now run it:

```bash
codebatch run --batch <your-batch-id> --store ./my-store
```

### 5. See what happened

```bash
# High-level summary
codebatch summary --batch <your-batch-id> --store ./my-store

# Any errors found?
codebatch errors --batch <your-batch-id> --store ./my-store

# What output kinds were produced?
codebatch top --batch <your-batch-id> --store ./my-store
```

That is it. You have snapshotted a project, run an analysis pipeline, and queried the results -- all without a database, server, or network connection.

## Common mistakes

### Forgetting to initialize the store

Every command that writes data needs a store. If you see `Store does not exist`, you need to run `codebatch init <path>` first.

### Using the wrong snapshot or batch ID

IDs are long and auto-generated. Use `codebatch snapshot-list --store ./my-store` or `codebatch batch-list --store ./my-store` to see what exists. Copy-paste IDs rather than typing them.

### Running the full pipeline on a large codebase first

The `full` pipeline runs four tasks (parse, analyze, symbols, lint). For your first run, use the `parse` pipeline to verify everything works before scaling up.

### Not specifying `--store` on every command

Almost every command requires `--store <path>`. The store is not auto-detected from the current directory -- you must always pass it explicitly.

### Expecting real-time output during long runs

Code Batch writes structured JSON records, not streaming logs. Use `codebatch status --batch <id> --store ./my-store` to check progress while a batch is running. Add `-v` (verbose) to the `run` command for per-shard progress output.

## Next steps

Once you are comfortable with the basics:

- **Try the `full` pipeline** — `codebatch batch init --snapshot <id> --pipeline full --store ./my-store` to run all four analysis tasks
- **Compare two runs** — Snapshot your code, make changes, snapshot again, run both, then use `codebatch diff <batchA> <batchB> --store ./my-store` to see what changed
- **Check for regressions** — `codebatch regressions <old-batch> <new-batch> --store ./my-store` shows new or worsened diagnostics
- **Inspect a specific file** — `codebatch inspect src/main.py --batch <id> --store ./my-store` shows every output record for that file
- **Explore gates** — `codebatch gate-list` shows the built-in quality checks you can run against your store
- **Read the full [Usage guide](/code-batch/handbook/usage/)** for query aliases, comparison workflows, and CI integration patterns
- **Read the [Commands reference](/code-batch/handbook/commands/)** for the complete CLI

## Glossary

| Term | Definition |
|------|------------|
| **Store** | A filesystem directory that holds all snapshots, batches, outputs, and indexes. Created with `codebatch init`. |
| **Snapshot** | An immutable, content-addressed capture of a source directory. Every file is hashed with SHA-256. The snapshot ID is deterministic -- same files always produce the same ID. |
| **Batch** | A unit of execution that pairs a snapshot with a pipeline. Contains tasks and their shard results. |
| **Pipeline** | An ordered sequence of tasks that define what analysis to perform. Built-in pipelines: `parse`, `analyze`, `full`. |
| **Task** | A single processing step within a pipeline (e.g. `01_parse`, `02_analyze`, `03_symbols`, `04_lint`). Tasks have dependencies and execute in order. |
| **Shard** | A deterministic partition of files within a task. File-to-shard assignment is a pure function of file paths, so the same input always produces the same shards. Shards execute in isolation. |
| **Output record** | A structured JSON document produced by a shard. Indexed by semantic kind (diagnostics, symbols, errors) for efficient querying. |
| **Gate** | An invariant check that validates store, batch, or output correctness. Gates can be ENFORCED (must pass), HARNESS (tracked), or PLACEHOLDER (not yet implemented). |
| **Content-addressed** | A storage scheme where data is identified by its content hash (SHA-256) rather than by name or location. Guarantees that identical content always has the same identifier. |
| **LMDB index** | An optional acceleration cache built from output records. Speeds up queries on large stores. Can be rebuilt at any time from the filesystem. |
| **Deterministic** | Given the same inputs, always produces the same outputs. No randomness, no ordering dependency, no hidden state. |
