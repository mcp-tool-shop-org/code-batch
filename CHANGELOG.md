# Changelog

All notable changes to the CodeBatch specification and implementation.

## [Unreleased]

## [1.0.0] - 2026-02-27

### Added
- SECURITY.md with vulnerability reporting and data scope
- SHIP_GATE.md quality gates (all hard gates pass)
- SCORECARD.md with pre/post remediation scores
- LICENSE file (MIT)
- Security & Data Scope section in README

### Changed
- Promoted from v0.1.1 to v1.0.0 (stable release)
- Development Status classifier updated to Production/Stable

---

## [Phase 8] - 2025-02-03

Phase 8: Real Workloads - Replaced stub logic with production-ready implementations.

### Added

**Parse Task (01_parse)**
- Full-fidelity Python AST with `FunctionDef.name`, `ClassDef.name`, `Name.id` preserved
- Tree-sitter integration for JavaScript/TypeScript parsing (optional dependency)
- Graceful fallback to token-mode parsing when tree-sitter unavailable
- Enhanced AST serialization including control flow nodes (If.test, BoolOp, etc.)

**Symbols Task (03_symbols)**
- Real Python symbol extraction with actual identifier names
- Scope tracking (module, class, function)
- Function parameters and variable assignments
- Import edge extraction with real module names
- JavaScript/TypeScript symbol extraction via tree-sitter

**Lint Task (04_lint)**
- L101: Unused import detection (AST-aware)
- L102: Unused variable detection (AST-aware)
- L103: Variable shadowing warnings (AST-aware)
- Proper distinction between variable definitions and uses

**Analyze Task (02_analyze)**
- Cyclomatic complexity calculation from AST control flow
- `max_complexity` metric (highest function complexity)
- `function_count`, `class_count`, `import_count` metrics

**Documentation**
- Phase 8 charter with gates (docs/PHASE8_CHARTER.md)
- Comprehensive task reference (docs/TASKS.md)
- Updated gates documentation

**Testing**
- P8-PARSE: Full AST fidelity gate
- P8-SYMBOLS: Real symbol names gate
- P8-ROUNDTRIP: Parse → Symbols → Query gate
- P8-TREESITTER: JS/TS real parsing gate (optional)
- P8-LINT-AST: AST-aware linting gate
- P8-METRICS: Code metrics gate
- P8-SELF-HOST: Self-analysis validation

### Changed
- Python AST now includes full node names instead of line-number placeholders
- Symbol extraction produces actual identifiers (`calculate_total` not `function_42`)
- Complexity metrics use real control-flow analysis

### Fixed
- AST serialization now captures `Expr.value`, `Call.func`, `Attribute.value`
- BoolOp nodes properly serialized for complexity calculation
- Assignment targets no longer incorrectly flagged as variable uses
- TypeScript class names extracted from `type_identifier` nodes

### Dependencies
- Optional: `tree-sitter>=0.21.0`, `tree-sitter-javascript>=0.21.0`, `tree-sitter-typescript>=0.21.0`
- Install with: `pip install codebatch[treesitter]`

---

## [spec-v1.0-draft] - 2025-02-02

### Added
- Complete storage and execution specification (SPEC.md)
- Content-addressed object store layout
- Snapshot immutability contract
- Batch, task, and shard execution model
- Output record indexing semantics
- Query model guarantees
- Large output chunking rules
- Versioning requirements for all records

### Defined
- 14 specification sections covering full execution lifecycle
- 6 global invariants for system correctness
- Compliance criteria for implementations

---

[Unreleased]: https://github.com/mcp-tool-shop-org/code-batch/compare/spec-v1.0-draft...HEAD
[spec-v1.0-draft]: https://github.com/mcp-tool-shop-org/code-batch/releases/tag/spec-v1.0-draft
