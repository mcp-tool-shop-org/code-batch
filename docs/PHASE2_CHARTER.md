# Phase 2 Charter: Semantic Workloads

**Status: LOCKED**
**Binding Tasks: symbols, lint**

---

## Objective

Add two real semantic workloads (symbols, lint) that prove the substrate works for chained analysis without breaking Phase 1 invariants.

---

## Core Policy: Per-Shard Output Replacement

Each shard's `outputs.index.jsonl` is treated as the shard's **complete semantic truth** for that task.

- A shard run produces a new complete file, committed atomically (tmp → rename)
- Retries **overwrite** the shard output index, not append
- Determinism and retry equivalence are provable without global dedupe logic

This policy is non-negotiable and verified by Gate 4 (Retry Determinism).

---

## Allowed Additions

| Category | Limit | Examples |
|----------|-------|----------|
| New tasks | 2 max | `03_symbols`, `04_lint` |
| Cache acceleration | 1 max | `indexes/` directory |
| Plan semantics | deps only | Task dependency ordering |

---

## Forbidden in Phase 2

| Category | Reason |
|----------|--------|
| Network services | No HTTP/WebSocket/RPC |
| Schedulers | No distributed execution |
| New truth stores | Only CAS + outputs indexes |
| Global deduplication | Per-shard replacement handles this |
| Cross-shard queries | Tasks read only their own shard |

---

## Binding Task Definitions

### 03_symbols

**Purpose**: Extract symbol tables and reference edges from parsed ASTs.

**Outputs**:
- `kind=symbol`: Per-file symbol definitions (functions, classes, variables)
- `kind=edge`: Import/reference relationships

**Inputs**: Depends on `01_parse` AST outputs.

**Schema** (symbol record):
```json
{
  "kind": "symbol",
  "path": "src/foo.py",
  "name": "MyClass",
  "symbol_type": "class",
  "line": 10,
  "col": 0,
  "scope": "module"
}
```

**Schema** (edge record):
```json
{
  "kind": "edge",
  "path": "src/foo.py",
  "edge_type": "imports",
  "target": "os.path",
  "line": 1
}
```

### 04_lint

**Purpose**: Run configurable lint rules and emit diagnostics.

**Outputs**:
- `kind=diagnostic`: Lint warnings/errors with code, severity, location

**Inputs**: Depends on `01_parse` AST outputs.

**Schema** (diagnostic record):
```json
{
  "kind": "diagnostic",
  "path": "src/foo.py",
  "severity": "warning",
  "code": "W0611",
  "message": "Unused import 'os'",
  "line": 1,
  "col": 0
}
```

---

## 02_analyze Completion

The existing `02_analyze` stub becomes real:

**Outputs**:
- `kind=metric`: File-level metrics (size, LOC, complexity)

**Schema** (metric record):
```json
{
  "kind": "metric",
  "path": "src/foo.py",
  "metric": "loc",
  "value": 150
}
```

---

## Plan Dependencies

Phase 2 adds task dependency enforcement to `plan.json`:

```json
{
  "tasks": [
    {"task_id": "01_parse", "deps": []},
    {"task_id": "02_analyze", "deps": ["01_parse"]},
    {"task_id": "03_symbols", "deps": ["01_parse"]},
    {"task_id": "04_lint", "deps": ["01_parse"]}
  ]
}
```

**Rules**:
- `deps` must refer only to earlier tasks in the list
- Runner errors if you try to run a task before deps are complete
- No other graph semantics in Phase 2

---

## Truth Sources (Exhaustive List)

| Source | Purpose | Mutable? |
|--------|---------|----------|
| `snapshots/<id>/files.index.jsonl` | Input file manifest | No (immutable) |
| `batches/<id>/tasks/<id>/shards/<id>/outputs.index.jsonl` | Semantic results | Yes (replacement only) |
| `objects/sha256/...` | Content blobs | No (add-only) |
| `indexes/` | Optional acceleration | Yes (rebuildable) |

Events (`events.jsonl`) are **not** truth sources. Semantic queries must work with events deleted.

---

## Phase 2 Completion Criteria

Phase 2 is complete when:

1. `02_analyze` emits real `kind=metric` outputs
2. `03_symbols` emits `kind=symbol` and `kind=edge` outputs
3. `04_lint` emits `kind=diagnostic` outputs with codes
4. Plan deps enforced (runner rejects out-of-order execution)
5. All Phase 2 gates pass in CI
6. 150+ tests passing

Everything else is Phase 3.
