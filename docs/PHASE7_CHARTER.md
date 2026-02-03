# Phase 7 Charter: Integration API

**Status**: In Progress
**Goal**: Provide a stable, machine-readable integration surface for external tools

## Overview

Phase 7 transforms CodeBatch into an integration-ready tool by:

1. Exposing a capability API (`codebatch api --json`)
2. Standardizing error handling with JSON envelopes
3. Publishing JSON schemas for all outputs
4. Providing a diagnostic command for compatibility checks

This phase enables:
- Editor extensions (Phase 8)
- MAUI desktop app (Phase 9/10)
- Third-party integrations

## Guiding Constraints

### 1. Built-ins Only

The API reflects only what's compiled/packaged in the build:
- No filesystem scanning for plugins
- No runtime downloads
- No network checks
- No external configuration files

### 2. Semi-Dynamic Reflection

"Dynamic" means reflecting what THIS binary/package contains:
- Which modules are importable
- Which commands are registered
- Which tasks/pipelines are available
- Which features are enabled

It does NOT mean:
- Loading external plugins
- Scanning directories for tasks
- Enabling features based on runtime state

### 3. Deterministic Output

All `--json` output must be:
- Byte-stable across identical invocations
- Sorted deterministically (by name/id)
- Free of timing-dependent fields in capability reports

### 4. No Side Effects for Capability Queries

`codebatch api` must:
- Work without a store
- Create no files
- Modify no state

### 5. Structured Errors

All `--json` failures must:
- Return a standard error envelope
- Include actionable hints
- Use consistent error codes

---

## API Response Shape (v1)

```json
{
  "schema_name": "codebatch.api",
  "schema_version": 1,

  "producer": {
    "name": "codebatch",
    "version": "0.7.0"
  },

  "build": {
    "platform": "win32",
    "python": "3.14.0",
    "git_commit": "abc1234",
    "build_time": "2026-02-03T11:58:00Z",
    "features": {
      "phase5_workflow": true,
      "phase6_ui": true,
      "diff": true,
      "cache": false
    }
  },

  "commands": [
    {
      "name": "summary",
      "read_only": true,
      "supports_json": true,
      "supports_explain": true,
      "since": "0.6.0"
    }
  ],

  "pipelines": [
    {
      "name": "full",
      "tasks": [
        {"task_id": "01_parse", "deps": []},
        {"task_id": "02_analyze", "deps": ["01_parse"]},
        {"task_id": "03_symbols", "deps": ["01_parse"]},
        {"task_id": "04_lint", "deps": ["01_parse"]}
      ]
    }
  ],

  "tasks": [
    {
      "task_id": "01_parse",
      "type": "parse",
      "kinds_out": ["ast", "diagnostic"],
      "deps": []
    }
  ],

  "output_kinds": [
    {
      "kind": "diagnostic",
      "canonical_key": ["kind", "path", "line", "column", "code"]
    },
    {
      "kind": "metric",
      "canonical_key": ["kind", "path", "metric"]
    },
    {
      "kind": "symbol",
      "canonical_key": ["kind", "path", "name", "line"]
    },
    {
      "kind": "ast",
      "canonical_key": ["kind", "path", "object"]
    }
  ]
}
```

### Field Definitions

| Field | Description |
|-------|-------------|
| `schema_name` | Always `"codebatch.api"` |
| `schema_version` | Integer version of this schema |
| `producer.name` | Always `"codebatch"` |
| `producer.version` | Package version string |
| `build.platform` | `sys.platform` value |
| `build.python` | Python version |
| `build.git_commit` | Git commit hash (if available) |
| `build.build_time` | ISO8601 build timestamp (stable per build) |
| `build.features` | Semi-dynamic feature flags |
| `commands[]` | Registered CLI commands with metadata |
| `pipelines[]` | Available pipelines with task ordering |
| `tasks[]` | Task definitions with output kinds |
| `output_kinds[]` | Canonical key definitions (from P6-DIFF) |

