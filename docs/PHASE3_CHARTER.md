# Phase 3 Charter: Acceleration (Lane A)

**Status: LOCKED**
**Scope: LMDB-backed query cache**

---

## Objective

Make queries and cross-task joins fast at scale without changing semantics.

The cache is **derived, rebuildable, never truth**.

---

## Allowed

| Category | Description |
|----------|-------------|
| Cache creation | `codebatch index build` creates `indexes/lmdb/` |
| Opportunistic use | Query engine uses cache when valid |
| Rebuild | Cache is rebuildable from JSONL + snapshot indexes |
| Deletion | Deleting `indexes/` falls back to scan (same answers, slower) |

---

## Forbidden

| Category | Reason |
|----------|--------|
| Cache becomes truth | Authoritative sources remain JSONL |
| Mutable "latest" pointers | No global state outside batch scope |
| Background daemons/watchers | No persistent processes |
| New semantic state | Only cache what's derivable |
| Arbitrary queries | Fixed query set only (Phase 4 territory) |

---

## Truth Sources (Unchanged from Phase 2)

| Source | Purpose | Mutable? |
|--------|---------|----------|
| `snapshots/<id>/files.index.jsonl` | Input file manifest | No |
| `batches/<id>/tasks/<id>/shards/<id>/outputs.index.jsonl` | Semantic results | Yes (replacement only) |
| `objects/sha256/...` | Content blobs | No (add-only) |

**Cache (`indexes/`) is NOT a truth source.**

---

## LMDB Environment Layout

```
<store>/indexes/lmdb/
  data.mdb
  lock.mdb
  cache_meta.json
```

### Named Databases (DBIs)

| DBI | Purpose | Key Format |
|-----|---------|------------|
| `meta` | Cache metadata (single record) | `meta` |
| `files_by_path` | Snapshot file info lookup | `v1␟<snapshot_id>␟<path>` |
| `outputs_by_kind` | Fast kind/path lookup | `v1␟<snapshot_id>␟<batch_id>␟<task_id>␟<kind>␟<path>` |
| `diags_by_sev` | Diagnostics by severity | `v1␟<snapshot_id>␟<batch_id>␟<task_id>␟<severity>␟<code>␟<path>␟<line>␟<col>` |
| `diags_by_code` | Diagnostics by code | `v1␟<snapshot_id>␟<batch_id>␟<task_id>␟<code>␟<severity>␟<path>␟<line>␟<col>` |
| `stats` | Pre-aggregated counters | `v1␟<snapshot_id>␟<batch_id>␟<task_id>␟count␟<group>␟<value>` |

**Delimiter**: `␟` = `\x1f` (unit separator)

---

## Key/Value Encoding

- Keys: UTF-8 bytes with `\x1f` delimiter
- Values: msgpack for speed/size (JSON fallback for debugging)
- All keys include schema version prefix (`v1`) for future compatibility

### files_by_path Value

```json
{"lang": "python", "size": 1234, "path_key": "src/a.py", "obj_prefix": "ab"}
```

### stats Value

8-byte big-endian u64 counter.

---

## Build Algorithm

Command:
```bash
codebatch index build --store <root> --batch <id> [--rebuild]
```

Steps:
1. Resolve `snapshot_id` from `batch.json`
2. Create fresh LMDB env (wipe if `--rebuild`)
3. Ingest `files.index.jsonl` → `files_by_path`
4. For each task, for each shard:
   - Read `outputs.index.jsonl`
   - Write to `outputs_by_kind`
   - If `kind=diagnostic`: write to `diags_by_sev`, `diags_by_code`
   - Update `stats` counters (including lang join)
5. Write `cache_meta.json` with fingerprint

### Source Fingerprint

Stable fingerprint from authoritative sources:
- Hash of `files.index.jsonl`
- Combined hash of all shard `outputs.index.jsonl`

If fingerprint mismatches, cache is stale → fallback to scan.

---

## Query Routing

```
cache = CacheLayer.try_open(store, batch_id)
if cache and cache.is_valid_against_sources():
    return cache.query_*(...)
else:
    return scan_jsonl_*(...)  # existing path
```

**No mixed mode.**

---

## Phase 3 Gates

### Gate A1: Cache Equivalence

Run queries via scan, then via cache. Canonicalized results must match.

### Gate A2: Cache Deletion Equivalence

Delete `indexes/lmdb/`. Queries return identical results (via scan fallback).

### Gate A3: Deterministic Rebuild

Rebuild cache twice from same sources. Canonical query suite results must be identical.

### Gate A4: Truth-Store Guard

During build and queries, no writes outside `indexes/` and allowed shard paths.

---

## What We Cache (Minimal, High Leverage)

### A) Snapshot File Metadata

From `files.index.jsonl`:
- `path` → `lang_hint`, `size`, `path_key`, `obj_prefix`

### B) Output Record Index

From `outputs.index.jsonl`:
- Diagnostics index (by severity/code)
- Outputs existence (by kind/path)
- Pre-aggregated stats counters

**We do NOT cache full output payload objects (CAS handles that).**

---

## Phase 3 Completion Criteria

1. `codebatch index build` creates valid LMDB cache
2. Queries use cache when valid, fallback to scan otherwise
3. Gate A1 passes (cache equivalence)
4. Gate A2 passes (deletion equivalence)
5. Gate A3 passes (deterministic rebuild)
6. Gate A4 passes (truth-store guard)
7. Documented speedup on representative workload

Everything else is Phase 4.
