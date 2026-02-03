"""Path canonicalization and safety utilities.

All file paths in a snapshot are canonicalized:
- UTF-8 encoded
- / as separator
- No . or .. segments
- No trailing slash
- Stable casing preserved

A path_key is included for normalized comparison (lowercase).
"""

import os
import re
from pathlib import Path, PurePosixPath
from typing import Tuple


class PathEscapeError(Exception):
    """Raised when a path attempts to escape the root directory."""

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Path escape attempt: {path} - {reason}")


class InvalidPathError(Exception):
    """Raised for invalid path characters or structure."""

    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid path: {path} - {reason}")


# Characters not allowed in paths (Windows restrictions + control chars)
INVALID_CHARS = re.compile(r'[\x00-\x1f<>:"|?*]')

# Reserved Windows filenames
RESERVED_NAMES = frozenset([
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
])


def canonicalize_path(path: str, root: Path = None) -> str:
    """Canonicalize a file path for storage.

    Args:
        path: Input path (may use any separator).
        root: Optional root directory for escape detection.

    Returns:
        Canonicalized path with / separators, no . or .. segments.

    Raises:
        PathEscapeError: If path escapes the root.
        InvalidPathError: If path contains invalid characters.
    """
    if not path:
        raise InvalidPathError(path, "empty path")

    # Check for invalid characters
    if INVALID_CHARS.search(path):
        raise InvalidPathError(path, "contains invalid characters")

    # Normalize separators to forward slash
    normalized = path.replace("\\", "/")

    # Remove leading/trailing whitespace
    normalized = normalized.strip()

    # Remove trailing slash
    normalized = normalized.rstrip("/")

    if not normalized:
        raise InvalidPathError(path, "path is empty after normalization")

    # Split into components and resolve . and ..
    parts = normalized.split("/")
    resolved = []

    for part in parts:
        if not part or part == ".":
            # Skip empty parts and current directory
            continue
        elif part == "..":
            # Parent directory - check for escape
            if not resolved:
                raise PathEscapeError(path, "attempts to go above root")
            resolved.pop()
        else:
            # Check for reserved Windows names
            base_name = part.split(".")[0].upper()
            if base_name in RESERVED_NAMES:
                raise InvalidPathError(path, f"contains reserved name: {part}")
            resolved.append(part)

    if not resolved:
        raise InvalidPathError(path, "path resolves to root")

    canonical = "/".join(resolved)

    # If root provided, verify the resolved path doesn't escape
    if root is not None:
        try:
            full_path = (root / canonical).resolve()
            root_resolved = root.resolve()
            # Check that full_path is under root
            try:
                full_path.relative_to(root_resolved)
            except ValueError:
                raise PathEscapeError(path, "resolved path escapes root")
        except OSError:
            # Path resolution failed - might be too long or invalid
            pass

    return canonical


def compute_path_key(path: str) -> str:
    """Compute a normalized path key for comparison.

    The path_key is lowercase with normalized separators,
    used for case-insensitive comparisons and collision detection.

    Args:
        path: Canonicalized path.

    Returns:
        Lowercase path key.
    """
    # Path should already be canonicalized (/ separators, no . or ..)
    return path.lower()


def canonicalize_with_key(path: str, root: Path = None) -> Tuple[str, str]:
    """Canonicalize a path and compute its key in one call.

    Args:
        path: Input path.
        root: Optional root directory for escape detection.

    Returns:
        Tuple of (canonical_path, path_key).
    """
    canonical = canonicalize_path(path, root)
    key = compute_path_key(canonical)
    return canonical, key


def is_safe_path(path: str, root: Path = None) -> bool:
    """Check if a path is safe (doesn't escape root, valid characters).

    Args:
        path: Path to check.
        root: Optional root directory.

    Returns:
        True if path is safe, False otherwise.
    """
    try:
        canonicalize_path(path, root)
        return True
    except (PathEscapeError, InvalidPathError):
        return False


def detect_case_collision(paths: list[str]) -> list[Tuple[str, str]]:
    """Detect case collisions in a list of paths.

    Args:
        paths: List of canonicalized paths.

    Returns:
        List of colliding path pairs.
    """
    key_to_paths: dict[str, list[str]] = {}

    for path in paths:
        key = compute_path_key(path)
        if key not in key_to_paths:
            key_to_paths[key] = []
        key_to_paths[key].append(path)

    collisions = []
    for key, path_list in key_to_paths.items():
        if len(path_list) > 1:
            # Return all pairs
            for i, p1 in enumerate(path_list):
                for p2 in path_list[i + 1:]:
                    collisions.append((p1, p2))

    return collisions
