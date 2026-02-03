# Task Reference

This document describes the four built-in tasks in CodeBatch's `full` pipeline.
Each task's capabilities, output kinds, and language support are detailed.

---

## Pipeline Overview

The `full` pipeline runs these tasks in order:

```
01_parse → 02_analyze → 03_symbols → 04_lint
```

Each task reads from snapshot files and/or prior task outputs, producing indexed
records that can be queried.

---

## 01_parse: AST Extraction

**Purpose**: Parse source files and produce Abstract Syntax Trees (AST).

### Capabilities by Language

| Language   | Parser        | AST Mode | Notes                                |
|------------|---------------|----------|--------------------------------------|
| Python     | stdlib `ast`  | Full     | Names preserved (FunctionDef.name, etc.) |
| JavaScript | tree-sitter*  | Full     | Real structural AST                  |
| TypeScript | tree-sitter*  | Full     | Full type annotation support         |
| JavaScript | fallback      | Token    | Without tree-sitter (import count only) |
| TypeScript | fallback      | Token    | Without tree-sitter (import count only) |
| Other      | None          | Skip     | No parsing, analysis still available |

*tree-sitter is optional: `pip install codebatch[treesitter]`

### Output Kinds

| Kind  | Description                          | Fields                           |
|-------|--------------------------------------|----------------------------------|
| `ast` | Parsed AST stored in CAS             | `path`, `object`, `format`, `ast_mode` |

### AST Format

**Python AST (Full Mode)**:
```json
{
  "type": "Module",
  "ast_mode": "full",
  "body": [
    {
      "type": "FunctionDef",
      "name": "calculate_total",
      "lineno": 1,
      "col_offset": 0,
      "args": {
        "type": "arguments",
        "args": [
          {"type": "arg", "arg": "items", "lineno": 1}
        ]
      },
      "body": [...]
    }
  ]
}
```

**JavaScript/TypeScript AST (tree-sitter)**:
```json
{
  "type": "program",
  "ast_mode": "full",
  "parser": "tree-sitter",
  "children": [
    {
      "type": "function_declaration",
      "name": "fetchData",
      "start_point": [0, 0],
      "end_point": [2, 1],
      "children": [...]
    }
  ]
}
```

**JavaScript Fallback (Token Mode)**:
```json
{
  "type": "token_summary",
  "ast_mode": "summary",
  "parser": "regex",
  "import_count": 5,
  "function_pattern_count": 3,
  "class_pattern_count": 1
}
```

### Query Examples

```bash
# List all AST outputs for a batch
codebatch query outputs --batch <id> --store ./store --kind ast

# Get Python files with full AST
codebatch query outputs --batch <id> --store ./store --kind ast --json | \
  jq '.[] | select(.format == "json" and .ast_mode == "full")'
```

### Known Limitations

- **Python**: Encoding assumed UTF-8. Syntax errors produce `error` output, not AST.
- **JavaScript**: Dynamic imports not tracked. JSX requires tree-sitter.
- **TypeScript**: Type-only imports included. Decorators captured as nodes.
- **Large files**: ASTs >1MB are automatically chunked.

---

## 02_analyze: File Metrics

**Purpose**: Produce file-level metrics for all files in the snapshot.

### Capabilities

| Metric         | Languages | Source          | Description                    |
|----------------|-----------|-----------------|--------------------------------|
| `bytes`        | All       | Snapshot        | File size in bytes             |
| `loc`          | Text      | File content    | Lines of code (non-empty)      |
| `lang`         | All       | Snapshot hint   | Language identifier            |
| `complexity`   | Python    | AST             | Total cyclomatic complexity    |
| `max_complexity` | Python  | AST             | Highest function complexity    |
| `function_count` | Python  | AST             | Number of functions            |
| `class_count`  | Python   | AST             | Number of classes              |
| `import_count` | Python   | AST             | Number of import statements    |

### Output Kinds

| Kind     | Description               | Fields                            |
|----------|---------------------------|-----------------------------------|
| `metric` | Single metric value       | `path`, `metric`, `value`         |

### Cyclomatic Complexity Calculation

Complexity starts at 1 for each function and increments for:

| Construct       | Contribution |
|-----------------|--------------|
| `if` / `elif`   | +1 each      |
| `for` / `while` | +1 each      |
| `except`        | +1 each      |
| `and` / `or`    | +1 per operator |
| `assert`        | +1           |
| Comprehensions  | +1 each      |
| Ternary (`if` expr) | +1       |

**Example**:
```python
def process(items):      # base: 1
    if not items:        # +1
        return []
    result = []
    for item in items:   # +1
        if item > 0:     # +1
            result.append(item)
    return result
# Total complexity: 4
```

### Query Examples

```bash
# Get all metrics for a file
codebatch query outputs --batch <id> --store ./store --kind metric --path src/main.py

# Find high-complexity files
codebatch query outputs --batch <id> --store ./store --kind metric --json | \
  jq '.[] | select(.metric == "complexity" and .value > 10)'

# Get total lines of code
codebatch query outputs --batch <id> --store ./store --kind metric --json | \
  jq '[.[] | select(.metric == "loc")] | map(.value) | add'
```

