# Phase 6 Charter: UI/UX - Exploration + Comparison

## One-Line Purpose

**Read-only views and comparisons over existing outputs, without changing any data.**

---

## Guiding Constraints (enforced every commit)

| Constraint         | Definition                                              |
|--------------------|---------------------------------------------------------|
| Read-only          | Phase 6 must not write under the store root             |
| Output determinism | Stable ordering, no randomization                       |
| No semantics       | Phase 6 only renders existing outputs                   |
| `--json` available | All commands support structured JSON output             |
| Non-TTY safe       | Works in headless environments; `--no-color` respected  |

---

## Scope: What Phase 6 Delivers

### Core Commands

| Command                  | Purpose                                          |
|--------------------------|--------------------------------------------------|
| `inspect <path>`         | File drilldown: show all outputs for a file      |
| `explain <cmd>`          | Show data sources used by a view                 |
| `diff <A> <B>`           | Compare two batches (added/removed/changed)      |
| `regressions <A> <B>`    | Diagnostics added or worsened between batches    |
| `improvements <A> <B>`   | Diagnostics removed or improved between batches  |

### UI Module

| Component       | Purpose                                               |
|-----------------|-------------------------------------------------------|
| `ui/format.py`  | Tables, stable sorting, optional color                |
| `ui/pager.py`   | Simple paging (no background refresh)                 |
| `ui/diff.py`    | Pure set-math comparison engine                       |

### Flags

| Flag           | Behavior                                              |
|----------------|-------------------------------------------------------|
| `--json`       | Structured JSON output (stable key order)             |
| `--no-color`   | Disable ANSI colors                                   |
| `--explain`    | Show data sources instead of data                     |
| `--kind`       | Filter by output kind (diagnostic, metric, etc.)      |

---

## Non-Goals (Explicit)

Phase 6 does NOT include:

- **Store writes** — No output persistence, no cache updates
- **Events dependency** — Views derive from outputs, not events
- **Background refresh** — No polling, no threads, no daemons
- **TUI framework** — No curses, no rich-live, no complex widgets
- **Network APIs** — No HTTP server, no WebSocket streaming
- **New truth stores** — No new indexes beyond existing outputs

If it writes to the store, it's not Phase 6.

---

## Gates

### P6-RO: Read-Only Enforcement

**Definition:** Phase 6 commands must not modify the store.

**Pass criteria:**
- Snapshot store tree before command
- Run any Phase 6 command
- Snapshot store tree after command
- Trees must be identical

**Status:** ENFORCED

### P6-DIFF: Diff Correctness

**Definition:** Diff output must match pure set math.

**Pass criteria:**
- Given batches A and B with known outputs
- `diff A B` produces correct added/removed/changed sets
- Results are deterministic across runs

**Status:** ENFORCED

### P6-EXPLAIN: Explain Fidelity

**Definition:** `--explain` must accurately describe data sources.

**Pass criteria:**
- Explanation lists output kinds used
- Explanation lists tasks referenced
- Explanation does NOT mention events as a dependency
- Explanation is deterministic

**Status:** ENFORCED

### P6-HEADLESS: Headless Compatibility

**Definition:** All commands work without TTY.

**Pass criteria:**
- Run commands with `stdout` redirected to file
- `--no-color` produces no ANSI escape sequences
- `--json` output is valid JSON
- Exit codes are correct

**Status:** ENFORCED

### P6-ISOLATION: UI Module Isolation

**Definition:** UI module can be removed without breaking core.

**Pass criteria:**
- Remove `src/codebatch/ui/` directory
- Phases 2-5 tests still pass
- Or: UI imports are guarded with conditional checks

**Status:** HARNESS

---

## Deliverables by Commit

### Perimeter (2 commits)

1. **docs: Phase 6 charter + gates** — This document + GATES.md updates
2. **test: Phase 6 gate harness** — Placeholder tests with xfail/skip

### UI Isolation (3 commits)

3. **feat(ui): UI module boundary** — `ui/__init__.py`, `format.py`, `pager.py`
4. **feat(ui): stable rendering contracts** — `render_table`, `render_json`
5. **test(ui): golden tests** — Deterministic output snapshots

### Core Commands (4 commits)

6. **feat(cli): inspect** — File drilldown command
7. **test: inspect e2e** — End-to-end tests with fixtures
8. **feat(cli): explain + --explain** — Data source explanation
9. **test: explain fidelity** — Lock explain semantics

### Comparison (4 commits)

10. **feat(diff): core diff engine** — Pure set math in `ui/diff.py`
11. **feat(cli): diff command** — CLI wrapper for diff engine
12. **feat(cli): regressions + improvements** — Diagnostic delta commands
13. **test: diff/regressions correctness** — Fixture-based verification

### Enforcement (1 commit)

14. **test(gates): Phase 6 read-only + headless** — Gate implementations

---

## Completion Criteria

Phase 6 is **done** when:

- [ ] `inspect`, `diff`, `regressions`, `improvements`, `--explain` exist
- [ ] `--json` for each is stable and deterministic
- [ ] P6-RO gate passes (store tree unchanged)
- [ ] P6-HEADLESS gate passes (non-TTY works)
- [ ] P6-ISOLATION gate passes or is guarded
- [ ] All 14 commits merged to main

---

## Optional Extensions (post-completion only)

These are polish, not core:

1. **Interactive pager toggle** — `--pager auto|always|never`
2. **Rich views** — `top --codes`, `files --with diagnostic`
3. **TUI** — Separate branch with own gates (no store writes, no threads)
