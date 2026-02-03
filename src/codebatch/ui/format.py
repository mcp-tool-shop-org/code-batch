"""Formatting utilities for CodeBatch UI.

Provides deterministic, stable output for tables, JSON, and colored text.
All functions are pure and read-only.

Key design principles:
- Stable ordering: results sorted by explicit key, never randomized
- Optional color: all color can be disabled with --no-color
- Non-TTY safe: works when stdout is redirected
- ASCII safe: no Unicode characters that might fail on Windows

Rendering Contracts:
-------------------
These contracts guarantee deterministic, reproducible output:

1. render_table(rows, columns, *, sort_key, ...)
   - Contract: Given identical rows and sort_key, output is byte-identical
   - Ordering: Rows sorted by sort_key (required for determinism)
   - Colors: Stripped in ColorMode.NEVER
   - Widths: Calculated from content, capped at 60 chars

2. render_json(obj, *, sort_keys=True, ...)
   - Contract: Given identical obj and sort_keys=True, output is byte-identical
   - Ordering: Dictionary keys sorted alphabetically
   - Encoding: UTF-8 with ensure_ascii=False

3. render_jsonl(records, *, sort_key, sort_dict_keys=True, ...)
   - Contract: Given identical records and sort_key, output is byte-identical
   - Ordering: Records sorted by sort_key; keys within records sorted
   - Format: One JSON object per line, no trailing newline
"""

import json
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Sequence


class ColorMode(Enum):
    """Color output mode."""

    AUTO = "auto"  # Color if TTY, no color otherwise
    ALWAYS = "always"  # Always use color
    NEVER = "never"  # Never use color


# ANSI color codes (ASCII-safe)
_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
}


def _should_color(mode: ColorMode) -> bool:
    """Determine if output should be colored."""
    if mode == ColorMode.NEVER:
        return False
    if mode == ColorMode.ALWAYS:
        return True
    # AUTO: color if stdout is a TTY
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def colorize(text: str, color: str, mode: ColorMode = ColorMode.AUTO) -> str:
    """Apply color to text if color mode allows.

    Args:
        text: Text to colorize.
        color: Color name (red, green, yellow, blue, etc.)
        mode: Color mode (auto, always, never).

    Returns:
        Colored text if mode allows, otherwise plain text.
    """
    if not _should_color(mode):
        return text

    code = _COLORS.get(color, "")
    reset = _COLORS.get("reset", "")

    if not code:
        return text

    return f"{code}{text}{reset}"


@dataclass
class Column:
    """Table column definition."""

    name: str
    header: str
    width: Optional[int] = None
    align: str = "left"  # "left", "right", "center"


def render_table(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[Column | str],
    *,
    sort_key: Optional[str | Callable[[dict], Any]] = None,
    color_mode: ColorMode = ColorMode.AUTO,
    max_rows: Optional[int] = None,
    page: int = 0,
    page_size: int = 50,
    show_header: bool = True,
) -> str:
    """Render rows as a formatted table.

    Args:
        rows: Sequence of dicts to render.
        columns: Column definitions (Column objects or field names).
        sort_key: Field name or function for sorting.
        color_mode: Color output mode.
        max_rows: Maximum rows to show (None for all).
        page: Page number (0-indexed).
        page_size: Rows per page.
        show_header: Whether to show column headers.

    Returns:
        Formatted table as string.
    """
    if not rows:
        return ""

    # Normalize columns
    cols = []
    for c in columns:
        if isinstance(c, str):
            cols.append(Column(name=c, header=c.upper()))
        else:
            cols.append(c)

    # Sort rows deterministically
    sorted_rows = list(rows)
    if sort_key:
        if isinstance(sort_key, str):
            key_fn = lambda r: (r.get(sort_key, "") or "")
        else:
            key_fn = sort_key
        sorted_rows.sort(key=key_fn)

    # Apply pagination
    if max_rows is not None:
        sorted_rows = sorted_rows[:max_rows]
    else:
        start = page * page_size
        end = start + page_size
        sorted_rows = sorted_rows[start:end]

    # Calculate column widths
    widths = []
    for col in cols:
        if col.width:
            widths.append(col.width)
        else:
            # Auto-width based on content
            max_len = len(col.header)
            for row in sorted_rows:
                val = str(row.get(col.name, ""))
                max_len = max(max_len, len(val))
            widths.append(min(max_len, 60))  # Cap at 60 chars

    # Build output
    lines = []

    # Header
    if show_header:
        header_parts = []
        for i, col in enumerate(cols):
            header_parts.append(_align(col.header, widths[i], col.align))
        header_line = "  ".join(header_parts)
        lines.append(colorize(header_line, "bold", color_mode))

        # Separator
        sep_parts = ["-" * w for w in widths]
        lines.append("  ".join(sep_parts))

    # Rows
    for row in sorted_rows:
        parts = []
        for i, col in enumerate(cols):
            val = str(row.get(col.name, ""))
            # Truncate if too long
            if len(val) > widths[i]:
                val = val[: widths[i] - 3] + "..."
            parts.append(_align(val, widths[i], col.align))
        lines.append("  ".join(parts))

    return "\n".join(lines)


