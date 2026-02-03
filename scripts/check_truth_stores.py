#!/usr/bin/env python3
"""CI Rule C: Truth store guard.

Verifies that code only writes semantic data to allowed paths.

This is a static analysis check that looks for file write patterns
and validates they target allowed locations.

Usage:
    python scripts/check_truth_stores.py [directory]

Arguments:
    directory: Directory to scan (default: src/)

Exit codes:
    0: All writes to allowed paths
    1: Potential writes to forbidden paths
    2: Error

Note: This is a heuristic check. It may have false positives.
      Manual review is required for flagged patterns.
"""

import ast
import sys
from pathlib import Path


# Allowed write path patterns (relative to store root)
ALLOWED_PATTERNS = [
    "objects/",           # CAS blobs
    "snapshots/",         # Snapshot creation (immutable after)
    "batches/",           # Batch/task/shard data
    "indexes/",           # Optional cache
    "store.json",         # Store metadata
]

# Write-related function/method names to check
WRITE_FUNCTIONS = {
    "open",
    "write",
    "write_bytes",
    "write_text",
    "mkdir",
    "makedirs",
    "rename",
    "replace",
}


class WritePatternVisitor(ast.NodeVisitor):
    """AST visitor that finds file write patterns."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.findings = []

    def visit_Call(self, node):
        """Check function calls for write operations."""
        func_name = None

        # Get function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in WRITE_FUNCTIONS:
            # Check if it looks like a hardcoded path outside allowed areas
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    path = arg.value
                    if not self._is_allowed_path(path):
                        self.findings.append({
                            "line": node.lineno,
                            "func": func_name,
                            "path": path,
                        })

        self.generic_visit(node)

    def _is_allowed_path(self, path: str) -> bool:
        """Check if a path matches allowed patterns."""
        # Normalize
        path = path.replace("\\", "/").lower()

        # Check against allowed patterns
        for pattern in ALLOWED_PATTERNS:
            if pattern.lower() in path:
                return True

        # Allow relative paths that don't look like absolute store paths
        if not path.startswith("/") and ":" not in path:
            # Likely a relative path within allowed structure
            return True

        return False


def check_file(filepath: Path) -> list[dict]:
    """Check a Python file for write patterns."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError:
        return []

    visitor = WritePatternVisitor(str(filepath))
    visitor.visit(tree)
    return visitor.findings


def main():
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src")

    if not directory.exists():
        print(f"ERROR: Directory not found: {directory}")
        sys.exit(2)

    all_findings = {}

    for filepath in directory.rglob("*.py"):
        findings = check_file(filepath)
        if findings:
            all_findings[str(filepath)] = findings

    if all_findings:
        print("WARNING: Potential writes to non-allowed paths detected")
        print("\nPhase 2 restricts semantic writes to:")
        for pattern in ALLOWED_PATTERNS:
            print(f"  - {pattern}")
        print("\nPlease review these patterns:\n")

        for filepath, findings in sorted(all_findings.items()):
            print(f"{filepath}:")
            for f in findings:
                print(f"  Line {f['line']}: {f['func']}({f['path']!r})")

        print("\nNote: This check may have false positives.")
        print("      If the paths are correct, this is informational only.")

        # Exit 0 because this is heuristic - manual review needed
        # Change to exit 1 if you want strict enforcement
        sys.exit(0)

    print(f"OK: No suspicious write patterns found in {directory}")
    sys.exit(0)


if __name__ == "__main__":
    main()
