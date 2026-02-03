# Phase 3 Gates: Cache Acceleration

**Status: LOCKED**

---

## Gate A1: Cache Equivalence

**Purpose**: Cached queries return identical results to JSONL scan.

**Test Procedure**:
1. Run full pipeline (parse → analyze → symbols → lint)
2. Execute representative query suite via JSONL scan
3. Build LMDB cache
4. Execute same query suite via cache
5. Canonicalize results (sort, drop `ts`)
6. Assert identical

**Representative Queries**:
- `query_outputs(batch, task)` for all 4 tasks
- `query_outputs(batch, task, kind=X)` for each output kind
- `query_stats(batch, task, group_by=kind)`
- `query_stats(batch, task, group_by=severity)`

---

## Gate A2: Cache Deletion Equivalence

**Purpose**: Deleting cache falls back to scan with identical results.

**Test Procedure**:
1. Run pipeline and build cache
2. Execute query suite (cached)
3. Delete `indexes/lmdb/` directory
4. Execute same query suite (falls back to scan)
5. Assert identical results

---

## Gate A3: Deterministic Rebuild

**Purpose**: Cache builds are reproducible.

**Test Procedure**:
1. Run pipeline
2. Build cache (run 1)
3. Execute query suite, capture results
4. Delete cache
5. Rebuild cache (run 2)
6. Execute same query suite, capture results
7. Assert identical results

**Note**: We compare query results, not raw `data.mdb` bytes (LMDB page allocation may differ).

---

## Gate A4: Truth-Store Guard

**Purpose**: Cache operations don't write to unauthorized locations.

**Test Procedure**:
1. Run pipeline
2. Build cache
3. Enumerate all paths under store root
4. Assert cache writes only under `indexes/`
5. Assert no new paths outside allowed set:
   - `store.json`
   - `objects/`
   - `snapshots/`
   - `batches/`
   - `indexes/`

---

## Failure Recovery

### Gate A1 Fails
- Check value encoding (msgpack vs JSON mismatch?)
- Check key ordering (LMDB uses byte order, ensure UTF-8 consistency)
- Check filter logic in cache queries matches scan queries

### Gate A2 Fails
- Cache fallback not triggering (check `is_valid_against_sources()`)
- Scan path broken (Phase 2 regression)

### Gate A3 Fails
- Non-deterministic ordering during build
- Timestamps leaking into cache keys/values
- Floating-point instability (shouldn't have any)

### Gate A4 Fails
- Temp files not cleaned up
- Lock files persisting (LMDB creates `lock.mdb`)
- Cache metadata written outside `indexes/`
