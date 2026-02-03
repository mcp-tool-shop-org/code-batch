# Phase 8 Charter: Real Workloads

**Status**: Complete
**Goal**: Replace stub logic with real implementations to make the engine actually useful

## Overview

Phase 8 transforms CodeBatch from a working-but-limited prototype into a genuinely
useful code analysis engine. The infrastructure (Phases 1-7) is solid; now we need
real workloads.

## Current State (Honest Assessment)

| Task | What Works | What's Broken/Stubbed |
|------|------------|----------------------|
| **01_parse** | Python AST (summarized), JS tokenization | JS has no real AST; Python AST truncated to 100 nodes; names not preserved |
| **02_analyze** | Bytes, LOC, lang metrics | `parse_status` check is `pass`; LOC counts all lines not just code |
| **03_symbols** | Structure exists | Python symbols have NO NAMES (just `function_<lineno>`); JS is fake |
| **04_lint** | 5 text-based rules work | AST-based rules are `pass`; no language-specific linting |

**The critical gap:** Symbol extraction is broken. Without real symbol names, the
engine can't do meaningful code analysis.

---

## Guiding Constraints

### 1. Fix Symbols First

Symbol extraction is the foundation. Parse → Symbols → Everything Else.
If we can't extract `def foo():` as `name="foo"`, nothing downstream works.

### 2. Real Languages, Real Parsers

- Python: stdlib `ast` module (full fidelity, not summarized)
- JavaScript/TypeScript: tree-sitter (real parser, not regex tokenization)
- No fake data, no placeholders, no `<lineno>` hacks

### 3. Self-Hosting Test

Phase 8 is complete when we can run CodeBatch on its own source code and get
meaningful results: real function names, real import graphs, real lint issues.

### 4. Preserve Determinism

All outputs must remain deterministic. Same input → same output.
No timestamp-dependent or random behavior.

---

## What Phase 8 Delivers

### Parse Task (01_parse)

**Before:** Python AST truncated to 100 nodes, no names. JS is regex tokenization.

**After:**
- Python: Full AST with `FunctionDef.name`, `ClassDef.name`, `Name.id` preserved
- JavaScript/TypeScript: Real AST via tree-sitter
- Chunking for large files (existing infrastructure)

### Symbols Task (03_symbols)

**Before:** `name="function_42"` (line number placeholder)

**After:**
- `name="calculate_total"` (actual identifier)
- Scope tracking: module, class, function
- Parameters and return type annotations
- Real import edges with module names

### Lint Task (04_lint)

**Before:** 5 text-based rules only (trailing whitespace, line length, etc.)

**After:**
- Existing text rules (preserved)
- AST-aware rules: unused imports, undefined names, shadowing
- Leverages symbol table from 03_symbols

### Analyze Task (02_analyze)

**Before:** bytes, LOC (all non-empty lines), lang

**After:**
- Cyclomatic complexity (from AST control flow)
- Function count, class count
- Import count
- Fixed `parse_status` correlation

---

## External Dependencies

**Required (add to pyproject.toml):**

```toml
[project.optional-dependencies]
treesitter = [
    "tree-sitter>=0.21.0",
    "tree-sitter-javascript>=0.21.0",
    "tree-sitter-typescript>=0.21.0",
]
```

Tree-sitter is optional; Python analysis works without it.
JS/TS analysis requires tree-sitter.

---

## Commit Plan

### Commit 1: docs - Phase 8 charter + gates
- `docs/PHASE8_CHARTER.md` (this file)
- Update `docs/GATES.md` with P8 gates

### Commit 2: feat(parse) - Full Python AST with names
- Rewrite `parse_python()` to preserve node names
- Include `FunctionDef.name`, `ClassDef.name`, `Name.id`
- Remove 100-node truncation
- Add `ast_mode: "full"`

### Commit 3: feat(symbols) - Real Python symbol extraction
- Extract actual names from AST
- Proper scope tracking
- Function parameters and annotations
- Variable assignments with names

### Commit 4: test - Symbol extraction golden tests
- Fixtures with known Python files
- Assert exact symbol names extracted
- Gate P8-SYMBOLS enforcement

### Commit 5: feat(parse) - Tree-sitter for JS/TS
- Integrate tree-sitter
- Real AST parsing for JavaScript/TypeScript
- Graceful fallback if tree-sitter unavailable

### Commit 6: feat(symbols) - JS/TS symbol extraction
- Extract from tree-sitter AST
- Functions, classes, const/let declarations
- Import/export edges

### Commit 7: feat(lint) - AST-aware Python rules
- Unused imports detection
- Undefined name references
- Variable shadowing warnings

