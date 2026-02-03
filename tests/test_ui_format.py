"""Golden tests for UI format module.

These tests ensure deterministic, stable output from the UI rendering functions.
Golden outputs are stored in tests/golden/ui/ and compared byte-for-byte.
"""

import json
import pytest
from pathlib import Path

from codebatch.ui import (
    render_table,
    render_json,
    render_jsonl,
    Column,
    ColorMode,
    colorize,
    format_count,
    format_path,
    format_severity,
    strip_ansi,
    verify_deterministic_table,
    verify_deterministic_json,
    verify_deterministic_jsonl,
)


# --- Test data ---

SAMPLE_ROWS = [
    {"path": "src/main.py", "kind": "diagnostic", "code": "E001", "severity": "error"},
    {"path": "src/util.py", "kind": "diagnostic", "code": "W002", "severity": "warning"},
    {"path": "src/main.py", "kind": "diagnostic", "code": "E003", "severity": "error"},
    {"path": "tests/test.py", "kind": "diagnostic", "code": "I001", "severity": "info"},
]

SAMPLE_COLUMNS = [
    Column(name="path", header="PATH"),
    Column(name="kind", header="KIND"),
    Column(name="code", header="CODE"),
    Column(name="severity", header="SEVERITY"),
]

SAMPLE_DICT = {
    "batch_id": "batch-abc123",
    "total_files": 42,
    "diagnostics": {
        "errors": 5,
        "warnings": 10,
    },
    "tasks": ["parse", "lint", "analyze"],
}


# --- Golden file helpers ---


GOLDEN_DIR = Path(__file__).parent / "golden" / "ui"


def load_golden(name: str) -> str:
    """Load golden output file."""
    path = GOLDEN_DIR / name
    if not path.exists():
        pytest.skip(f"Golden file not found: {name}")
    return path.read_text(encoding="utf-8")


def save_golden(name: str, content: str) -> None:
    """Save golden output file (for regeneration)."""
    path = GOLDEN_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def assert_golden(name: str, actual: str, *, regenerate: bool = False) -> None:
    """Assert output matches golden file.

    Args:
        name: Golden file name.
        actual: Actual output to compare.
        regenerate: If True, save actual as new golden.
    """
    if regenerate:
        save_golden(name, actual)
        return

    expected = load_golden(name)
    assert actual == expected, f"Output differs from golden/{name}"


# --- Table rendering tests ---


class TestRenderTable:
    """Tests for render_table function."""

    def test_basic_table(self):
        """Should render basic table correctly."""
        output = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
        )

        # Verify structure
        lines = output.split("\n")
        assert len(lines) >= 3  # header + separator + at least 1 row
        assert "PATH" in lines[0]
        assert "---" in lines[1]

    def test_empty_rows(self):
        """Should return empty string for empty rows."""
        output = render_table([], SAMPLE_COLUMNS, color_mode=ColorMode.NEVER)
        assert output == ""

    def test_stable_ordering(self):
        """Same input should produce identical output."""
        output1 = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
        )
        output2 = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
        )
        assert output1 == output2

    def test_sort_key_required_for_determinism(self):
        """Verify determinism with sort_key."""
        assert verify_deterministic_table(SAMPLE_ROWS, SAMPLE_COLUMNS, "path")

    def test_string_columns(self):
        """Should accept string column names."""
        output = render_table(
            SAMPLE_ROWS,
            ["path", "code"],
            sort_key="path",
            color_mode=ColorMode.NEVER,
        )
        assert "PATH" in output
        assert "CODE" in output

    def test_pagination(self):
        """Should paginate rows correctly."""
        output = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
            page_size=2,
            page=0,
        )
        lines = [l for l in output.split("\n") if l and "---" not in l and "PATH" not in l]
        assert len(lines) == 2

    def test_max_rows(self):
        """Should limit rows with max_rows."""
        output = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
            max_rows=2,
        )
        lines = [l for l in output.split("\n") if l and "---" not in l and "PATH" not in l]
        assert len(lines) == 2

    def test_no_header(self):
        """Should render without header."""
        output = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
            show_header=False,
        )
        assert "PATH" not in output
        assert "---" not in output

    def test_golden_table_basic(self):
        """Golden test: basic table output."""
        output = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
        )
        assert_golden("table_basic.txt", output)

    def test_golden_table_no_header(self):
        """Golden test: table without header."""
        output = render_table(
            SAMPLE_ROWS,
            SAMPLE_COLUMNS,
            sort_key="path",
            color_mode=ColorMode.NEVER,
            show_header=False,
        )
        assert_golden("table_no_header.txt", output)


# --- JSON rendering tests ---


