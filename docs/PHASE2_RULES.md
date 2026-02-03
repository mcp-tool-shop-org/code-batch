# Phase 2 Rules

**Mechanical enforcement rules for Phase 2 development.**

---

## 1. Output Replacement Rule

Per-shard outputs are **complete replacement**, not append.

```
# CORRECT: atomic replacement
temp_path.write(all_outputs)
temp_path.replace(outputs_path)

# WRONG: appending
with open(outputs_path, 'a') as f:
    f.write(new_output)
```

**Enforced by**: Gate 4 (Retry Determinism)

---

## 2. Allowed Additions

### Tasks (max 2 new)
- `03_symbols` - symbol extraction
- `04_lint` - lint diagnostics

### Cache (max 1)
- `indexes/` directory for query acceleration
- Must be rebuildable from outputs indexes
- Deletion must not break queries

### Plan Semantics
- `deps` field added to task definitions
- Runner enforces topological order
- No parallel execution semantics

---

## 3. Disallowed Categories

### Network Services
No imports of:
- `socket`, `http.server`, `asyncio.Server`
- `fastapi`, `flask`, `uvicorn`, `starlette`
- `aiohttp.web`, `tornado.web`

**Enforced by**: CI Rule B (Network Surface Guard)

### New Truth Stores
Semantic answers may only be written to:
- `objects/sha256/...` (CAS blobs)
- `batches/.../shards/.../outputs.index.jsonl`
- `indexes/` (cache only)

**Enforced by**: CI Rule C (Truth Store Guard)

### Forbidden Changes to SPEC
Protected regions (marked in SPEC.md):
- Store layout
- Shard execution rules
- Truth separation (events vs outputs)
- Object ref semantics
- Snapshot immutability

**Enforced by**: CI Rule A (SPEC Stability Guard)

---

## 4. Task Executor Constraints

### Allowed Inputs
- `runner.iter_shard_files()` - files for current shard
- `runner.iter_prior_outputs(task_id, kind=None)` - outputs from dep task, same shard

### Forbidden
- Scanning all shards
- Reading other batches
- Writing outside shard directory

### Signature (unchanged from Phase 1)
```python
def executor(
    config: dict,
    files: Iterable[dict],
    runner: ShardRunner
) -> Iterable[dict]
```

---

## 5. Plan.json Shape (Locked)

```json
{
  "schema_name": "codebatch.plan",
  "schema_version": 1,
  "producer": {"name": "codebatch", "version": "..."},
  "batch_id": "batch_...",
  "tasks": [
    {"task_id": "01_parse", "type": "parse", "deps": []},
    {"task_id": "02_analyze", "type": "analyze", "deps": ["01_parse"]},
    {"task_id": "03_symbols", "type": "symbols", "deps": ["01_parse"]},
    {"task_id": "04_lint", "type": "lint", "deps": ["01_parse"]}
  ]
}
```

**Rules**:
- `tasks` is ordered list
- `deps` references earlier tasks only
- `type` matches executor name

---

## 6. Output Canonicalization (Tests Only)

For deterministic test comparisons:

1. Sort records by `(kind, path, code, object)`
2. Drop or zero `ts` field
3. Normalize diagnostic message whitespace (optional)

This is **test infrastructure only**, not runtime behavior.

---

## 7. CI Gates Summary

| Gate | What it checks |
|------|----------------|
| A: SPEC Stability | Protected regions unchanged |
| B: Network Surface | No server imports |
| C: Truth Store | Writes only to allowed paths |
| 1: Multi-task E2E | Full pipeline completes |
| 2: Log Independence | Queries work without events |
| 3: Cache Deletion | Queries work without indexes/ |
| 4: Retry Determinism | Shard retry produces same outputs |
| 5: Spec Stability | Schema backward compatibility |