### Commit 8: feat(analyze) - Real code metrics
- Cyclomatic complexity
- Function/class/import counts
- Fix `parse_status` check

### Commit 9: test - End-to-end pipeline validation
- Self-test on codebatch source
- Performance baseline
- Gate enforcement

### Commit 10: docs - Updated task documentation
- Actual capabilities per language
- Query examples with real output
- Known limitations

---

## Phase 8 Gates

### P8-PARSE: Full AST Fidelity

**Definition:** Python AST must preserve function and class names.

**Test:**
```python
# Input
def calculate_total(items):
    pass

# AST must contain
{"type": "FunctionDef", "name": "calculate_total", ...}
```

**Pass:** AST nodes include actual `name` field, not line numbers.

---

### P8-SYMBOLS: Real Symbol Names

**Definition:** Symbol extraction produces actual identifiers.

**Test:**
```python
# Input
class ShoppingCart:
    def add_item(self, item):
        pass

# Symbols must include
{"kind": "symbol", "name": "ShoppingCart", "symbol_type": "class", ...}
{"kind": "symbol", "name": "add_item", "symbol_type": "function", "scope": "ShoppingCart", ...}
```

**Pass:** No `function_<lineno>` or `class_<lineno>` placeholders in output.

---

### P8-ROUNDTRIP: Parse → Symbols → Query

**Definition:** Full pipeline produces queryable results with real names.

**Test:**
1. Snapshot a Python file with known functions
2. Run batch with full pipeline
3. Query symbols by name
4. Results match expected names

**Pass:** `codebatch query symbols --name "calculate_total"` returns the function.

---

### P8-TREESITTER: JS/TS Real Parsing

**Definition:** JavaScript/TypeScript files produce real AST (not tokenization).

**Test:**
```javascript
// Input
function fetchData(url) {
    return fetch(url);
}

// AST must contain
{"type": "function_declaration", "name": "fetchData", ...}
```

**Pass:** JS/TS AST has structural nodes, not just token counts.

**Note:** This gate is SKIPPED if tree-sitter is not installed.

---

### P8-LINT-AST: AST-Aware Linting

**Definition:** Lint task produces semantic diagnostics from AST analysis.

**Test:**
```python
# Input
import os  # unused

def foo():
    x = 1  # unused local
```

**Expected diagnostics:**
- `L101: Unused import 'os'`
- `L102: Unused variable 'x'`

**Pass:** At least 2 AST-aware rules produce correct diagnostics.

---

### P8-METRICS: Real Code Metrics

**Definition:** Analyze task produces cyclomatic complexity.

**Test:**
```python
def complex_function(x):
    if x > 0:
        if x > 10:
            return "large"
        return "small"
    return "negative"
```

**Expected:** `{"kind": "metric", "metric": "complexity", "value": 3, ...}`

**Pass:** Complexity metric matches expected value for control flow.

---

### P8-SELF-HOST: Self-Analysis Works

**Definition:** CodeBatch can analyze its own source code meaningfully.

**Test:**
1. `codebatch snapshot ./src/codebatch --store ./test-store`
2. `codebatch batch init --snapshot <id> --pipeline full --store ./test-store`
3. `codebatch run --batch <id> --store ./test-store`
4. `codebatch query symbols --batch <id> --store ./test-store`

**Pass:**
- Symbols include real function names from codebatch source
- No placeholder names in output
- At least 50 symbols extracted

---

## Completion Criteria

Phase 8 is **done** when:

- [x] Python AST includes real function/class/variable names
- [x] Symbol extraction produces actual identifiers (not `function_<lineno>`)
- [x] JS/TS has real parsing via tree-sitter (optional dependency)
- [x] At least 3 AST-aware lint rules work
- [x] Analyze produces cyclomatic complexity metric
- [x] Self-test: running on codebatch source produces meaningful results
- [x] All P8 gates pass (except P8-TREESITTER if tree-sitter not installed)

---

## Non-Goals

Phase 8 does NOT include:

- **New languages** beyond Python/JS/TS (future phases)
- **IDE integration** (Phase 9+)
- **Incremental analysis** (would require architecture changes)
- **Cross-file analysis** (type inference across modules)
- **Auto-fix** capabilities

These are explicitly out of scope.

---

## Risk: Tree-sitter Complexity

Tree-sitter adds native dependencies. Mitigation:
- Make it optional (`[treesitter]` extra)
- Python analysis works without it
- Clear error message if JS/TS analysis attempted without tree-sitter
- CI tests both with and without tree-sitter
