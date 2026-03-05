---
title: Code Batch Handbook
description: Complete guide to the content-addressed batch execution engine.
sidebar:
  order: 0
---

Welcome to the **Code Batch** handbook. This guide covers everything you need to know to install, configure, and operate Code Batch — a filesystem-based execution substrate for running deterministic transformations over codebases.

## What is Code Batch?

Code Batch snapshots your source code, shards work deterministically across pipelines, and indexes every output for structured queries. There is no database, no server process, and no network dependency. Everything lives on your filesystem as plain JSON records.

The core guarantee: **same input + same pipeline = same result**. Re-run a batch six months later and get byte-identical outputs.

## Who is it for?

Code Batch is built for developers who need:

- **Repeatable code analysis pipelines** that produce identical results given identical inputs
- **CI integrations** where batch results must be auditable and diffable between runs
- **Batch transformation workflows** where every step is traceable from input to output
- **Large-scale codebase processing** that can be parallelized, interrupted, and resumed

## Handbook contents

| Page | What you will learn |
|------|---------------------|
| [Getting Started](/code-batch/handbook/getting-started/) | Install Code Batch, create your first store, snapshot a project, and run a batch end-to-end |
| [Usage](/code-batch/handbook/usage/) | Discover pipelines and tasks, query outputs with aliases, explore and compare batches |
| [Commands](/code-batch/handbook/commands/) | Full CLI reference for low-level commands, shard execution, and LMDB indexing |
| [Reference](/code-batch/handbook/reference/) | Project structure, spec versioning policy, and security and data scope |

## Key concepts

Before diving in, here are the terms you will encounter throughout the handbook:

- **Store** — A filesystem directory that holds all snapshots, batches, and outputs. Created with `codebatch init`.
- **Snapshot** — An immutable, content-addressed capture of a source directory. Every file is hashed with SHA-256.
- **Batch** — A unit of execution that pairs a snapshot with a pipeline. Contains tasks and shards.
- **Pipeline** — An ordered sequence of tasks (e.g. parse, analyze, symbols, lint) that define what work to perform.
- **Task** — A single processing step within a pipeline (e.g. `01_parse`, `02_analyze`).
- **Shard** — A deterministic partition of files within a task. Shards execute in isolation and write structured JSON output records.
- **Output record** — A structured JSON document produced by a shard, indexed by semantic kind (diagnostics, symbols, errors).

## Design principles

1. **Content-addressed inputs** — Every input is hashed. Same content produces the same hash, which produces the same result. No hidden state.
2. **Deterministic sharding** — File-to-shard assignment is a pure function of file paths. No randomness, no ordering dependency.
3. **Filesystem-native** — All state is plain files and directories. No database server, no background process, no ports to manage.
4. **Structured outputs** — Every output has a semantic kind. Query by type (diagnostics, symbols, errors) instead of parsing log files.
5. **Resumable execution** — Interrupted batches can be resumed from exactly where they stopped. Completed shards are not re-executed.
