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
- **P7-\***: Integration API gates (Phase 7 - stable integration surface)
- **P8-\***: Real workloads gates (Phase 8 - full AST, real symbols, AST linting)
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
| P7-API-DYN            | API reflects actual build capabilities         |
| P7-API-STABLE         | API output is deterministic                    |
| P7-API-NO-SIDE-EFFECTS| API works without store, creates no files      |
| P7-ERR                | All --json failures use error envelope         |
| P7-SCHEMA             | JSON outputs validate against schemas          |
| P8-PARSE              | Python AST preserves function/class names      |
| P8-SYMBOLS            | Symbol names are real identifiers              |
| P8-ROUNDTRIP          | Parse → Symbols → Query returns real names     |
| P8-TREESITTER         | JS/TS real parsing (optional)                  |
| P8-LINT-AST           | AST-aware linting (unused imports/vars)        |
| P8-METRICS            | Real code metrics (complexity)                 |
| P8-SELF-HOST          | Self-analysis produces meaningful results      |
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

---

## Phase 6 Gates: Detailed Specifications

### P6-RO: Read-Only Enforcement

**Gate ID**: `P6-RO`
**Status**: ENFORCED

Phase 6 commands must be purely read-only. They query the store but never write
to it. This is verified by:

1. **No file additions**: No new files appear in store after command
2. **No file deletions**: No files disappear from store after command
3. **No file modifications**: Existing file mtimes remain unchanged

**Commands covered**: `inspect`, `diff`, `regressions`, `improvements`, `explain`

**Test location**: `tests/test_phase6_gates.py::TestGateP6RO`

---

### P6-DIFF: Diff Correctness

**Gate ID**: `P6-DIFF`
**Status**: ENFORCED

The diff engine uses pure set-math comparison with stable, deterministic output.
Records are compared using **canonical keys** that uniquely identify each record
type.

#### Canonical Key Rules

The diff engine normalizes records before comparison by:
1. Removing ephemeral fields: `ts`, `timestamp`, `run_id`, `shard_id`
2. Extracting a canonical key tuple based on record kind

**Canonical key definitions by kind:**

| Kind         | Key Fields                                | Example Key                                      |
|--------------|-------------------------------------------|--------------------------------------------------|
| `diagnostic` | (kind, path, line, column, code)          | `("diagnostic", "test.py", 10, 5, "E001")`       |
| `metric`     | (kind, path, name)                        | `("metric", "test.py", "complexity")`            |
| `symbol`     | (kind, path, name, line)                  | `("symbol", "test.py", "MyClass", 42)`           |
| `ast`        | (kind, path, object)                      | `("ast", "test.py", "sha256:abc123...")`         |
| (generic)    | (kind, path)                              | `("unknown", "test.py")`                         |

**Key guarantees:**

1. **Uniqueness**: Each record has exactly one key
2. **Stability**: Same record always produces same key
3. **Comparability**: Records with same key can be compared for changes
4. **Sortability**: Keys are tuples, enabling deterministic ordering

**Changed detection:**

Two records are "changed" (not added/removed) when:
- They have the same canonical key
- But differ in non-key, non-ephemeral fields (e.g., `severity`, `value`, `message`)

**Normalization fields ignored:**

```python
DEFAULT_IGNORE_FIELDS = {"ts", "timestamp", "run_id", "shard_id"}
```

**Implementation**: `src/codebatch/ui/diff.py`

**Test locations**:
- `tests/test_diff_engine.py` - Unit tests for diff functions
- `tests/test_diff_commands.py` - Integration tests for diff commands
- `tests/test_phase6_gates.py::TestGateP6RO` - Read-only verification

---

### P6-EXPLAIN: Explain Fidelity

**Gate ID**: `P6-EXPLAIN`
**Status**: ENFORCED

The `--explain` flag and `explain` subcommand must accurately describe what data
sources each command uses. Critical requirements:

1. **No false dependencies**: Must NOT mention events if the command doesn't use events
2. **Explicit disclaimers**: Must explicitly state "Does NOT use events"
3. **Accurate sources**: Must list actual data sources (e.g., `outputs.index.jsonl`)
4. **Deterministic**: Output must be identical across runs