### Known Limitations

- **LOC**: Counts non-empty lines, not SLOC (includes comments).
- **Complexity**: Python only. JS/TS complexity requires tree-sitter AST (future).
- **Binary files**: No LOC metric, bytes only.

---

## 03_symbols: Symbol Extraction

**Purpose**: Extract named symbols (functions, classes, variables) and import edges.

### Capabilities by Language

| Language   | Functions | Classes | Variables | Imports | Exports |
|------------|-----------|---------|-----------|---------|---------|
| Python     | Yes       | Yes     | Yes       | Yes     | N/A     |
| JavaScript | Yes*      | Yes*    | Yes*      | Yes*    | Yes*    |
| TypeScript | Yes*      | Yes*    | Yes*      | Yes*    | Yes*    |

*Requires tree-sitter for full support. Fallback mode uses regex patterns.

### Output Kinds

| Kind     | Description               | Fields                                      |
|----------|---------------------------|---------------------------------------------|
| `symbol` | Named symbol definition   | `path`, `name`, `symbol_type`, `scope`, `line`, `column` |
| `edge`   | Dependency relationship   | `path`, `edge_type`, `source`, `target`     |

### Symbol Types

| Type       | Description                              | Example                    |
|------------|------------------------------------------|----------------------------|
| `function` | Function or method definition            | `def calculate()`          |
| `class`    | Class definition                         | `class ShoppingCart`       |
| `variable` | Variable assignment in function/method   | `total = 0`                |
| `parameter`| Function/method parameter                | `def foo(x, y)`            |
| `import`   | Imported name                            | `from os import path`      |

### Edge Types

| Type      | Description                     | Example                        |
|-----------|---------------------------------|--------------------------------|
| `imports` | Module import dependency        | `import os` → target: `os`     |
| `exports` | Exported symbol (JS/TS only)    | `export function foo` → `foo`  |

### Scope Tracking

Symbols include their enclosing scope:

```python
# Input
class Cart:
    def add(self, item):
        price = item.price
```

```json
{"name": "Cart", "symbol_type": "class", "scope": "module"}
{"name": "add", "symbol_type": "function", "scope": "Cart"}
{"name": "item", "symbol_type": "parameter", "scope": "add"}
{"name": "price", "symbol_type": "variable", "scope": "add"}
```

### Query Examples

```bash
# List all functions in a file
codebatch query outputs --batch <id> --store ./store --kind symbol --path src/main.py --json | \
  jq '.[] | select(.symbol_type == "function")'

# Find all classes
codebatch query outputs --batch <id> --store ./store --kind symbol --json | \
  jq '.[] | select(.symbol_type == "class") | .name'

# Get import graph edges
codebatch query outputs --batch <id> --store ./store --kind edge --json | \
  jq '.[] | select(.edge_type == "imports")'

# Find a specific function by name
codebatch query outputs --batch <id> --store ./store --kind symbol --json | \
  jq '.[] | select(.name == "calculate_total")'
```

### Known Limitations

- **Python**: Comprehension variables not tracked as symbols.
- **JavaScript/TypeScript**: Dynamic imports (`import()`) not tracked.
- **Fallback mode**: Only function/class patterns detected, no variables.
- **Cross-file**: No type resolution across modules.

---

## 04_lint: Code Quality Diagnostics

**Purpose**: Detect code quality issues through text-based and AST-aware rules.

### Rule Categories

#### Text-Based Rules (All Languages)

| Code | Rule                     | Description                           |
|------|--------------------------|---------------------------------------|
| L001 | Trailing whitespace      | Lines ending with spaces/tabs         |
| L002 | Mixed indentation        | Tabs and spaces in same file          |
| L003 | Line too long            | Lines exceeding 120 characters        |
| L004 | No newline at end        | File doesn't end with newline         |
| L005 | Multiple blank lines     | More than 2 consecutive blank lines   |

#### AST-Aware Rules (Python Only)

| Code | Rule                | Description                                |
|------|---------------------|--------------------------------------------|
| L101 | Unused import       | Import statement not referenced in code    |
| L102 | Unused variable     | Local variable assigned but never used     |
| L103 | Variable shadowing  | Inner scope shadows outer scope variable   |

### Output Kinds

| Kind         | Description           | Fields                                     |
|--------------|-----------------------|--------------------------------------------|
| `diagnostic` | Code quality issue    | `path`, `code`, `message`, `severity`, `line`, `column` |

### Severity Levels

| Severity  | Meaning                                    |
|-----------|--------------------------------------------|
| `error`   | Must be fixed (syntax errors, etc.)        |
| `warning` | Should be fixed (unused code, etc.)        |
| `info`    | Style suggestion                           |

### Rule Details

#### L101: Unused Import

Detects imports that are never referenced in the code.

