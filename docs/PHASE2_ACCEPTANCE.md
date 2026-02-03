# Phase 2 Acceptance Checklist

**Human-readable checklist mirroring automated gates.**

Use this when debugging CI failures.

---

## Pre-Flight Checks

- [ ] All Phase 1 tests still pass (121 baseline)
- [ ] No uncommitted changes to protected SPEC regions
- [ ] No network imports in new code

---

## Gate 1: Multi-Task Pipeline End-to-End

**What it tests**: Complete pipeline with deps works.

**Manual verification**:
```bash
# Init and snapshot
codebatch init ./test-store
codebatch snapshot ./fixtures/corpus --store ./test-store

# Create batch with full pipeline
codebatch batch init --snapshot <id> --pipeline full --store ./test-store

# Run tasks in order
codebatch run-task --batch <id> --task 01_parse --store ./test-store
codebatch run-task --batch <id> --task 02_analyze --store ./test-store
codebatch run-task --batch <id> --task 03_symbols --store ./test-store
codebatch run-task --batch <id> --task 04_lint --store ./test-store

# Verify all shards done
find ./test-store/batches/*/tasks/*/shards/*/state.json -exec grep -l '"status": "done"' {} \;
```

**Pass condition**: All shard states are "done", each task has outputs.

---

## Gate 2: Log Independence

**What it tests**: Semantic queries don't depend on events.

**Manual verification**:
```bash
# Run queries, save output
codebatch query diagnostics --batch <id> --task 04_lint --store ./test-store > before.json
codebatch query outputs --batch <id> --task 03_symbols --kind symbol --store ./test-store >> before.json

# Delete all events
find ./test-store -name "events.jsonl" -delete

# Rerun queries
codebatch query diagnostics --batch <id> --task 04_lint --store ./test-store > after.json
codebatch query outputs --batch <id> --task 03_symbols --kind symbol --store ./test-store >> after.json

# Compare (ignoring timestamps)
diff <(jq -S 'del(.ts)' before.json) <(jq -S 'del(.ts)' after.json)
```

**Pass condition**: Identical semantic results.

---

## Gate 3: Cache Deletion Equivalence

**What it tests**: indexes/ is truly optional.

**Manual verification**:
```bash
# Run queries with cache
codebatch query stats --batch <id> --task 03_symbols --store ./test-store > with_cache.json

# Delete cache
rm -rf ./test-store/indexes/

# Rerun queries
codebatch query stats --batch <id> --task 03_symbols --store ./test-store > without_cache.json

# Compare
diff with_cache.json without_cache.json
```

**Pass condition**: Identical results.

---

## Gate 4: Retry Determinism

**What it tests**: Per-shard replacement produces same outputs on retry.

**Manual verification**:
```bash
# Run shard, capture outputs
codebatch run-shard --batch <id> --task 03_symbols --shard ab --store ./test-store
cp ./test-store/batches/<id>/tasks/03_symbols/shards/ab/outputs.index.jsonl run1.jsonl

# Reset shard (delete state and outputs)
rm ./test-store/batches/<id>/tasks/03_symbols/shards/ab/state.json
rm ./test-store/batches/<id>/tasks/03_symbols/shards/ab/outputs.index.jsonl

# Rerun
codebatch run-shard --batch <id> --task 03_symbols --shard ab --store ./test-store
cp ./test-store/batches/<id>/tasks/03_symbols/shards/ab/outputs.index.jsonl run2.jsonl

# Compare (ignoring ts)
diff <(jq -S 'del(.ts)' run1.jsonl) <(jq -S 'del(.ts)' run2.jsonl)
```

**Pass condition**: Same semantic records (objects may differ if content-equivalent).

---

## Gate 5: SPEC Stability

**What it tests**: Protected SPEC regions unchanged.

**Manual verification**:
```bash
# Check protected region
git diff origin/main -- SPEC.md | grep -A5 -B5 "SPEC_PROTECTED"
```

**Pass condition**: No changes between SPEC_PROTECTED markers.

---

## Task Output Verification

### 02_analyze
- [ ] Emits `kind=metric` records
- [ ] Metrics include: `loc`, `size`, `complexity` (optional)

### 03_symbols
- [ ] Emits `kind=symbol` records with `name`, `symbol_type`, `line`
- [ ] Emits `kind=edge` records with `edge_type`, `target`
- [ ] Symbol types include: `function`, `class`, `variable`
- [ ] Edge types include: `imports`, `calls` (optional)

### 04_lint
- [ ] Emits `kind=diagnostic` records
- [ ] Diagnostics have `severity`, `code`, `message`
- [ ] Line/col positions when available

---

## Final Checklist

- [ ] 150+ tests passing
- [ ] All 5 gates pass in CI
- [ ] No network imports
- [ ] No writes outside allowed paths
- [ ] Plan deps enforced
- [ ] Documentation updated
