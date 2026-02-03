# CodeBatch

Content-addressed batch execution engine with deterministic sharding and queryable outputs.

## Overview

CodeBatch provides a filesystem-based execution substrate for running deterministic transformations over codebases. It captures inputs as immutable snapshots, executes work in isolated shards, and indexes all semantic outputs for efficient querying—without requiring a database.

## Documentation

- **[SPEC.md](./SPEC.md)** — Full storage and execution specification
- **[CHANGELOG.md](./CHANGELOG.md)** — Version history

## Spec Versioning

The specification uses semantic versioning with draft/stable markers. Each version is tagged in git (e.g., `spec-v1.0-draft`). Breaking changes increment the major version. Implementations should declare which spec version they target and tolerate unknown fields for forward compatibility.

## Project Structure

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
examples/     Usage examples
.github/      CI/CD workflows
```

## Quick Start

```bash
# Initialize a store
codebatch init ./store

# Create a snapshot of a directory
codebatch snapshot ./my-project --store ./store

# List available pipelines
codebatch pipelines

# Initialize a batch with a pipeline
codebatch batch init --snapshot <id> --pipeline full --store ./store

# Run all tasks and shards (Phase 5 workflow)
codebatch run --batch <id> --store ./store

# View progress
codebatch status --batch <id> --store ./store

# View summary
codebatch summary --batch <id> --store ./store
```

## Human Workflow (Phase 5)

Phase 5 adds human-friendly commands that compose existing primitives:

```bash
# Run entire batch (no manual shard iteration needed)
codebatch run --batch <id> --store ./store

# Resume interrupted execution
codebatch resume --batch <id> --store ./store

# Progress summary
codebatch status --batch <id> --store ./store

# Output summary
codebatch summary --batch <id> --store ./store
```

## Discoverability

```bash
# List pipelines
codebatch pipelines

# Show pipeline details
codebatch pipeline full

# List tasks in a batch
codebatch tasks --batch <id> --store ./store

# List shards for a task
codebatch shards --batch <id> --task 01_parse --store ./store
```

## Query Aliases

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## Low-Level Commands

For fine-grained control, the original commands remain available:

```bash
# Run a specific shard
codebatch run-shard --batch <id> --task 01_parse --shard ab --store ./store

# Query outputs
codebatch query outputs --batch <id> --task 01_parse --store ./store

# Query diagnostics
codebatch query diagnostics --batch <id> --task 01_parse --store ./store

# Build LMDB acceleration cache
codebatch index-build --batch <id> --store ./store
```

## License

MIT