```python
import os       # Used - os.path referenced below
import sys      # UNUSED - never referenced
from typing import List  # Used in type annotation

def example():
    return os.path.exists("/tmp")

items: List[int] = []
```

**Diagnostic**: `L101: Unused import 'sys'` at line 2

#### L102: Unused Variable

Detects local variables that are assigned but never read.

```python
def calculate(x):
    temp = x * 2    # UNUSED - never read
    result = x + 1  # Used - returned below
    return result
```

**Diagnostic**: `L102: Unused variable 'temp'` at line 2

**Note**: Does not flag:
- Module-level variables (may be exports)
- Variables starting with `_` (intentionally unused)
- Loop variables in comprehensions

#### L103: Variable Shadowing

Detects inner scope variables that shadow outer scope.

```python
x = 10  # Outer scope

def example():
    x = 20  # Shadows outer 'x'
    return x
```

**Diagnostic**: `L103: Variable 'x' shadows outer scope` at line 4

### Query Examples

```bash
# Get all diagnostics for a batch
codebatch query diagnostics --batch <id> --store ./store

# Filter by severity
codebatch query outputs --batch <id> --store ./store --kind diagnostic --json | \
  jq '.[] | select(.severity == "warning")'

# Find unused imports
codebatch query outputs --batch <id> --store ./store --kind diagnostic --json | \
  jq '.[] | select(.code == "L101")'

# Count diagnostics by code
codebatch query outputs --batch <id> --store ./store --kind diagnostic --json | \
  jq 'group_by(.code) | map({code: .[0].code, count: length})'

# Get errors only
codebatch errors --batch <id> --store ./store
```

### Known Limitations

- **AST rules**: Python only. JS/TS linting requires external tools.
- **L102 false positives**: Doesn't track complex attribute usage.
- **L103**: Only tracks direct shadowing, not closure capture.
- **No auto-fix**: Diagnostics are informational only.

---

## Output Schema Reference

### Common Fields

All output records include:

| Field            | Type   | Description                    |
|------------------|--------|--------------------------------|
| `schema_version` | int    | Record schema version (1)      |
| `snapshot_id`    | string | Source snapshot identifier     |
| `batch_id`       | string | Execution batch identifier     |
| `task_id`        | string | Task that produced this output |
| `shard_id`       | string | Shard that produced this output|
| `path`           | string | Source file path               |
| `kind`           | string | Output type (ast, symbol, etc.)|
| `ts`             | string | ISO timestamp                  |

### AST Record

```json
{
  "kind": "ast",
  "path": "src/main.py",
  "object": "sha256:abc123...",
  "format": "json",
  "ast_mode": "full"
}
```

### Symbol Record

```json
{
  "kind": "symbol",
  "path": "src/main.py",
  "name": "calculate_total",
  "symbol_type": "function",
  "scope": "module",
  "line": 10,
  "column": 0
}
```

### Edge Record

```json
{
  "kind": "edge",
  "path": "src/main.py",
  "edge_type": "imports",
  "source": "src/main.py",
  "target": "os"
}
```

### Metric Record

```json
{
  "kind": "metric",
  "path": "src/main.py",
  "metric": "complexity",
  "value": 15
}
```

### Diagnostic Record

```json
{
  "kind": "diagnostic",
  "path": "src/main.py",
  "code": "L101",
  "message": "Unused import 'sys'",
  "severity": "warning",
  "line": 2,
  "column": 0
}
```

---

## Configuration

Tasks are configured in the pipeline definition. The `full` pipeline uses
default settings:

```python
PIPELINES = {
    "full": [
        {"task": "parse", "id": "01_parse"},
        {"task": "analyze", "id": "02_analyze", "depends": ["01_parse"]},
        {"task": "symbols", "id": "03_symbols", "depends": ["01_parse"]},
        {"task": "lint", "id": "04_lint", "depends": ["01_parse"]},
    ],
}
```

### Task Dependencies

```
            ┌─────────────┐
            │  Snapshot   │
            └──────┬──────┘
                   │
            ┌──────▼──────┐
            │  01_parse   │
            └──────┬──────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
│02_analyze │ │03_symbols│ │ 04_lint  │
└───────────┘ └──────────┘ └──────────┘
```

All downstream tasks can read AST outputs from `01_parse` via `iter_prior_outputs()`.

---

## Language Support Summary

| Feature              | Python | JavaScript | TypeScript |
|----------------------|--------|------------|------------|
| Full AST             | Yes    | tree-sitter| tree-sitter|
| Symbol extraction    | Yes    | tree-sitter| tree-sitter|
| Import tracking      | Yes    | tree-sitter| tree-sitter|
| Complexity metrics   | Yes    | No         | No         |
| AST-aware linting    | Yes    | No         | No         |
| Text-based linting   | Yes    | Yes        | Yes        |

**tree-sitter**: Optional dependency. Install with `pip install codebatch[treesitter]`

Without tree-sitter, JavaScript/TypeScript files:
- Get token-mode parsing (import counts, function patterns)
- Have limited symbol extraction (regex-based)
- Still receive text-based lint diagnostics
