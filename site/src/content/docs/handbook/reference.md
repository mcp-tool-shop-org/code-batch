---
title: Reference
description: Project structure, specification details, and security and data scope.
sidebar:
  order: 4
---

This page covers the structural and operational details of Code Batch: how the project is organized, what data it accesses, and the boundaries of its execution environment.

## Project structure

The Code Batch repository is organized as follows:

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation (including TASKS.md task reference)
.github/      CI/CD workflows
```

### schemas/

Contains JSON Schema definitions for every record type Code Batch produces — snapshots, batches, shard records, output records, diagnostics, and more. These schemas are the formal contract between Code Batch and any tooling that reads its output.

### src/

The core Python implementation. Includes the CLI entry point, the snapshot engine, the sharding algorithm, task runners, the query engine, and the LMDB indexer.

### tests/

Test suites covering the snapshot engine, deterministic sharding, task execution, query correctness, and the index builder. Fixtures provide known-good inputs and expected outputs for regression testing.

### docs/

Extended documentation beyond the README. The key file here is **TASKS.md**, which provides a detailed reference for every built-in task type: parse, analyze, symbols, and lint.

## Store layout

When you initialize a store and run batches, the filesystem layout looks like this:

```
store/
  snapshots/
    <snapshot-id>/
      manifest.json        # File list with SHA-256 hashes
      files/               # Content-addressed file copies
  batches/
    <batch-id>/
      batch.json           # Batch metadata (snapshot, pipeline, timestamps)
      tasks/
        01_parse/
          shards/
            ab/
              status.json  # Shard execution status
              outputs/     # Structured JSON output records
            cd/
              ...
        02_analyze/
          ...
  indexes/
    <batch-id>.lmdb        # Optional acceleration index
```

Every piece of state is a plain file. You can inspect, back up, or move stores with standard filesystem tools. There is no hidden state, no lock files that linger, and no background process to manage.

## Specification

The Code Batch specification (SPEC.md in the repository root) defines the storage format, execution model, and output record schema. Key aspects:

### Versioning

- Semantic versioning with draft/stable markers
- Each version is git-tagged (e.g. `spec-v1.0-draft`)
- Breaking changes increment the major version
- Implementations declare their target spec version

### Forward compatibility

- Unknown fields in JSON records must be tolerated (not rejected)
- New optional fields may be added in minor versions
- Existing fields never change meaning within a major version

### Determinism guarantees

- Snapshot ID is a deterministic function of directory contents
- Shard assignment is a deterministic function of file paths
- Task execution within a shard is deterministic given the same input and task configuration
- Two independent runs of the same snapshot + pipeline produce byte-identical output records

## Security and data scope

Code Batch is a **local-first CLI tool**. It makes no network requests, collects no telemetry, and has no cloud dependency.

### Data accessed

- **Source files:** Read for content-addressed snapshotting (SHA-256 hashing). Files are copied into the store's snapshot directory.
- **Store directory:** Read and write for batch state, shard outputs, and optional LMDB indexes. All writes go to user-specified directories only.

### Data not accessed

- No network requests of any kind
- No telemetry or usage reporting
- No cloud services or remote APIs
- No credential storage or secret management
- No environment variable reading beyond standard Python behavior

### Permissions required

- **Filesystem read** on source directories (for snapshotting)
- **Filesystem write** on store and output directories (for batch execution and indexing)
- No elevated privileges, no system-level access, no background services

### Threat model

Code Batch processes untrusted source files by reading and hashing their contents. It does not execute source files, evaluate them, or pass them to interpreters. The analysis tasks (parse, lint, etc.) operate on file content as data, not as code. Output records are structured JSON — they contain metadata about source files, not executable content.

The primary risk surface is the filesystem: a malicious store directory could contain symlinks or path traversal attempts. Code Batch follows standard path resolution and does not follow symlinks outside the store boundary.

## Additional documentation

- **[SPEC.md](https://github.com/mcp-tool-shop-org/code-batch/blob/main/SPEC.md)** — Full storage and execution specification
- **[docs/TASKS.md](https://github.com/mcp-tool-shop-org/code-batch/blob/main/docs/TASKS.md)** — Task reference (parse, analyze, symbols, lint)
- **[CHANGELOG.md](https://github.com/mcp-tool-shop-org/code-batch/blob/main/CHANGELOG.md)** — Version history
- **[SECURITY.md](https://github.com/mcp-tool-shop-org/code-batch/blob/main/SECURITY.md)** — Vulnerability reporting

## Support

- **Questions and help:** [GitHub Discussions](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **Bug reports:** [GitHub Issues](https://github.com/mcp-tool-shop-org/code-batch/issues)

## License

Code Batch is MIT licensed. See [LICENSE](https://github.com/mcp-tool-shop-org/code-batch/blob/main/LICENSE) for the full text.
