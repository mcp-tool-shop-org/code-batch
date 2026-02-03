# CodeBatch Gate System

The gate system is CodeBatch's unified enforcement product. Gates define invariants
that must hold across phases, and the system provides a consistent way to run,
report, and enforce them.

## Overview

Gates are named invariants with formal definitions, pass criteria, and enforcement
status. They can be run individually, in bundles, or as part of CI.

```bash
# List all gates
codebatch gate list

# Run a specific gate
codebatch gate run P3-A1 --store ./mystore --batch batch-123

# Run a bundle
codebatch gate run-bundle release --store ./mystore --batch batch-123

# Get gate details
codebatch gate explain P3-A1
```

## Gate Statuses

| Status       | Meaning                                           | CI Behavior           |
|--------------|---------------------------------------------------|----------------------|
| ENFORCED     | Must pass; failure blocks releases                | Fail on failure      |
| HARNESS      | Has tests; may be promoted to ENFORCED            | Warn on failure      |
| PLACEHOLDER  | Defined but not yet implemented                   | Skip                 |

## Gate ID Scheme

Gate IDs follow a stable naming scheme:

```
<Phase>-<Code>[-<suffix>]
```

- **P1-\***: Substrate gates (Phase 1 - store, CAS, snapshots)
- **P2-\***: Pipeline/task gates (Phase 2 - tasks, runner, outputs)
- **P3-\***: Cache gates (Phase 3 - LMDB acceleration)
- **R-\***: Release gates (strict bundle aliases)

### Examples

| Gate ID               | Description                                    |
|-----------------------|------------------------------------------------|
| P1-G1                 | Store schema validation                        |
| P2-G1                 | Parse task produces valid AST outputs          |
| P2-G6                 | Truth-store guard (no writes outside batches/) |
| P3-A1                 | Cache equivalence (cache = scan)               |
| P3-A2                 | Cache deletion fallback                        |
| P3-A3                 | Deterministic rebuild                          |
| P3-A4                 | Truth-store guard for cache                    |
| R-RELEASE             | All enforced gates for release                 |

Short aliases (e.g., `A1` for `P3-A1`) are supported for convenience.

## Gate Result Schema

Every gate run produces a structured result:

```json
{
  "gate_id": "P3-A1",
  "status": "ENFORCED",
  "passed": true,
  "duration_ms": 1234,
  "details": {
    "outputs_compared": 147,
    "mismatches": 0
  },
  "artifacts": [
    "indexes/gate_artifacts/P3-A1/comparison.json"
  ],
  "failures": [],
  "environment": {
    "os": "win32",
    "python": "3.14.0",
    "codebatch_version": "0.3.0"
  },
  "context": {
    "store": "./mystore",
    "batch_id": "batch-123",
    "snapshot_id": "snap-456"
  }
}
```

### Result Fields

| Field        | Type           | Description                                    |
|--------------|----------------|------------------------------------------------|
| gate_id      | string         | Canonical gate identifier                      |
| status       | enum           | ENFORCED, HARNESS, PLACEHOLDER                 |
| passed       | boolean        | Whether the gate passed                        |
| duration_ms  | integer        | Execution time in milliseconds                 |
| details      | object         | Gate-specific structured data                  |
| artifacts    | string[]       | Paths to generated artifacts                   |
| failures     | object[]       | List of actionable failure details             |
| environment  | object         | Runtime environment info                       |
| context      | object         | Store/batch/snapshot identifiers               |

## Bundles

Bundles group gates for common use cases:

| Bundle        | Description                              | Gates Included           |
|---------------|------------------------------------------|--------------------------|
| phase1        | Substrate invariants                     | P1-*                     |
| phase2        | Pipeline/task invariants                 | P2-*                     |
| phase3        | Cache invariants                         | P3-*                     |
| release       | All ENFORCED gates                       | All with status=ENFORCED |

```bash
# Run phase 3 bundle
codebatch gate run-bundle phase3 --store ./mystore --batch batch-123

# Run release bundle (strict)
codebatch gate run-bundle release --store ./mystore --batch batch-123
```

## Gate Registry

All gates are registered in a central registry with:

- **gate_id**: Unique stable identifier
- **title**: One-line summary
- **description**: Full description with pass criteria
- **status**: ENFORCED, HARNESS, or PLACEHOLDER
- **required_inputs**: What context the gate needs
- **tags**: Categorization (phase, area)
- **entrypoint**: Callable that executes the gate

### Required Inputs

| Input         | Description                                    |
|---------------|------------------------------------------------|
| store         | Path to CodeBatch store                        |
| batch         | Batch ID to test                               |
| snapshot      | Snapshot ID (usually derived from batch)       |
| cache         | Whether LMDB cache must exist                  |
| tasks         | List of task IDs (for task-specific gates)     |

## Artifacts

Gates may produce artifacts for debugging or auditing:

```
<store>/
  indexes/
    gate_artifacts/
      <gate_id>/
        <timestamp>/
          summary.json
          comparison.jsonl
          ...
```

Or for batch-specific artifacts:

```
<store>/
  batches/
    <batch_id>/
      gate_artifacts/
        <gate_id>/
          ...
```

Each artifact directory includes a `summary.json` describing what was generated.

## CI Integration

CI runs the release bundle:

```bash
codebatch gate run-bundle release --store ./mystore --batch $BATCH_ID --json > gate-results.json
```

Exit codes:
- **0**: All gates passed
- **1**: At least one ENFORCED gate failed
- **2**: Gate runner error (invalid args, missing store, etc.)

### CI Job Structure

```yaml
gate-check:
  steps:
    - name: Run gate bundle
      run: codebatch gate run-bundle release --store ./store --batch $BATCH_ID --json > results.json

    - name: Upload artifacts on failure
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: gate-artifacts
        path: ./store/indexes/gate_artifacts/
```

## Adding a New Gate

1. **Define the gate** in `src/codebatch/gates/registry.py`:

```python
@register_gate(
    gate_id="P4-G1",
    title="My new invariant",
    description="Ensures X always equals Y when Z happens.",
    status=GateStatus.HARNESS,
    required_inputs=["store", "batch"],
    tags=["phase4", "validation"],
)
def gate_p4_g1(ctx: GateContext) -> GateResult:
    # Implementation
    passed = check_invariant(ctx.store, ctx.batch_id)
    return GateResult(
        gate_id="P4-G1",
        passed=passed,
        details={"checked": 100},
    )
```

2. **Add to bundle** if needed (in `bundles.py`).

3. **Write tests** to verify the gate logic.

4. **Promote to ENFORCED** when ready.

## Troubleshooting

### Gate not found

```
Error: Unknown gate 'X1'. Did you mean 'P1-G1'?
```

Use `codebatch gate list` to see all available gates.

### Missing required input

```
Error: Gate 'P3-A1' requires 'batch' but none provided.
```

Provide all required inputs: `--store`, `--batch`, etc.

### Reproducing CI failures

Run the exact same command locally:

```bash
codebatch gate run-bundle release --store ./store --batch batch-123
```

Check `gate_artifacts/` for detailed comparison data.

## Gate Invariants

The gate system itself has invariants:

1. **Deterministic**: Same inputs → same pass/fail result
2. **Idempotent**: Running twice produces identical results
3. **Fast**: Gates should complete in reasonable time
4. **Actionable**: Failures include specific fix suggestions
