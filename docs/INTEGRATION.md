# CodeBatch Integration Guide

This guide explains how to integrate with CodeBatch from external tools,
editor extensions, and applications.

## Overview

CodeBatch provides a stable integration API through:

1. **`codebatch api --json`**: Discover capabilities and metadata
2. **`codebatch diagnose --json`**: Verify store integrity
3. **Standard JSON output**: All `--json` commands produce structured output
4. **Error envelopes**: Consistent error format for `--json` failures

## Quick Start

### 1. Check CodeBatch is installed

```bash
codebatch --version
```

### 2. Discover capabilities

```bash
codebatch api --json
```

This returns:
- Available commands with metadata
- Supported pipelines and tasks
- Output kinds with canonical keys
- Feature flags

### 3. Verify store compatibility

```bash
codebatch diagnose --store ./mystore --json
```

This checks:
- Store structure is valid
- Schema version is compatible
- Snapshots and batches are accessible

## API Response

The `api` command returns a stable JSON structure:

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
    "schema_version": 1,
    "features": {
      "phase5_workflow": true,
      "phase6_ui": true,
      "diff": true,
      "cache": true
    }
  },
  "commands": [...],
  "pipelines": [...],
  "tasks": [...],
  "output_kinds": [...]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `schema_version` | API schema version (integer) |
| `producer.version` | CodeBatch version (semver) |
| `build.features` | Available feature flags |
| `commands` | Available CLI commands |
| `output_kinds` | Output types with canonical keys |

### Command Metadata

Each command in `commands[]` includes:

```json
{
  "name": "inspect",
  "description": "Show all outputs for a file",
  "read_only": true,
  "supports_json": true,
  "supports_explain": true,
  "requires_store": true,
  "requires_batch": true,
  "since": "0.6.0",
  "group": "ui"
}
```

Use this to:
- Filter commands by capability (`read_only`, `supports_json`)
- Check version compatibility (`since`)
- Validate required arguments (`requires_store`, `requires_batch`)

## Error Handling

When a `--json` command fails, it returns a standard error envelope:

```json
{
  "error": {
    "code": "BATCH_NOT_FOUND",
    "message": "Batch not found: batch-xyz",
    "hints": ["Run: codebatch batch-list --store /path/to/store"],
    "details": {"batch_id": "batch-xyz"}
  }
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `STORE_NOT_FOUND` | Store path doesn't exist |
| `STORE_INVALID` | Store exists but is invalid |
| `BATCH_NOT_FOUND` | Batch ID not found |
| `SNAPSHOT_NOT_FOUND` | Snapshot ID not found |
| `PIPELINE_NOT_FOUND` | Pipeline name not found |
| `TASK_NOT_FOUND` | Task ID not found |
| `GATE_NOT_FOUND` | Gate ID not found |
| `INVALID_ARGUMENT` | Invalid argument value |
| `FILE_NOT_FOUND` | File not found |
| `COMMAND_ERROR` | Generic command error |
| `INTERNAL_ERROR` | Unexpected internal error |

## Common Workflows

### Workflow 1: Run analysis and get results

```bash
# Initialize store
codebatch init ./store

# Create snapshot from source
codebatch snapshot ./src --store ./store

# Create and run batch
codebatch batch init --snapshot snap-xxx --pipeline full --store ./store
codebatch run --batch batch-xxx --store ./store

# Get results as JSON
codebatch summary --batch batch-xxx --store ./store --json
codebatch inspect example.py --batch batch-xxx --store ./store --json
```

### Workflow 2: Compare two runs

```bash
# Run analysis on two versions
codebatch snapshot ./src-v1 --store ./store
codebatch batch init --snapshot snap-v1 --pipeline full --store ./store
codebatch run --batch batch-v1 --store ./store

codebatch snapshot ./src-v2 --store ./store
codebatch batch init --snapshot snap-v2 --pipeline full --store ./store
codebatch run --batch batch-v2 --store ./store

# Compare results
codebatch diff batch-v1 batch-v2 --store ./store --json
codebatch regressions batch-v1 batch-v2 --store ./store --json
codebatch improvements batch-v1 batch-v2 --store ./store --json
```

### Workflow 3: Query specific outputs

```bash
# Get all diagnostics
codebatch query diagnostics --batch batch-xxx --task 04_lint --store ./store --json