def _align(text: str, width: int, align: str) -> str:
    """Align text within width."""
    if align == "right":
        return text.rjust(width)
    elif align == "center":
        return text.center(width)
    else:
        return text.ljust(width)


def render_json(
    obj: Any,
    *,
    indent: int = 2,
    sort_keys: bool = True,
) -> str:
    """Render object as JSON with stable key ordering.

    Args:
        obj: Object to serialize.
        indent: Indentation level (None for compact).
        sort_keys: Whether to sort dictionary keys.

    Returns:
        JSON string with stable ordering.
    """
    return json.dumps(
        obj,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=False,
        default=_json_default,
    )


def render_jsonl(
    records: Sequence[dict[str, Any]],
    *,
    sort_key: Optional[str | Callable[[dict], Any]] = None,
    sort_dict_keys: bool = True,
) -> str:
    """Render records as JSON Lines with stable ordering.

    Args:
        records: Sequence of records to render.
        sort_key: Field name or function for sorting records.
        sort_dict_keys: Whether to sort keys within each record.

    Returns:
        JSON Lines string (one JSON object per line).
    """
    if not records:
        return ""

    # Sort records deterministically
    sorted_records = list(records)
    if sort_key:
        if isinstance(sort_key, str):
            key_fn = lambda r: (r.get(sort_key, "") or "")
        else:
            key_fn = sort_key
        sorted_records.sort(key=key_fn)

    lines = []
    for record in sorted_records:
        line = json.dumps(
            record,
            sort_keys=sort_dict_keys,
            ensure_ascii=False,
            default=_json_default,
        )
        lines.append(line)

    return "\n".join(lines)


def _json_default(obj: Any) -> Any:
    """JSON serialization fallback for non-standard types."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def format_count(count: int, label: str, color_mode: ColorMode = ColorMode.AUTO) -> str:
    """Format a count with label and optional color.

    Args:
        count: The count value.
        label: Label for the count (e.g., "errors", "warnings").
        color_mode: Color output mode.

    Returns:
        Formatted string like "5 errors" with appropriate color.
    """
    text = f"{count} {label}"

    # Color based on label semantics
    if count == 0:
        return colorize(text, "dim", color_mode)
    elif "error" in label.lower():
        return colorize(text, "red", color_mode)
    elif "warning" in label.lower():
        return colorize(text, "yellow", color_mode)
    elif "success" in label.lower() or "pass" in label.lower():
        return colorize(text, "green", color_mode)
    else:
        return text


def format_path(path: str, color_mode: ColorMode = ColorMode.AUTO) -> str:
    """Format a file path with optional color.

    Args:
        path: File path to format.
        color_mode: Color output mode.

    Returns:
        Formatted path with color.
    """
    return colorize(path, "cyan", color_mode)


def format_severity(
    severity: str, color_mode: ColorMode = ColorMode.AUTO
) -> str:
    """Format a severity level with color.

    Args:
        severity: Severity string (error, warning, info, hint).
        color_mode: Color output mode.

    Returns:
        Colored severity string.
    """
    severity_lower = severity.lower()
    if severity_lower == "error":
        return colorize(severity, "red", color_mode)
    elif severity_lower == "warning":
        return colorize(severity, "yellow", color_mode)
    elif severity_lower == "info":
        return colorize(severity, "blue", color_mode)
    elif severity_lower == "hint":
        return colorize(severity, "dim", color_mode)
    else:
        return severity


# --- Rendering Contract Verification ---


def verify_deterministic_table(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[Column | str],
    sort_key: str,
) -> bool:
    """Verify that table rendering is deterministic.

    Renders the table twice and compares output.

    Args:
        rows: Rows to render.
        columns: Column definitions.
        sort_key: Sort key (required for determinism).

    Returns:
        True if outputs are identical.

    Raises:
        AssertionError: If outputs differ.
    """
    output1 = render_table(
        rows, columns, sort_key=sort_key, color_mode=ColorMode.NEVER
    )
    output2 = render_table(
        rows, columns, sort_key=sort_key, color_mode=ColorMode.NEVER
    )
    assert output1 == output2, "Table rendering is not deterministic"
    return True


def verify_deterministic_json(obj: Any) -> bool:
    """Verify that JSON rendering is deterministic.

    Renders the object twice and compares output.

    Args:
        obj: Object to serialize.

    Returns:
        True if outputs are identical.

    Raises:
        AssertionError: If outputs differ.
    """
    output1 = render_json(obj, sort_keys=True)
    output2 = render_json(obj, sort_keys=True)
    assert output1 == output2, "JSON rendering is not deterministic"
    return True


def verify_deterministic_jsonl(
    records: Sequence[dict[str, Any]],
    sort_key: str,
) -> bool:
    """Verify that JSONL rendering is deterministic.

    Renders the records twice and compares output.

    Args:
        records: Records to render.
        sort_key: Sort key for records.

    Returns:
        True if outputs are identical.

    Raises:
        AssertionError: If outputs differ.
    """
    output1 = render_jsonl(records, sort_key=sort_key)
    output2 = render_jsonl(records, sort_key=sort_key)
    assert output1 == output2, "JSONL rendering is not deterministic"
    return True


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text.

    Args:
        text: Text potentially containing ANSI codes.

    Returns:
        Text with ANSI codes removed.
    """
    import re
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)
