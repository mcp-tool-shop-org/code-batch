"""Tests for explain command fidelity (Phase 6).

Tests verify:
- Explain output includes output kinds used
- Explain output includes tasks referenced
- Explain output does NOT mention events as a dependency
- Explain output is deterministic
"""

import json
import pytest

from codebatch.cli import cmd_explain, get_explain_info, print_explain


class MockArgs:
    """Mock argparse namespace for testing."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestExplainCommand:
    """Tests for explain command."""

    def test_explain_inspect(self, capsys):
        """Should explain inspect command."""
        args = MockArgs(subcommand="inspect", json=False)
        result = cmd_explain(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "inspect" in captured.out.lower()
        assert "Data Sources:" in captured.out

    def test_explain_diff(self, capsys):
        """Should explain diff command."""
        args = MockArgs(subcommand="diff", json=False)
        result = cmd_explain(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "diff" in captured.out.lower()

    def test_explain_unknown_command(self, capsys):
        """Should handle unknown commands gracefully."""
        args = MockArgs(subcommand="nonexistent", json=False)
        result = cmd_explain(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out

    def test_explain_json_output(self, capsys):
        """Should produce valid JSON output."""
        args = MockArgs(subcommand="inspect", json=True)
        result = cmd_explain(args)

        assert result == 0
        captured = capsys.readouterr()

        # Should be valid JSON
        info = json.loads(captured.out)
        assert isinstance(info, dict)
        assert "command" in info

    def test_explain_json_stable(self, capsys):
        """JSON output should be deterministic."""
        args = MockArgs(subcommand="inspect", json=True)

        # Run twice
        cmd_explain(args)
        output1 = capsys.readouterr().out

        cmd_explain(args)
        output2 = capsys.readouterr().out

        # Should be identical
        assert output1 == output2


class TestExplainFidelity:
    """Tests for P6-EXPLAIN gate: explain fidelity."""

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements", "summary"])
    def test_lists_output_kinds(self, command):
        """Explain should list which output kinds are used."""
        info = get_explain_info(command)

        assert "output_kinds_used" in info
        assert isinstance(info["output_kinds_used"], list)
        assert len(info["output_kinds_used"]) > 0

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements", "summary"])
    def test_lists_tasks_referenced(self, command):
        """Explain should describe which tasks are referenced."""
        info = get_explain_info(command)

        assert "tasks_referenced" in info
        assert info["tasks_referenced"]  # Not empty

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements", "summary"])
    def test_does_not_mention_events(self, command):
        """Explain should NOT mention events as a dependency."""
        info = get_explain_info(command)

        # Check data_sources - should not include events
        for src in info.get("data_sources", []):
            assert "event" not in src.lower(), f"Events mentioned in data_sources: {src}"

        # Check notes - should explicitly say "Does NOT use events"
        notes_text = " ".join(info.get("notes", []))
        assert "does not use events" in notes_text.lower(), "Should explicitly state events are not used"

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements", "summary"])
    def test_lists_data_sources(self, command):
        """Explain should list data sources."""
        info = get_explain_info(command)

        assert "data_sources" in info
        assert isinstance(info["data_sources"], list)
        assert len(info["data_sources"]) > 0

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements", "summary"])
    def test_explains_filters(self, command):
        """Explain should describe available filters."""
        info = get_explain_info(command)

        assert "filters" in info
        assert isinstance(info["filters"], list)

    @pytest.mark.parametrize("command", ["inspect", "diff", "regressions", "improvements", "summary"])
    def test_deterministic_output(self, command):
        """Explain output should be identical across runs."""
        info1 = get_explain_info(command)
        info2 = get_explain_info(command)

        assert info1 == info2


class TestExplainInfoStructure:
    """Tests for explain info structure."""

    def test_info_has_required_fields(self):
        """Explain info should have all required fields."""
        info = get_explain_info("inspect")

        required_fields = [
            "command",
            "description",
            "data_sources",
            "output_kinds_used",
            "tasks_referenced",
            "filters",
            "grouping",
            "notes",
        ]

        for field in required_fields:
            assert field in info, f"Missing required field: {field}"

    def test_unknown_command_has_structure(self):
        """Unknown command should still return valid structure."""
        info = get_explain_info("nonexistent")

        assert info["command"] == "nonexistent"
        assert "Unknown command" in info["description"]
        assert isinstance(info["data_sources"], list)
        assert isinstance(info["output_kinds_used"], list)

    def test_output_kinds_are_valid(self):
        """Output kinds should be valid CodeBatch kinds."""
        valid_kinds = {"diagnostic", "metric", "symbol", "ast"}

        for command in ["inspect", "diff", "regressions", "improvements"]:
            info = get_explain_info(command)
            for kind in info["output_kinds_used"]:
                assert kind in valid_kinds, f"Invalid kind in {command}: {kind}"


class TestPrintExplain:
    """Tests for print_explain function."""

    def test_prints_all_sections(self, capsys):
        """Should print all sections."""
        info = {
            "command": "test",
            "description": "Test command",
            "data_sources": ["source1", "source2"],
            "output_kinds_used": ["diagnostic"],
            "tasks_referenced": "all tasks",
            "filters": ["filter1"],
            "grouping": "by kind",
            "notes": ["note1", "note2"],
        }

        print_explain(info)
        captured = capsys.readouterr()

        assert "Command: test" in captured.out
        assert "Description: Test command" in captured.out
        assert "Data Sources:" in captured.out
        assert "source1" in captured.out
        assert "Output Kinds Used:" in captured.out
        assert "diagnostic" in captured.out
        assert "Tasks Referenced: all tasks" in captured.out
        assert "Filters/Parameters:" in captured.out
        assert "filter1" in captured.out
        assert "Grouping: by kind" in captured.out
        assert "Notes:" in captured.out
        assert "note1" in captured.out