# Filter by severity
codebatch query diagnostics --batch batch-xxx --task 04_lint --store ./store --severity error --json

# Get statistics
codebatch query stats --batch batch-xxx --task 04_lint --store ./store --json
```

## JSON Schemas

Published schemas are in the `schemas/` directory:

| Schema | File | Description |
|--------|------|-------------|
| API | `schemas/api.schema.json` | `api --json` response |
| Error | `schemas/error.schema.json` | Error envelope |

### Validating Output

Using Python with jsonschema:

```python
import json
import subprocess
import jsonschema

# Load schema
with open("schemas/api.schema.json") as f:
    schema = json.load(f)

# Get API output
result = subprocess.run(
    ["codebatch", "api", "--json"],
    capture_output=True,
    text=True,
)
data = json.loads(result.stdout)

# Validate
jsonschema.validate(data, schema)
```

## Integration Do's and Don'ts

### Do

- **Check `api --json` first** to discover capabilities
- **Use `diagnose --json`** before operating on a store
- **Parse JSON output** for reliable data extraction
- **Check `read_only`** before running commands that might modify data
- **Use `since` field** to check version compatibility
- **Handle error envelopes** gracefully

### Don't

- **Don't parse human-readable output** - use `--json` instead
- **Don't assume command availability** - check `api` first
- **Don't hardcode paths** - use `--store` and `--batch` arguments
- **Don't ignore exit codes** - non-zero means failure
- **Don't write to the store directly** - use CodeBatch commands
- **Don't rely on undocumented behavior** - stick to the API contract

## Version Compatibility

### Checking compatibility

```python
import subprocess
import json

result = subprocess.run(
    ["codebatch", "api", "--json"],
    capture_output=True,
    text=True,
)
api = json.loads(result.stdout)

# Check API schema version
if api["schema_version"] < 1:
    raise RuntimeError("Unsupported API version")

# Check feature availability
if not api["build"]["features"].get("phase6_ui"):
    raise RuntimeError("UI features not available")

# Check specific command
cmd_names = {c["name"] for c in api["commands"]}
if "inspect" not in cmd_names:
    raise RuntimeError("inspect command not available")
```

### Semantic versioning

CodeBatch follows semantic versioning:

- **Major**: Breaking changes to the API
- **Minor**: New features, backward compatible
- **Patch**: Bug fixes, backward compatible

The `schema_version` field tracks API schema changes independently.

## Example: Python Integration

```python
import json
import subprocess
from pathlib import Path
from typing import Optional


class CodeBatchClient:
    """Simple CodeBatch integration client."""

    def __init__(self, store_path: str):
        self.store = Path(store_path)
        self._verify_store()

    def _run(self, *args, json_output: bool = True) -> dict:
        """Run a codebatch command."""
        cmd = ["codebatch"] + list(args)
        if json_output:
            cmd.append("--json")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if json_output:
            data = json.loads(result.stdout or result.stderr)
            if "error" in data:
                raise RuntimeError(f"{data['error']['code']}: {data['error']['message']}")
            return data

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return {"output": result.stdout}

    def _verify_store(self):
        """Verify store is valid."""
        result = self._run("diagnose", "--store", str(self.store))
        if result["status"] == "error":
            raise RuntimeError(f"Invalid store: {result['issues']}")

    def get_api(self) -> dict:
        """Get API capabilities."""
        return self._run("api")

    def summary(self, batch_id: str) -> dict:
        """Get batch summary."""
        return self._run("summary", "--batch", batch_id, "--store", str(self.store))

    def inspect(self, batch_id: str, path: str) -> list:
        """Get outputs for a file."""
        return self._run("inspect", path, "--batch", batch_id, "--store", str(self.store))

    def diff(self, batch_a: str, batch_b: str) -> dict:
        """Compare two batches."""
        return self._run("diff", batch_a, batch_b, "--store", str(self.store))


# Usage
client = CodeBatchClient("./mystore")
api = client.get_api()
print(f"CodeBatch {api['producer']['version']}")

summary = client.summary("batch-xyz")
print(f"Outputs: {summary['totals']['outputs']}")
```

## Support

- **Documentation**: See `docs/` directory
- **Issues**: Report at https://github.com/codebatch/codebatch/issues
- **API Schema**: See `schemas/` directory
