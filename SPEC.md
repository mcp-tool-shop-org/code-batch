# CodeBatch Storage & Execution Specification

**Specification Version: 1.0 (Draft)**
**Schema Version: 1** (`schema_version` field in all records)

> **Note**: The specification version tracks the document itself. The schema version
> is the integer value written to `schema_version` fields in JSON records and is
> incremented when record formats change in backward-incompatible ways.

---

## 1. Scope and Non-Goals

This specification defines:

- The on-disk storage layout
- Content-addressed object rules
- Snapshot, batch, task, and shard contracts
- Execution and output indexing semantics
- Queryability guarantees

This specification does **not** define:

- Scheduling policies
- UI concerns
- Cloud-specific integrations
- Programming language requirements

All behaviors are defined in terms of filesystem structure and serialized records.

---

## 2. Global Invariants

The system SHALL maintain the following invariants:

1. Content-addressed objects are immutable and add-only.
2. Snapshots represent frozen input state and never change after creation.
3. Batches represent execution attempts and may be repeated or discarded.
4. Semantic results are discoverable without reading execution logs.
5. Partial execution SHALL NOT corrupt previously completed work.
6. All indexes are append-only and rebuildable from authoritative data.

---

## 3. Store Root Layout

A CodeBatch store has the following top-level layout:

```
<store_root>/
  store.json
  objects/
  snapshots/
  batches/
  indexes/        # optional acceleration only
```

`store.json` describes store-level configuration and versioning.

---

## 4. Object Store

### 4.1 Object Identity

- Each object is identified by `sha256(raw_bytes)`.
- Object identity is independent of filename, origin, or usage.
- Object hashes are stable across platforms.

### 4.2 Storage Layout

Objects SHALL be stored at:

```
objects/sha256/<aa>/<bb>/<full_hash>
```

Where `<aa>` and `<bb>` are the first two byte pairs of the hex hash.

### 4.3 Object Metadata (Optional)

An object MAY have an adjacent metadata file:

```
<full_hash>.meta.json
```

Metadata is advisory and SHALL NOT be required for correctness.

---

## 5. Snapshots

### 5.1 Snapshot Definition

- A snapshot represents a frozen view of an input source at a specific point in time.
- Snapshots are immutable once written.

### 5.2 Snapshot Layout

```
snapshots/<snapshot_id>/
  snapshot.json
  files.index.jsonl
```

### 5.3 Path Canonicalization

All file paths in a snapshot SHALL be canonicalized:

- UTF-8 encoded
- `/` as separator
- No `.` or `..` segments
- No trailing slash
- Stable casing preserved

A `path_key` field SHALL be included for normalized comparison.

### 5.4 File Index Records

Each line in `files.index.jsonl` describes exactly one file.

**Required fields:**

| Field | Description |
|-------|-------------|
| `schema_version` | Record schema version |
| `path` | Original file path |
| `path_key` | Normalized path for comparison |
| `object` | SHA-256 hash of file content |
| `size` | File size in bytes |

**Optional fields MAY include:**

- `text_hash`
- `lang_hint`
- `mode`
- `mtime`

---

## 6. Batches

### 6.1 Batch Definition

- A batch represents one execution attempt over a snapshot.
- Batches are isolated, repeatable, and discardable.

### 6.2 Batch Layout

```
batches/<batch_id>/
  batch.json
  plan.json
  events.jsonl
  tasks/
```

### 6.3 Batch Events

- `events.jsonl` records execution facts only.
- Events SHALL NOT be required to answer semantic questions about outputs.

---

## 7. Tasks

### 7.1 Task Definition

- A task performs a deterministic transformation over snapshot inputs or prior task outputs.
- Tasks SHALL be idempotent per shard.

### 7.2 Task Layout

```
tasks/<task_id>/
  task.json
  events.jsonl
  shards/
```

### 7.3 Task Configuration

`task.json` SHALL fully describe:

- Task identity
- Input requirements
- Sharding strategy
- Resolved configuration parameters

Task configuration SHALL be treated as immutable.

---

## 8. Shards

### 8.1 Shard Identity

- Shards are deterministic partitions of task input space.
- Shard identifiers SHALL be stable across executions.

### 8.2 Shard Layout

```
shards/<shard_id>/
  state.json
  outputs.index.jsonl
```

### 8.3 Shard State

- `state.json` tracks shard execution status.
- Shard state transitions SHALL be monotonic.

### 8.4 Shard Execution Rules

A shard:

1. Reads only snapshot and prior task outputs
2. Writes only within its own shard directory
3. Adds objects to the object store
4. Appends records to its outputs index
5. Emits completion events only after outputs are committed

---

## 9. Outputs

### 9.1 Output Records

- All semantic results SHALL be represented as output records.
- Output records are append-only.

### 9.2 Output Index

Each shard SHALL maintain an `outputs.index.jsonl`.

Each record SHALL include:

| Field | Description |
|-------|-------------|
| `schema_version` | Record schema version |
| `snapshot_id` | Source snapshot |
| `batch_id` | Execution batch |
| `task_id` | Owning task |
| `shard_id` | Owning shard |
| `path` | Source file path |
| `kind` | Output type |
| `ts` | Timestamp |

Records MAY include:

- `object` — Content hash for stored outputs
- `format` — Output format identifier
- Diagnostic fields (`severity`, `code`, `message`)

### 9.3 Diagnostics

- Diagnostics SHALL be represented as output records with `kind = diagnostic`.
- Diagnostics SHALL NOT be inferred from execution events.

---

## 10. Large Outputs

### 10.1 Chunking Requirement

- Outputs exceeding a configured size threshold SHALL be chunked.
- Chunked outputs SHALL be represented by a manifest object.

### 10.2 Chunk Manifest

A chunk manifest SHALL include:

| Field | Description |
|-------|-------------|
| `schema_name` | Manifest schema identifier |
| `schema_version` | Manifest schema version |
| `kind` | Output kind |
| `format` | Content format |
| `chunks` | Array of chunk object references |
| `total_bytes` | Total size across all chunks |

Output records SHALL reference the manifest object.

---

## 11. Execution Semantics

### 11.1 Determinism

Given identical snapshot, task configuration, and shard identifier:

- The same outputs SHALL be produced
- Duplicate objects SHALL deduplicate naturally

### 11.2 Failure Handling

- Shard failure SHALL NOT invalidate other shards.
- Restarting a shard SHALL NOT require cleanup.

---

## 12. Query Model

The following questions SHALL be answerable without reading execution logs:

1. Which files produced diagnostics?
2. Which outputs exist for a given task?
3. Which files failed a given task?
4. Aggregate counts by kind, severity, or language

Indexes MAY be accelerated but SHALL remain rebuildable.

---

## 13. Versioning

All structured records SHALL include:

- `schema_name`
- `schema_version`

Readers SHALL tolerate unknown fields.

---

## 14. Compliance

An implementation is compliant if:

1. All required structures are present
2. All invariants are preserved
3. Semantic state is discoverable from indexes alone
4. Partial execution does not corrupt prior results
