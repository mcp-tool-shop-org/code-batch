"""Simple output paging for CodeBatch UI.

Provides basic paging without background refresh or complex state.
Designed for non-TTY safety and deterministic output.

Key design principles:
- No background threads or refresh
- No curses or complex terminal manipulation
- Works with redirected output
- Optional integration with system pager (less)
"""

import os
import shutil
import subprocess
import sys
from typing import Optional


def should_paginate(
    line_count: int,
    *,
    threshold: Optional[int] = None,
    force: Optional[bool] = None,
) -> bool:
    """Determine if output should be paginated.

    Args:
        line_count: Number of lines in output.
        threshold: Line threshold for pagination (default: terminal height - 5).
        force: Force pagination on/off (overrides auto-detection).

    Returns:
        True if output should be paginated.
    """
    # Explicit override
    if force is not None:
        return force

    # Don't paginate if not a TTY
    if not sys.stdout.isatty():
        return False

    # Get terminal height
    try:
        term_size = shutil.get_terminal_size()
        term_height = term_size.lines
    except (ValueError, OSError):
        term_height = 24  # Default fallback

    # Use provided threshold or calculate from terminal
    if threshold is None:
        threshold = term_height - 5  # Leave room for prompt

    return line_count > threshold


def paginate(
    content: str,
    *,
    pager_cmd: Optional[str] = None,
    fallback_print: bool = True,
) -> None:
    """Display content through a pager.

    Args:
        content: Text content to paginate.
        pager_cmd: Pager command (default: PAGER env var or 'less -FRSX').
        fallback_print: Print directly if pager fails.

    The default pager flags for less:
        -F: Quit if content fits on one screen
        -R: Pass through ANSI color codes
        -S: Chop long lines (don't wrap)
        -X: Don't clear screen on exit
    """
    # Don't paginate if not a TTY
    if not sys.stdout.isatty():
        print(content)
        return

    # Determine pager command
    if pager_cmd is None:
        pager_cmd = os.environ.get("PAGER", "")
        if not pager_cmd:
            # Default to less with sensible flags
            pager_cmd = "less -FRSX"

    try:
        # Split command for subprocess
        cmd_parts = pager_cmd.split()

        # Run pager
        proc = subprocess.Popen(
            cmd_parts,
            stdin=subprocess.PIPE,
            text=True,
        )
        proc.communicate(input=content)

    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        # Pager not available, fall back to print
        if fallback_print:
            print(content)


def paginate_lines(
    lines: list[str],
    *,
    page: int = 0,
    page_size: int = 50,
) -> tuple[list[str], bool]:
    """Get a page of lines.

    Args:
        lines: All lines.
        page: Page number (0-indexed).
        page_size: Lines per page.

    Returns:
        Tuple of (page_lines, has_more).
    """
    start = page * page_size
    end = start + page_size

    page_lines = lines[start:end]
    has_more = end < len(lines)

    return page_lines, has_more


def format_pagination_info(
    page: int,
    page_size: int,
    total: int,
) -> str:
    """Format pagination information string.

    Args:
        page: Current page (0-indexed).
        page_size: Lines per page.
        total: Total line count.

    Returns:
        String like "Showing 1-50 of 123".
    """
    start = page * page_size + 1
    end = min((page + 1) * page_size, total)

    if total <= page_size:
        return f"{total} items"
    else:
        return f"Showing {start}-{end} of {total}"
