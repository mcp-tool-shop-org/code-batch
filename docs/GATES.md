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
- **P5-\***: Workflow gates (Phase 5 - CLI UX, no new truth)
- **P6-\***: UI/UX gates (Phase 6 - read-only views, comparison)
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
| P5-G1                 | No semantic changes (workflow = low-level)     |
| P5-G2                 | No new truth stores                            |
| P5-G4                 | Discoverability coverage                       |
| P6-RO                 | Read-only enforcement (no store writes)        |
| P6-DIFF               | Diff correctness (pure set math)               |
| P6-EXPLAIN            | Explain fidelity (accurate data sources)       |
| P6-HEADLESS           | Headless compatibility (non-TTY works)         |
| P6-ISOLATION          | UI module isolation (removable without breaks) |
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

### Step 1: Define the Gate

Add your gate to `src/codebatch/gates/definitions.py`:

```python
from .registry import register_gate
from .result import GateContext, GateResult, GateStatus

@register_gate(
    gate_id="P4-G1",
    title="My new invariant",
    description="Ensures X always equals Y when Z happens.",
    status=GateStatus.HARNESS,  # Start as HARNESS
    required_inputs=["store", "batch"],
    tags=["phase4", "validation"],
    aliases=["my-gate"],  # Optional short alias
)
def gate_p4_g1(ctx: GateContext) -> GateResult:
    """Check that X equals Y."""
    result = GateResult(
        gate_id="P4-G1",
        passed=True,
        status=GateStatus.HARNESS,
    )

    # Perform checks
    try:
        value_x = get_x(ctx.store_root, ctx.batch_id)
        value_y = get_y(ctx.store_root, ctx.batch_id)

        if value_x != value_y:
            result.add_failure(
                message="X does not equal Y",
                expected=str(value_y),
                actual=str(value_x),
                suggestion="Ensure X and Y are computed from the same source",
            )

        # Add details for reporting
        result.details = {
            "x_value": value_x,
            "y_value": value_y,
            "match": value_x == value_y,
        }

    except Exception as e:
        result.add_failure(message=f"Check error: {e}")

    return result
```

### Step 2: Register in `_REGISTERED_GATES`

At the bottom of `definitions.py`, add your gate function to the list:

```python
_REGISTERED_GATES = [
    gate_p1_g1,
    gate_p2_g1,
    # ... existing gates ...
    gate_p4_g1,  # Add new gate here
]
```

### Step 3: Write Tests

Add tests in `tests/test_gates.py` or a dedicated test file:

```python
class TestGateP4G1:
    """Tests for P4-G1 gate."""

    def test_passes_when_x_equals_y(self, store_with_batch):
        """Should pass when X equals Y."""
        store, batch_id = store_with_batch
        runner = GateRunner(store)
        result = runner.run("P4-G1", batch_id=batch_id)

        assert result.passed is True
        assert result.details["match"] is True

    def test_fails_when_x_differs_from_y(self, store_with_mismatch):
        """Should fail when X differs from Y."""
        store, batch_id = store_with_mismatch
        runner = GateRunner(store)
        result = runner.run("P4-G1", batch_id=batch_id)

        assert result.passed is False
        assert len(result.failures) > 0
```

### Step 4: Write Artifacts (Optional)

If your gate produces debugging output, use the artifact API:

```python
@register_gate(...)
def gate_p4_g1(ctx: GateContext) -> GateResult:
    result = GateResult(gate_id="P4-G1", passed=True)

    # Write comparison data for debugging
    comparison = {"x": value_x, "y": value_y}
    artifact_path = ctx.write_artifact_json(
        "P4-G1", "comparison.json", comparison
    )

    # Artifacts are automatically collected by the runner
    return result
```

Artifacts are stored at: `indexes/gate_artifacts/<gate_id>/<run_id>/`

### Step 5: Test Your Gate

```bash
# Run the gate manually
codebatch gate-run P4-G1 --store ./mystore --batch batch-123

# Run with JSON output for debugging
codebatch gate-run P4-G1 --store ./mystore --batch batch-123 --json

# Explain the gate
codebatch gate-explain P4-G1
```

### Step 6: Promote to ENFORCED

Once the gate is stable and passing consistently:

1. Change `status=GateStatus.HARNESS` to `status=GateStatus.ENFORCED`
2. Add to the "release" bundle (automatic for ENFORCED gates)
3. Update documentation if needed

## Troubleshooting

### Gate not found

```
Error: Unknown gate 'X1'. Did you mean 'P1-G1'?
```

**Solutions:**
- Use `codebatch gate-list` to see all available gates
- Check for typos - the system suggests similar gates
- Use the canonical ID (e.g., `P3-A1`) or a valid alias (e.g., `A1`)

### Missing required input

```
Error: Gate 'P3-A1' requires 'batch' but none provided.
```

**Solutions:**
- Check what inputs the gate needs: `codebatch gate-explain P3-A1`
- Provide all required inputs: `--store`, `--batch`, etc.
- Some gates only need `--store`, others need `--batch` as well

### Gate runs but always fails

**Debugging steps:**
1. Run with JSON output to see details:
   ```bash
   codebatch gate-run P3-A1 --store ./store --batch batch-123 --json
   ```

2. Check the `failures` array for specific error messages

3. Look at `details` for gate-specific diagnostic data

4. Check artifacts at `indexes/gate_artifacts/<gate_id>/`

### Reproducing CI failures

Run the exact same command locally:

```bash
codebatch gate-bundle release --store ./store --batch batch-123 --json
```

**Tips:**
- Ensure your local store has the same content as CI
- Check `gate_artifacts/` for detailed comparison data
- Run individual failing gates for faster iteration

### Bundle shows gates as "skipped"

Gates are skipped for these reasons:
- **PLACEHOLDER status**: Gate is defined but not implemented
- **Missing required inputs**: Gate needs `--batch` but none provided
- **Validation failure**: Gate prerequisites aren't met

Run with verbose output to see skip reasons.

### Performance issues

If gates are slow:
1. Check if LMDB cache exists (gates like P3-A1 use it for comparison)
2. Ensure your batch isn't excessively large
3. Use `--fail-fast` to stop on first failure

### Cache vs. Scan mismatches

If P3-A1 (cache equivalence) fails:
1. Check the comparison artifact at `indexes/gate_artifacts/P3-A1/`
2. The file shows which outputs differ
3. Common causes:
   - Corrupt cache (rebuild with `codebatch index-build --rebuild`)
   - Different query engines (ensure same version)
   - Timing issues (use canonical comparison without timestamps)

## Gate Invariants

The gate system itself has invariants:

1. **Deterministic**: Same inputs → same pass/fail result
2. **Idempotent**: Running twice produces identical results
3. **Fast**: Gates should complete in reasonable time
4. **Actionable**: Failures include specific fix suggestions
