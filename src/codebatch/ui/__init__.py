"""UI module for CodeBatch Phase 6.

This module provides read-only views and formatting for CodeBatch outputs.
It is designed to be isolated from core modules and can be removed without
breaking Phases 1-5 functionality.

Submodules:
- format: Table rendering, JSON output, color handling
- pager: Simple output paging (no background refresh)
- diff: Pure set-math comparison engine

All UI functions are read-only and never write to the store.

Usage:
    from codebatch.ui import render_table, render_json
    from codebatch.ui.format import render_table
    from codebatch.ui.diff import diff_sets
"""

from .format import (
    render_table,
    render_json,
    render_jsonl,
    ColorMode,
    Column,
    colorize,
    format_count,
    format_path,
    format_severity,
    strip_ansi,
    verify_deterministic_table,
    verify_deterministic_json,
    verify_deterministic_jsonl,
)
from .pager import (
    paginate,
    should_paginate,
    paginate_lines,
    format_pagination_info,
)

__all__ = [
    # Format - core rendering
    "render_table",
    "render_json",
    "render_jsonl",
    "ColorMode",
    "Column",
    # Format - helpers
    "colorize",
    "format_count",
    "format_path",
    "format_severity",
    "strip_ansi",
    # Format - contract verification
    "verify_deterministic_table",
    "verify_deterministic_json",
    "verify_deterministic_jsonl",
    # Pager
    "paginate",
    "should_paginate",
    "paginate_lines",
    "format_pagination_info",
]
