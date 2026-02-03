"""Lint task executor - rule-based diagnostics.

Emits:
- kind=diagnostic: Lint warnings/errors with severity, code, message, location

Inputs:
- Parse outputs (kind=ast) via iter_prior_outputs (preferred)
- Falls back to raw file content for simple text rules

Rules (Phase 2 minimal set):
- L001: Trailing whitespace
- L002: Line too long (>120 chars)
- L003: TODO/FIXME presence
- L004: Tab indentation (prefer spaces)
- L005: Missing newline at end of file
"""

import json
from typing import Iterable, Optional

from ..runner import ShardRunner


# Rule configuration
DEFAULT_MAX_LINE_LENGTH = 120
TODO_PATTERNS = ["TODO", "FIXME", "XXX", "HACK"]


def lint_trailing_whitespace(lines: list[str], path: str) -> list[dict]:
    """L001: Detect trailing whitespace."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        # Don't strip newline, just check for trailing spaces/tabs before it
        stripped = line.rstrip('\n\r')
        if stripped != stripped.rstrip():
            diagnostics.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "L001",
                "message": "Trailing whitespace",
                "line": i,
                "col": len(stripped.rstrip()) + 1,
            })
    return diagnostics


def lint_line_too_long(lines: list[str], path: str, max_length: int = DEFAULT_MAX_LINE_LENGTH) -> list[dict]:
    """L002: Detect lines exceeding max length."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip('\n\r')
        if len(stripped) > max_length:
            diagnostics.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "L002",
                "message": f"Line too long ({len(stripped)} > {max_length})",
                "line": i,
                "col": max_length + 1,
            })
    return diagnostics


def lint_todo_fixme(lines: list[str], path: str) -> list[dict]:
    """L003: Detect TODO/FIXME/XXX/HACK comments."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        upper_line = line.upper()
        for pattern in TODO_PATTERNS:
            if pattern in upper_line:
                col = line.upper().find(pattern) + 1
                diagnostics.append({
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "info",
                    "code": "L003",
                    "message": f"Found {pattern} comment",
                    "line": i,
                    "col": col,
                })
                break  # Only report once per line
    return diagnostics


def lint_tab_indentation(lines: list[str], path: str) -> list[dict]:
    """L004: Detect tab indentation (prefer spaces)."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        if line.startswith('\t'):
            diagnostics.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "L004",
                "message": "Tab indentation (prefer spaces)",
                "line": i,
                "col": 1,
            })
    return diagnostics


def lint_missing_final_newline(content: str, path: str) -> list[dict]:
    """L005: Detect missing newline at end of file."""
    diagnostics = []
    if content and not content.endswith('\n'):
        lines = content.split('\n')
        diagnostics.append({
            "kind": "diagnostic",
            "path": path,
            "severity": "warning",
            "code": "L005",
            "message": "Missing newline at end of file",
            "line": len(lines),
            "col": len(lines[-1]) + 1 if lines else 1,
        })
    return diagnostics


def lint_content(content: str, path: str, config: dict) -> list[dict]:
    """Run all lint rules on content.

    Args:
        content: File content as string.
        path: File path.
        config: Lint configuration.

    Returns:
        List of diagnostic records.
    """
    diagnostics = []
    lines = content.split('\n')

    # Get config options
    max_line_length = config.get("max_line_length", DEFAULT_MAX_LINE_LENGTH)
    check_trailing = config.get("check_trailing_whitespace", True)
    check_line_length = config.get("check_line_length", True)
    check_todo = config.get("check_todo", True)
    check_tabs = config.get("check_tab_indentation", True)
    check_final_newline = config.get("check_final_newline", True)

    if check_trailing:
        diagnostics.extend(lint_trailing_whitespace(lines, path))

    if check_line_length:
        diagnostics.extend(lint_line_too_long(lines, path, max_line_length))

    if check_todo:
        diagnostics.extend(lint_todo_fixme(lines, path))

    if check_tabs:
        diagnostics.extend(lint_tab_indentation(lines, path))

    if check_final_newline:
        diagnostics.extend(lint_missing_final_newline(content, path))

    return diagnostics


def lint_executor(config: dict, files: Iterable[dict], runner: ShardRunner) -> list[dict]:
    """Execute the lint task.

    Runs lint rules on files in the shard. Prefers AST-based linting but
    falls back to text-based rules for all files.

    Args:
        config: Task configuration.
        files: Iterable of file records for this shard.
        runner: ShardRunner for CAS access.

    Returns:
        List of diagnostic output records.
    """
    outputs = []

    # Get execution context
    batch_id = config.get("_batch_id")
    shard_id = config.get("_shard_id")

    # Track which files we've linted (to avoid duplicates)
    linted_paths = set()

    # First pass: lint files that have AST (from parse task)
    if batch_id and shard_id:
        for ast_output in runner.iter_prior_outputs(batch_id, "01_parse", shard_id, kind="ast"):
            path = ast_output.get("path")
            object_ref = ast_output.get("object")

            if not path or not object_ref or path in linted_paths:
                continue

            # Skip chunked ASTs
            if ast_output.get("format") == "json+chunks":
                continue

            try:
                # Load AST to check for any parse-related issues
                # (Future: could add AST-based lint rules here)

                # For now, get the original file content and run text rules
                # We need to find the file's object ref from snapshot
                pass

            except Exception:
                pass

    # Second pass: lint all files in shard by reading from CAS
    file_list = list(files)
    for file_record in file_list:
        path = file_record["path"]
        object_ref = file_record["object"]

        if path in linted_paths:
            continue

        try:
            # Get file content from CAS
            data = runner.object_store.get_bytes(object_ref)

            # Try to decode as text
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                # Binary file - skip
                continue

            # Run lint rules
            diagnostics = lint_content(content, path, config)
            outputs.extend(diagnostics)
            linted_paths.add(path)

        except Exception as e:
            outputs.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "error",
                "code": "L999",
                "message": f"Lint error: {e}",
                "line": 1,
                "col": 1,
            })

    return outputs
