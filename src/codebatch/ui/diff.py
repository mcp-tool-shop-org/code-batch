"""Diff engine for batch comparison (Phase 6).

Pure set-math comparison engine for comparing outputs between batches.
All functions are read-only and deterministic.

Key design principles:
- Pure functions: no side effects, no state mutation
- Stable ordering: results sorted deterministically
- Normalized records: ignore timestamps and ephemeral fields
- Read-only: never writes to store
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Sequence
import json


@dataclass
class DiffResult:
    """Result of comparing two output sets."""

    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    changed: list[tuple[dict, dict]] = field(default_factory=list)  # (old, new) pairs

    @property
    def total_changes(self) -> int:
        """Total number of changes."""
        return len(self.added) + len(self.removed) + len(self.changed)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": [{"old": old, "new": new} for old, new in self.changed],
            "summary": {
                "added_count": len(self.added),
                "removed_count": len(self.removed),
                "changed_count": len(self.changed),
                "total_changes": self.total_changes,
            },
        }


def normalize_output(
    record: dict,
    *,
    ignore_fields: Optional[set[str]] = None,
) -> dict:
    """Normalize an output record for comparison.

    Removes ephemeral fields (timestamps, run IDs) that shouldn't
    affect comparison.

    Args:
        record: Output record to normalize.
        ignore_fields: Additional fields to ignore.

    Returns:
        Normalized record (copy, not mutated original).
    """
    # Default fields to ignore
    default_ignore = {"ts", "timestamp", "run_id", "shard_id"}
    if ignore_fields:
        default_ignore = default_ignore.union(ignore_fields)

    normalized = {}
    for key, value in record.items():
        if key not in default_ignore:
            normalized[key] = value

    return normalized


def make_output_key(record: dict, key_fields: Optional[list[str]] = None) -> tuple:
    """Create a hashable key for an output record.

    Args:
        record: Output record.
        key_fields: Fields to use for key (default: auto-detect by kind).

    Returns:
        Tuple key for set operations.
    """
    if key_fields:
        return tuple(record.get(f, "") for f in key_fields)

    # Auto-detect key fields by kind
    kind = record.get("kind", "")

    if kind == "diagnostic":
        # Diagnostics keyed by path, line, code
        return (
            kind,
            record.get("path", ""),
            record.get("line", 0),
            record.get("column", 0),
            record.get("code", ""),
        )
    elif kind == "metric":
        # Metrics keyed by path, name
        return (
            kind,
            record.get("path", ""),
            record.get("name", ""),
        )
    elif kind == "symbol":
        # Symbols keyed by path, name, line
        return (
            kind,
            record.get("path", ""),
            record.get("name", ""),
            record.get("line", 0),
        )
    elif kind == "ast":
        # AST keyed by path, object
        return (
            kind,
            record.get("path", ""),
            record.get("object", ""),
        )
    else:
        # Generic: use kind and path
        return (
            kind,
            record.get("path", ""),
        )


def diff_sets(
    set_a: Sequence[dict],
    set_b: Sequence[dict],
    *,
    key_fn: Optional[Callable[[dict], tuple]] = None,
    ignore_fields: Optional[set[str]] = None,
) -> DiffResult:
    """Compute difference between two output sets.

    Args:
        set_a: First set of outputs (before/baseline).
        set_b: Second set of outputs (after/current).
        key_fn: Function to extract key from record (default: make_output_key).
        ignore_fields: Fields to ignore when comparing.

    Returns:
        DiffResult with added, removed, and changed records.
    """
    if key_fn is None:
        key_fn = make_output_key

    # Build lookup maps
    map_a = {}  # key -> normalized record
    map_b = {}

    for record in set_a:
        normalized = normalize_output(record, ignore_fields=ignore_fields)
        key = key_fn(normalized)
        map_a[key] = normalized

    for record in set_b:
        normalized = normalize_output(record, ignore_fields=ignore_fields)
        key = key_fn(normalized)
        map_b[key] = normalized

    # Compute differences
    keys_a = set(map_a.keys())
    keys_b = set(map_b.keys())

    added_keys = keys_b - keys_a
    removed_keys = keys_a - keys_b
    common_keys = keys_a & keys_b

    # Build result
    result = DiffResult()

    # Added records (in B but not A)
    for key in sorted(added_keys):
        result.added.append(map_b[key])

    # Removed records (in A but not B)
    for key in sorted(removed_keys):
        result.removed.append(map_a[key])

    # Changed records (same key but different values)
    for key in sorted(common_keys):
        old = map_a[key]
        new = map_b[key]
        if old != new:
            result.changed.append((old, new))

    return result


def load_batch_outputs(
    store_root: Path,
    batch_id: str,
    *,
    kind_filter: Optional[str] = None,
    task_filter: Optional[str] = None,
) -> list[dict]:
    """Load all outputs from a batch.

    Read-only: does not modify the store.

    Args:
        store_root: Store root directory.
        batch_id: Batch ID to load.
        kind_filter: Filter by output kind (optional).
        task_filter: Filter by task ID (optional).

    Returns:
        List of output records with task_id added.
    """
    batch_dir = store_root / "batches" / batch_id
    plan_path = batch_dir / "plan.json"

    if not plan_path.exists():
        raise FileNotFoundError(f"Batch not found: {batch_id}")

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    outputs = []
    task_ids = [t["task_id"] for t in plan["tasks"]]

    if task_filter:
        task_ids = [t for t in task_ids if t == task_filter]

    for task_id in task_ids:
        shards_dir = batch_dir / "tasks" / task_id / "shards"
        if not shards_dir.exists():
            continue

        for shard_dir in sorted(shards_dir.iterdir()):
            if not shard_dir.is_dir():
                continue

            outputs_path = shard_dir / "outputs.index.jsonl"
            if not outputs_path.exists():
                continue

            with open(outputs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = json.loads(line)

                        # Apply kind filter
                        if kind_filter and record.get("kind") != kind_filter:
                            continue

                        record["task_id"] = task_id
                        outputs.append(record)

    return outputs


def diff_batches(
    store_root: Path,
    batch_a: str,
    batch_b: str,
    *,
    kind_filter: Optional[str] = None,
) -> DiffResult:
    """Compare outputs between two batches.

    Read-only: does not modify the store.

    Args:
        store_root: Store root directory.
        batch_a: First batch ID (before/baseline).
        batch_b: Second batch ID (after/current).
        kind_filter: Filter by output kind (optional).

    Returns:
        DiffResult with added, removed, and changed records.
    """
    outputs_a = load_batch_outputs(store_root, batch_a, kind_filter=kind_filter)
    outputs_b = load_batch_outputs(store_root, batch_b, kind_filter=kind_filter)

    return diff_sets(outputs_a, outputs_b)


# --- Diagnostic-specific comparison ---


_SEVERITY_ORDER = {
    "error": 0,
    "warning": 1,
    "info": 2,
    "hint": 3,
}


def severity_value(severity: str) -> int:
    """Get numeric value for severity (lower = more severe)."""
    return _SEVERITY_ORDER.get(severity.lower(), 99)


def is_regression(old: Optional[dict], new: dict) -> bool:
    """Check if a diagnostic change is a regression.

    Regression = new diagnostic or severity increased.

    Args:
        old: Old diagnostic (None if new).
        new: New diagnostic.

    Returns:
        True if this is a regression.
    """
    if old is None:
        # New diagnostic = regression
        return True

    old_sev = severity_value(old.get("severity", ""))
    new_sev = severity_value(new.get("severity", ""))

    # Lower severity value = more severe
    return new_sev < old_sev


def is_improvement(old: dict, new: Optional[dict]) -> bool:
    """Check if a diagnostic change is an improvement.

    Improvement = diagnostic removed or severity decreased.

    Args:
        old: Old diagnostic.
        new: New diagnostic (None if removed).

    Returns:
        True if this is an improvement.
    """
    if new is None:
        # Removed diagnostic = improvement
        return True

    old_sev = severity_value(old.get("severity", ""))
    new_sev = severity_value(new.get("severity", ""))

    # Higher severity value = less severe
    return new_sev > old_sev


@dataclass
class DiagnosticDelta:
    """Result of comparing diagnostics between batches."""

    regressions: list[dict] = field(default_factory=list)
    improvements: list[dict] = field(default_factory=list)
    unchanged: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "regressions": self.regressions,
            "improvements": self.improvements,
            "unchanged": self.unchanged,
            "summary": {
                "regressions_count": len(self.regressions),
                "improvements_count": len(self.improvements),
                "unchanged_count": len(self.unchanged),
            },
        }


def diff_diagnostics(
    store_root: Path,
    batch_a: str,
    batch_b: str,
) -> DiagnosticDelta:
    """Compare diagnostics between two batches.

    Classifies changes as regressions, improvements, or unchanged.

    Args:
        store_root: Store root directory.
        batch_a: First batch ID (before/baseline).
        batch_b: Second batch ID (after/current).

    Returns:
        DiagnosticDelta with classified changes.
    """
    diff = diff_batches(store_root, batch_a, batch_b, kind_filter="diagnostic")
    result = DiagnosticDelta()

    # Added diagnostics are regressions
    for record in diff.added:
        result.regressions.append(record)

    # Removed diagnostics are improvements
    for record in diff.removed:
        result.improvements.append(record)

    # Changed diagnostics: check severity
    for old, new in diff.changed:
        if is_regression(old, new):
            result.regressions.append(new)
        elif is_improvement(old, new):
            result.improvements.append(old)  # Report old (what was improved)
        else:
            result.unchanged.append(new)

    # Sort results for determinism
    result.regressions.sort(key=lambda x: (x.get("path", ""), x.get("line", 0)))
    result.improvements.sort(key=lambda x: (x.get("path", ""), x.get("line", 0)))
    result.unchanged.sort(key=lambda x: (x.get("path", ""), x.get("line", 0)))

    return result