**Events independence guarantee:**

Phase 6 commands read ONLY from:
- `batches/<batch_id>/tasks/<task_id>/shards/<shard>/outputs.index.jsonl`
- `batches/<batch_id>/plan.json`

They do NOT read from:
- `events/` directory
- Any event stream or log files

This is verified by a negative test that deletes the events directory and confirms
command output remains unchanged.

**Test locations**:
- `tests/test_explain.py::TestExplainFidelity`
- `tests/test_explain.py::TestExplainEventsIndependence`
- `tests/test_phase6_gates.py::TestGateP6Explain`

---

### P6-HEADLESS: Headless Compatibility

**Gate ID**: `P6-HEADLESS`
**Status**: ENFORCED

All Phase 6 commands must work in headless/non-TTY environments:

1. **`--no-color`**: Produces output with no ANSI escape sequences
2. **`--json`**: Produces valid, parseable JSON output
3. **Non-interactive**: No prompts or terminal dependencies

**Test location**: `tests/test_phase6_gates.py::TestGateP6Headless`

---

### P6-ISOLATION: UI Module Isolation

**Gate ID**: `P6-ISOLATION`
**Status**: ENFORCED

The `codebatch.ui` module is isolated from core modules and can be removed without
breaking Phases 1-5 functionality.

**Requirements:**

1. **No core imports**: UI module does not import from core modules' implementation details
2. **Core independence**: Core modules (`store`, `snapshot`, `batch`, `runner`, `query`)
   work without UI being imported first
3. **Removability**: Deleting `src/codebatch/ui/` would not break Phase 1-5 functionality

**Module structure:**
```
codebatch/
  ui/
    __init__.py     # Exports (isolated)
    format.py       # Table/JSON rendering
    pager.py        # Output pagination
    diff.py         # Diff engine (pure functions)
```

**Test location**: `tests/test_phase6_gates.py::TestGateP6Isolation`

---

## Phase 7 Gates: Detailed Specifications

### P7-API-DYN: Accurate Capability Reflection

**Gate ID**: `P7-API-DYN`
**Status**: ENFORCED

The `api` command must accurately reflect what's present in the build:

1. **Commands**: Only registered commands appear in output
2. **Features**: Feature flags match importability of modules
3. **Tasks**: Only registered tasks appear in output
4. **Pipelines**: Only defined pipelines appear in output

**Feature detection rules:**

| Feature | Detection |
|---------|-----------|
| `phase5_workflow` | `import codebatch.workflow` succeeds |
| `phase6_ui` | `import codebatch.ui` succeeds |
| `diff` | `import codebatch.ui.diff` succeeds |
| `cache` | `import codebatch.cache` succeeds (future) |

**Test**: In a build where a module is absent, `api` reports it correctly.

**Pass**: No phantom commands/features in output.

**Test location**: `tests/test_phase7_gates.py::TestGateP7ApiDyn`

---

### P7-API-STABLE: Deterministic Output

**Gate ID**: `P7-API-STABLE`
**Status**: ENFORCED

The `api --json` output must be byte-stable:

1. **No timing fields**: `created_at` is omitted from `api` output
2. **Sorted arrays**: `commands[]`, `pipelines[]`, `tasks[]`, `output_kinds[]` sorted by name/id
3. **Consistent ordering**: JSON keys in predictable order

**Test**: Run `codebatch api --json` twice.

**Pass**: Identical byte-for-byte output.

**Test location**: `tests/test_phase7_gates.py::TestGateP7ApiStable`

---

### P7-API-NO-SIDE-EFFECTS: Read-Only Capability Query

**Gate ID**: `P7-API-NO-SIDE-EFFECTS`
**Status**: ENFORCED

The `api` command must have no side effects:

1. **No store required**: Works without `--store` argument
2. **No file creation**: Creates no files anywhere
3. **No environment mutation**: Doesn't modify env vars or global state

**Test**: Run `codebatch api --json` with no store.

**Pass**: Succeeds with exit code 0, no files created.

**Test location**: `tests/test_phase7_gates.py::TestGateP7ApiNoSideEffects`

---

### P7-ERR: Error Envelope Compliance

**Gate ID**: `P7-ERR`
**Status**: ENFORCED

