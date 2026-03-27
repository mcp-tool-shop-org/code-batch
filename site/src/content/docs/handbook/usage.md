---
title: Usage
description: Discover pipelines and tasks, query outputs with aliases, and explore and compare batches.
sidebar:
  order: 2
---

Once you have run your first batch, Code Batch provides a rich set of commands for discovering what happened, querying outputs, and comparing runs over time.

## Discoverability

Code Batch makes it easy to navigate the structure of your batches without digging through filesystem paths.

### List pipelines

See all available pipelines:

```bash
codebatch pipelines
```

Code Batch ships with three built-in pipelines:

- **`parse`** — Parse source files and emit AST and diagnostics (single task: `01_parse`)
- **`analyze`** — Parse and analyze (two tasks: `01_parse`, `02_analyze`)
- **`full`** — Complete pipeline (four tasks: `01_parse`, `02_analyze`, `03_symbols`, `04_lint`)

### Inspect a pipeline

View the tasks in a specific pipeline:

```bash
codebatch pipeline full
```

This shows the ordered list of tasks, their types, dependencies, and configuration.

### List tasks in a batch

Once a batch exists, list the tasks it contains:

```bash
codebatch tasks --batch <id> --store ./store
```

### List shards for a task

See the shard breakdown for a specific task:

```bash
codebatch shards --batch <id> --task 01_parse --store ./store
```

Each shard represents a deterministic partition of the input files. The shard ID (e.g. `ab`, `cd`) is derived from file paths, so the same input always produces the same shards.

## Query aliases

Query aliases are shorthand commands that wrap common `codebatch query` patterns. They save typing and make common operations feel natural.

### Show errors

Surface all error-kind outputs across every task and shard:

```bash
codebatch errors --batch <id> --store ./store
```

This is equivalent to querying all outputs with `kind: error` but presents them in a human-readable format with file paths and messages.

### List files in a snapshot

See which files are part of the batch's snapshot:

```bash
codebatch files --batch <id> --store ./store
```

Useful for verifying that the snapshot captured what you expected, or for scripting over file lists.

### Top output kinds

Get a ranked count of output kinds across all tasks:

```bash
codebatch top --batch <id> --store ./store
```

This gives you a quick feel for what a batch produced — how many diagnostics, symbols, errors, etc. Use `--by` to group by different fields:

```bash
codebatch top --batch <id> --store ./store --by severity
codebatch top --batch <id> --store ./store --by code --limit 20
```

## Exploration and comparison (Phase 6)

Phase 6 adds read-only commands for deep exploration and cross-batch comparison. These commands never modify the store.

### Inspect outputs for a file

See every output record associated with a specific source file:

```bash
codebatch inspect src/main.py --batch <id> --store ./store
```

This collects outputs from all tasks and shards that processed the file, giving you a complete picture of what Code Batch found.

### Understand data sources

Add `--explain` to any inspect command to see where each output came from:

```bash
codebatch inspect src/main.py --batch <id> --store ./store --explain
```

The explain flag annotates each output with its source task, shard, and record path. This is useful for debugging pipelines or understanding why a particular diagnostic appeared.

### Compare two batches

See what changed between two batch runs:

```bash
codebatch diff <batchA> <batchB> --store ./store
```

The diff command compares outputs by semantic kind and file path, showing additions, removals, and changes. Both batches must reference the same store.

### Show regressions

Filter the diff to show only new or worsened diagnostics:

```bash
codebatch regressions <batchA> <batchB> --store ./store
```

Regressions are outputs that appear in batch B but not in batch A, or outputs that are worse (e.g. a warning that became an error). This is the go-to command for CI gating — if regressions appear, the pipeline can fail.

### Show improvements

Filter the diff to show only fixed or improved diagnostics:

```bash
codebatch improvements <batchA> <batchB> --store ./store
```

Improvements are outputs that existed in batch A but were resolved in batch B. Use this to track progress over time or to celebrate cleanup work.

## Practical patterns

### CI gating with regressions

Run Code Batch as part of your CI pipeline. Compare the current batch against the previous known-good batch, and fail the build if regressions are found:

```bash
codebatch regressions $PREV_BATCH $CURR_BATCH --store ./store
# Exit code indicates whether regressions were found
```

### Tracking progress across releases

Snapshot each release and run the same pipeline. Use `diff` and `improvements` to build a history of code quality over time.

### File-level deep dives

When investigating a specific file, `inspect --explain` gives you the full lineage: which task processed it, which shard it landed in, and exactly what outputs were produced. No log parsing required.

## Next steps

- See the full [command reference](/code-batch/handbook/commands/) for all available commands
- Review [project structure and security scope](/code-batch/handbook/reference/)
- New to Code Batch? Read the [Beginners guide](/code-batch/handbook/beginners/)