### Feature Flags (Semi-Dynamic)

| Feature | Detection Rule |
|---------|---------------|
| `phase5_workflow` | `codebatch.workflow` importable |
| `phase6_ui` | `codebatch.ui` importable |
| `diff` | `codebatch.ui.diff` importable |
| `cache` | `codebatch.cache` importable (future) |

---

## Standard Error Envelope

When `--json` is used and a command fails:

```json
{
  "error": {
    "code": "BATCH_NOT_FOUND",
    "message": "Batch 'batch-xyz' does not exist",
    "hints": [
      "Run: codebatch batch-list --store <path>",
      "Check your --store path"
    ],
    "details": {
      "batch_id": "batch-xyz",
      "store": "/path/to/store"
    }
  }
}
```

### Error Codes

| Code | Meaning |
|------|---------|
| `STORE_NOT_FOUND` | Store path doesn't exist |
| `STORE_INVALID` | Store exists but invalid structure |
| `BATCH_NOT_FOUND` | Batch ID not found |
| `SNAPSHOT_NOT_FOUND` | Snapshot ID not found |
| `COMMAND_ERROR` | Generic command failure |
| `SCHEMA_ERROR` | Invalid input data |
| `INTERNAL_ERROR` | Unexpected error |

---

## Commit Plan

### Commit 1: docs - Phase 7 charter + gates
- `docs/PHASE7_CHARTER.md` (this file)
- Update `docs/GATES.md` with P7 gates

### Commit 2: feat(cli) - registry metadata
- Add metadata to command registration
- Add metadata to task definitions
- Properties: `read_only`, `supports_json`, `supports_explain`, `since`

### Commit 3: feat(cli) - codebatch api --json
- Implement `api` command
- Introspect command registry
- Compute feature flags
- Report pipelines/tasks/output_kinds

### Commit 4: schemas - add codebatch.api schema
- `schemas/api.schema.json`
- Document all fields

### Commit 5: test - validate api output against schema
- Test that `api --json` matches schema
- Test all required fields present

### Commit 6: test - stability + no-side-effects
- Test byte-stable output
- Test works without store
- Test creates no files

### Commit 7: feat(cli) - JSON error envelope
- Centralized error handling
- Standard envelope format
- Consistent exit codes

### Commit 8: test - error envelope validation
- Test error shape for common failures
- Test no raw text errors under `--json`

### Commit 9: feat(cli) - codebatch diagnose
- Store integrity check
- Version compatibility
- Schema support verification
- Machine-readable output

### Commit 10: docs - integration guide
- How to integrate with codebatch
- Sample CLI calls + JSON parsing
- Do's and don'ts

---

## Phase 7 Gates

### P7-API-DYN: Accurate Reflection

**Test**: In a build where a module is absent, `api` reports it correctly.

**Pass**: No phantom commands/features in output.

### P7-API-STABLE: Deterministic Output

**Test**: Run `codebatch api --json` twice.

**Pass**: Identical output (no timing-dependent fields).

### P7-API-NO-SIDE-EFFECTS: Read-Only Capability Query

**Test**: Run `codebatch api --json` with no store present.

**Pass**: Succeeds and creates no files.

### P7-ERR: Error Envelope Compliance

**Test**: All `--json` failures return standard envelope.

**Pass**: Error shape matches schema, includes code/message/hints.

### P7-SCHEMA: Schema Validation

**Test**: Validate CLI JSON output against published schemas.

**Pass**: No missing fields, no drift from schema.

---

## What Phase 7 Unlocks

After Phase 7:
- Editor extensions can discover capabilities via `api`
- MAUI app can validate compatibility before connecting
- Third-party tools have a stable integration contract
- Marketing can say: "codebatch has a stable integration API"

No core refactoring needed to support integrations.

---

## Non-Goals

Phase 7 does NOT include:
- Plugin system
- External task loading
- Network-based discovery
- Runtime feature downloads
- WebSocket/HTTP server mode

These are explicitly out of scope and reserved for future phases.