All `--json` failures must use the standard error envelope:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "hints": ["Actionable suggestion 1", "Actionable suggestion 2"],
    "details": {"key": "value"}
  }
}
```

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `error.code` | string | Machine-readable error code |
| `error.message` | string | Human-readable description |
| `error.hints` | string[] | Actionable suggestions (may be empty) |
| `error.details` | object | Context-specific data (may be empty) |

**Standard error codes:**

| Code | Usage |
|------|-------|
| `STORE_NOT_FOUND` | Store path doesn't exist |
| `STORE_INVALID` | Store exists but invalid |
| `BATCH_NOT_FOUND` | Batch ID not found |
| `SNAPSHOT_NOT_FOUND` | Snapshot ID not found |
| `COMMAND_ERROR` | Generic command failure |
| `SCHEMA_ERROR` | Invalid input data |
| `INTERNAL_ERROR` | Unexpected error |

**Test**: All `--json` failures return standard envelope.

**Pass**: Error shape matches schema, no raw text errors.

**Test location**: `tests/test_phase7_gates.py::TestGateP7Err`

---

### P7-SCHEMA: Schema Validation

**Gate ID**: `P7-SCHEMA`
**Status**: ENFORCED

All CLI JSON outputs must validate against published schemas:

1. **Schema files**: Located in `schemas/` directory
2. **Versioned**: Schema includes `schema_version` field
3. **CI validation**: Tests validate output against schemas

**Published schemas:**

| Schema | File | Description |
|--------|------|-------------|
| `codebatch.api` | `schemas/api.schema.json` | API capability response |
| `codebatch.error` | `schemas/error.schema.json` | Error envelope |

**Test**: Validate CLI JSON output against schemas.

**Pass**: No missing fields, no schema drift.

**Test location**: `tests/test_phase7_gates.py::TestGateP7Schema`

---

## Phase 8 Gates: Detailed Specifications

### P8-PARSE: Full AST Fidelity

**Gate ID**: `P8-PARSE`
**Status**: ENFORCED

Python AST must preserve function and class names, not just node types.

**Requirements:**

1. `FunctionDef` nodes include actual `name` field
2. `ClassDef` nodes include actual `name` field
3. `Name` nodes include `id` field
4. No 100-node truncation (use chunking for large files)

**Test:**
```python
# Input
def calculate_total(items):
    pass

class ShoppingCart:
    pass
```

**Expected AST contains:**
```json
{"type": "FunctionDef", "name": "calculate_total", "lineno": 1}
{"type": "ClassDef", "name": "ShoppingCart", "lineno": 4}
```

**Pass**: AST nodes include actual `name` field, not line number placeholders.

**Test location**: `tests/test_phase8_gates.py::TestGateP8Parse`

---

### P8-SYMBOLS: Real Symbol Names

**Gate ID**: `P8-SYMBOLS`
**Status**: ENFORCED

Symbol extraction must produce actual identifiers, not placeholders.

**Requirements:**

1. Function symbols have real names (not `function_<lineno>`)
2. Class symbols have real names (not `class_<lineno>`)
3. Scope tracking works (module, class, function)
4. Import edges have real module names

**Test:**
```python
# Input
import os
from pathlib import Path

class ShoppingCart:
    def add_item(self, item):
        total = 0
        return total
