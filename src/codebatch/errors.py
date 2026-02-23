"""Centralized error handling for CodeBatch CLI.

This module provides:
- Standard error codes
- Error envelope format for --json output
- Helper functions for consistent error reporting

Phase 7: Integration API
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Error Codes
# =============================================================================

# Store errors
STORE_NOT_FOUND = "STORE_NOT_FOUND"
STORE_INVALID = "STORE_INVALID"
STORE_EXISTS = "STORE_EXISTS"

# Batch errors
BATCH_NOT_FOUND = "BATCH_NOT_FOUND"
BATCH_INVALID = "BATCH_INVALID"

# Snapshot errors
SNAPSHOT_NOT_FOUND = "SNAPSHOT_NOT_FOUND"
SNAPSHOT_INVALID = "SNAPSHOT_INVALID"

# Pipeline errors
PIPELINE_NOT_FOUND = "PIPELINE_NOT_FOUND"

# Task errors
TASK_NOT_FOUND = "TASK_NOT_FOUND"
SHARD_NOT_FOUND = "SHARD_NOT_FOUND"

# Gate errors
GATE_NOT_FOUND = "GATE_NOT_FOUND"

# Input errors
INVALID_ARGUMENT = "INVALID_ARGUMENT"
SCHEMA_ERROR = "SCHEMA_ERROR"
FILE_NOT_FOUND = "FILE_NOT_FOUND"

# Generic errors
COMMAND_ERROR = "COMMAND_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"


# =============================================================================
# Error Envelope
# =============================================================================


@dataclass
class CodeBatchError:
    """Structured error for JSON output.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable error message.
        hints: Actionable suggestions for resolving the error.
        details: Context-specific error details.
    """

    code: str
    message: str
    hints: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to error envelope dict."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "hints": self.hints,
                "details": self.details,
            }
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def print_json(self, file=None) -> None:
        """Print error as JSON to file (default: stderr)."""
        if file is None:
            file = sys.stderr
        print(self.to_json(), file=file)

    def print_text(self, file=None) -> None:
        """Print error as human-readable text to file (default: stderr)."""
        if file is None:
            file = sys.stderr
        print(f"Error: {self.message}", file=file)
        if self.hints:
            for hint in self.hints:
                print(f"  Hint: {hint}", file=file)


# =============================================================================
# Factory Functions
# =============================================================================


def store_not_found(path: str) -> CodeBatchError:
    """Create error for missing store."""
    return CodeBatchError(
        code=STORE_NOT_FOUND,
        message=f"Store does not exist: {path}",
        hints=[
            f"Run: codebatch init {path}",
            "Check that the path is correct",
        ],
        details={"path": path},
    )


def store_invalid(path: str, reason: str = "") -> CodeBatchError:
    """Create error for invalid store."""
    msg = f"Invalid store: {path}"
    if reason:
        msg += f" ({reason})"
    return CodeBatchError(
        code=STORE_INVALID,
        message=msg,
        hints=[
            "Ensure the store was initialized with 'codebatch init'",
            "Check store.json exists and is valid",
        ],
        details={"path": path, "reason": reason},
    )


def store_exists(path: str) -> CodeBatchError:
    """Create error for existing store when initializing."""
    return CodeBatchError(
        code=STORE_EXISTS,
        message=f"Store already exists: {path}",
        hints=[
            "Use a different path",
            "Remove existing store if you want to reinitialize",
        ],
        details={"path": path},
    )


def batch_not_found(batch_id: str, store: Optional[str] = None) -> CodeBatchError:
    """Create error for missing batch."""
    hints = ["Run: codebatch batch-list --store <path>"]
    if store:
        hints[0] = f"Run: codebatch batch-list --store {store}"
    return CodeBatchError(
        code=BATCH_NOT_FOUND,
        message=f"Batch not found: {batch_id}",
        hints=hints,
        details={"batch_id": batch_id, "store": store}
        if store
        else {"batch_id": batch_id},
    )


def snapshot_not_found(snapshot_id: str, store: Optional[str] = None) -> CodeBatchError:
    """Create error for missing snapshot."""
    hints = ["Run: codebatch snapshot-list --store <path>"]
    if store:
        hints[0] = f"Run: codebatch snapshot-list --store {store}"
    return CodeBatchError(
        code=SNAPSHOT_NOT_FOUND,
        message=f"Snapshot not found: {snapshot_id}",
        hints=hints,
        details={"snapshot_id": snapshot_id, "store": store}
        if store
        else {"snapshot_id": snapshot_id},
    )


def pipeline_not_found(pipeline_name: str) -> CodeBatchError:
    """Create error for missing pipeline."""
    return CodeBatchError(
        code=PIPELINE_NOT_FOUND,
        message=f"Pipeline not found: {pipeline_name}",
        hints=[
            "Run: codebatch pipelines --json",
            "Check the pipeline name spelling",
        ],
        details={"pipeline": pipeline_name},
    )


def task_not_found(task_id: str) -> CodeBatchError:
    """Create error for missing task."""
    return CodeBatchError(
        code=TASK_NOT_FOUND,
        message=f"Task not found: {task_id}",
        hints=[
            "Run: codebatch tasks --batch <batch_id> --store <path>",
        ],
        details={"task_id": task_id},
    )


def gate_not_found(gate_id: str) -> CodeBatchError:
    """Create error for missing gate."""
    return CodeBatchError(
        code=GATE_NOT_FOUND,
        message=f"Gate not found: {gate_id}",
        hints=[
            "Run: codebatch gate-list",
            "Check the gate ID spelling",
        ],
        details={"gate_id": gate_id},
    )


def invalid_argument(arg_name: str, value: str, reason: str = "") -> CodeBatchError:
    """Create error for invalid argument."""
    msg = f"Invalid argument '{arg_name}': {value}"
    if reason:
        msg += f" ({reason})"
    return CodeBatchError(
        code=INVALID_ARGUMENT,
        message=msg,
        hints=[
            "Check the argument value",
            "Run: codebatch <command> --help",
        ],
        details={"argument": arg_name, "value": value, "reason": reason},
    )


def file_not_found(path: str) -> CodeBatchError:
    """Create error for missing file."""
    return CodeBatchError(
        code=FILE_NOT_FOUND,
        message=f"File not found: {path}",
        hints=["Check that the file path is correct"],
        details={"path": path},
    )


def command_error(message: str, details: Optional[dict] = None) -> CodeBatchError:
    """Create generic command error."""
    return CodeBatchError(
        code=COMMAND_ERROR,
        message=message,
        hints=[],
        details=details or {},
    )


def internal_error(message: str, details: Optional[dict] = None) -> CodeBatchError:
    """Create internal error."""
    return CodeBatchError(
        code=INTERNAL_ERROR,
        message=f"Internal error: {message}",
        hints=["Please report this issue"],
        details=details or {},
    )


# =============================================================================
# Output Helper
# =============================================================================


def print_error(
    error: CodeBatchError,
    json_mode: bool = False,
    file=None,
) -> None:
    """Print error in appropriate format.

    Args:
        error: The error to print.
        json_mode: If True, print as JSON envelope. If False, print as text.
        file: Output file (default: stderr).
    """
    if json_mode:
        error.print_json(file)
    else:
        error.print_text(file)