class TestRenderJson:
    """Tests for render_json function."""

    def test_basic_json(self):
        """Should render valid JSON."""
        output = render_json(SAMPLE_DICT)
        parsed = json.loads(output)
        assert parsed == SAMPLE_DICT

    def test_sorted_keys(self):
        """Should sort dictionary keys."""
        output = render_json({"z": 1, "a": 2, "m": 3})
        keys = list(json.loads(output).keys())
        assert keys == sorted(keys)

    def test_stable_output(self):
        """Same input should produce identical output."""
        output1 = render_json(SAMPLE_DICT)
        output2 = render_json(SAMPLE_DICT)
        assert output1 == output2

    def test_verify_deterministic(self):
        """Verify determinism."""
        assert verify_deterministic_json(SAMPLE_DICT)

    def test_golden_json_basic(self):
        """Golden test: basic JSON output."""
        output = render_json(SAMPLE_DICT)
        assert_golden("json_basic.json", output)

    def test_nested_objects(self):
        """Should handle nested objects."""
        nested = {
            "outer": {
                "inner": {
                    "value": 42
                }
            },
            "array": [1, 2, 3],
        }
        output = render_json(nested)
        parsed = json.loads(output)
        assert parsed["outer"]["inner"]["value"] == 42


# --- JSONL rendering tests ---


class TestRenderJsonl:
    """Tests for render_jsonl function."""

    def test_basic_jsonl(self):
        """Should render valid JSONL."""
        output = render_jsonl(SAMPLE_ROWS, sort_key="path")
        lines = output.strip().split("\n")
        assert len(lines) == len(SAMPLE_ROWS)

        # Each line should be valid JSON
        for line in lines:
            json.loads(line)

    def test_empty_records(self):
        """Should return empty string for empty records."""
        output = render_jsonl([])
        assert output == ""

    def test_sorted_records(self):
        """Records should be sorted by sort_key."""
        output = render_jsonl(SAMPLE_ROWS, sort_key="code")
        lines = output.strip().split("\n")
        codes = [json.loads(line)["code"] for line in lines]
        assert codes == sorted(codes)

    def test_stable_output(self):
        """Same input should produce identical output."""
        output1 = render_jsonl(SAMPLE_ROWS, sort_key="path")
        output2 = render_jsonl(SAMPLE_ROWS, sort_key="path")
        assert output1 == output2

    def test_verify_deterministic(self):
        """Verify determinism."""
        assert verify_deterministic_jsonl(SAMPLE_ROWS, "path")

    def test_golden_jsonl_basic(self):
        """Golden test: basic JSONL output."""
        output = render_jsonl(SAMPLE_ROWS, sort_key="path")
        assert_golden("jsonl_basic.jsonl", output)


# --- Color tests ---


class TestColorize:
    """Tests for color functions."""

    def test_colorize_never(self):
        """Should not add color in NEVER mode."""
        output = colorize("test", "red", ColorMode.NEVER)
        assert output == "test"
        assert "\033[" not in output

    def test_colorize_always(self):
        """Should add color in ALWAYS mode."""
        output = colorize("test", "red", ColorMode.ALWAYS)
        assert "\033[" in output
        assert "test" in output

    def test_strip_ansi(self):
        """Should remove ANSI codes."""
        colored = colorize("test", "red", ColorMode.ALWAYS)
        stripped = strip_ansi(colored)
        assert stripped == "test"
        assert "\033[" not in stripped

    def test_format_count_error(self):
        """Should color error counts."""
        output = format_count(5, "errors", ColorMode.ALWAYS)
        assert "5 errors" in strip_ansi(output)

    def test_format_count_zero(self):
        """Should dim zero counts."""
        output = format_count(0, "errors", ColorMode.NEVER)
        assert output == "0 errors"

    def test_format_path(self):
        """Should format path."""
        output = format_path("src/main.py", ColorMode.NEVER)
        assert output == "src/main.py"

    def test_format_severity(self):
        """Should format severity levels."""
        for sev in ["error", "warning", "info", "hint"]:
            output = format_severity(sev, ColorMode.NEVER)
            assert output == sev


# --- Column tests ---


class TestColumn:
    """Tests for Column dataclass."""

    def test_create_column(self):
        """Should create column with defaults."""
        col = Column(name="path", header="PATH")
        assert col.name == "path"
        assert col.header == "PATH"
        assert col.width is None
        assert col.align == "left"

    def test_column_with_width(self):
        """Should accept explicit width."""
        col = Column(name="code", header="CODE", width=10)
        assert col.width == 10

    def test_column_alignment(self):
        """Should accept alignment."""
        col = Column(name="count", header="COUNT", align="right")
        assert col.align == "right"
