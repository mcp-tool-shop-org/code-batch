# CodeBatch

Content-addressed batch execution engine with deterministic sharding and queryable outputs.

## Overview

CodeBatch provides a filesystem-based execution substrate for running deterministic transformations over codebases. It captures inputs as immutable snapshots, executes work in isolated shards, and indexes all semantic outputs for efficient querying—without requiring a database.

## Documentation

- **[SPEC.md](./SPEC.md)** — Full storage and execution specification

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
# Create a snapshot of a directory
codebatch snapshot ./my-project --store ./store

# Initialize a batch with a pipeline
codebatch batch init --snapshot <id> --pipeline parse

# Run a shard
codebatch run-shard --batch <id> --task 01_parse --shard ab

# Query results
codebatch query diagnostics --batch <id> --task 01_parse
```

## License

MIT