```

**Expected symbols:**
```json
{"kind": "symbol", "name": "ShoppingCart", "symbol_type": "class", "scope": "module"}
{"kind": "symbol", "name": "add_item", "symbol_type": "function", "scope": "ShoppingCart"}
{"kind": "symbol", "name": "total", "symbol_type": "variable", "scope": "add_item"}
```

**Expected edges:**
```json
{"kind": "edge", "edge_type": "imports", "target": "os"}
{"kind": "edge", "edge_type": "imports", "target": "pathlib.Path"}
```

**Pass**: No `function_<lineno>` or `class_<lineno>` placeholders anywhere.

**Test location**: `tests/test_phase8_gates.py::TestGateP8Symbols`

---

### P8-ROUNDTRIP: Parse → Symbols → Query

**Gate ID**: `P8-ROUNDTRIP`
**Status**: ENFORCED

Full pipeline must produce queryable results with real names.

**Requirements:**

1. Snapshot → Batch → Run completes without error
2. Symbols are queryable by actual name
3. Results match expected identifiers

**Test:**
1. Create snapshot of Python file with known functions
2. Run full pipeline
3. Query: `codebatch query symbols --batch <id> --store <path> --json`
4. Verify function names appear in results

**Pass**: Query returns symbols with real names, not placeholders.

**Test location**: `tests/test_phase8_gates.py::TestGateP8Roundtrip`

---

### P8-TREESITTER: JS/TS Real Parsing

**Gate ID**: `P8-TREESITTER`
**Status**: HARNESS (optional dependency)

JavaScript/TypeScript files must produce real AST via tree-sitter.

**Requirements:**

1. JS files produce structural AST (not token counts)
2. Function declarations include name
3. Class declarations include name
4. Import statements are parsed

**Test:**
```javascript
// Input
import { useState } from 'react';

function fetchData(url) {
    return fetch(url);
}

class DataService {
    constructor() {}
}
```

**Expected AST contains:**
```json
{"type": "function_declaration", "name": "fetchData"}
{"type": "class_declaration", "name": "DataService"}
{"type": "import_statement", "source": "react"}
```

**Pass**: JS/TS AST has structural nodes with names.

**Skip condition**: Gate is SKIPPED if tree-sitter is not installed.

**Test location**: `tests/test_phase8_gates.py::TestGateP8TreeSitter`

---

### P8-LINT-AST: AST-Aware Linting

**Gate ID**: `P8-LINT-AST`
**Status**: ENFORCED

Lint task must produce semantic diagnostics from AST analysis.

**Requirements:**

1. Detect unused imports
2. Detect unused local variables
3. Diagnostics include accurate line/column

**Test:**
```python
# Input
import os
import sys  # unused

def foo():
    x = 1  # unused
    return 42
```

**Expected diagnostics:**
```json
{"kind": "diagnostic", "code": "L101", "message": "Unused import 'sys'", "line": 2}
{"kind": "diagnostic", "code": "L102", "message": "Unused variable 'x'", "line": 5}
```

**Pass**: At least unused imports (L101) and unused variables (L102) detected.

**Test location**: `tests/test_phase8_gates.py::TestGateP8LintAst`

---

### P8-METRICS: Real Code Metrics

**Gate ID**: `P8-METRICS`
**Status**: ENFORCED

Analyze task must produce cyclomatic complexity metrics.

**Requirements:**

1. Complexity metric calculated from control flow
2. Function count metric
3. Class count metric

**Cyclomatic complexity rules:**
- Base complexity: 1
- +1 for each: `if`, `elif`, `for`, `while`, `except`, `with`, `and`, `or`, `assert`

**Test:**
```python
def simple():
    return 1

def complex_function(x):
    if x > 0:           # +1
        if x > 10:      # +1
            return "large"
        return "small"
    return "negative"
# complexity = 1 + 2 = 3
```

**Expected metrics:**
```json
{"kind": "metric", "path": "test.py", "metric": "complexity", "value": 3}
{"kind": "metric", "path": "test.py", "metric": "function_count", "value": 2}
```

**Pass**: Complexity values match expected calculations.

**Test location**: `tests/test_phase8_gates.py::TestGateP8Metrics`

---

### P8-SELF-HOST: Self-Analysis Works

**Gate ID**: `P8-SELF-HOST`
**Status**: ENFORCED

CodeBatch must be able to analyze its own source code meaningfully.

**Requirements:**

1. Snapshot of `src/codebatch/` succeeds
2. Full pipeline runs without errors
3. Symbols include real function names from source
4. No placeholder names in any output
5. At least 50 symbols extracted

**Test:**
```bash
codebatch snapshot ./src/codebatch --store ./self-test
codebatch batch init --snapshot <id> --pipeline full --store ./self-test
codebatch run --batch <id> --store ./self-test
codebatch query symbols --batch <id> --store ./self-test --json | wc -l
# Should be > 50
```

**Pass**: Real function names from codebatch source appear in symbol output.

**Test location**: `tests/test_phase8_gates.py::TestGateP8SelfHost`
