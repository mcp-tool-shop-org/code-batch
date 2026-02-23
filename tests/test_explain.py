"""Tests for explain command fidelity (Phase 6).

Tests verify:
- Explain output includes output kinds used
- Explain output includes tasks referenced
- Explain output does NOT mention events as a dependency
- Explain output is deterministic
- Explain works even when events directory doesn't exist (negative test)
"""

import json
import shutil
import pytest
from pathlib import Path

from codebatch.cli import cmd_explain, cmd_inspect, get_explain_info, print_explain
from codebatch.store import init_store
from codebatch.snapshot import SnapshotBuilder
from codebatch.batch import BatchManager
from codebatch.runner import ShardRunner
from codebatch.common import object_shard_prefix
from codebatch.tasks import get_executor


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

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements", "summary"]
    )
    def test_lists_output_kinds(self, command):
        """Explain should list which output kinds are used."""
        info = get_explain_info(command)

        assert "output_kinds_used" in info
        assert isinstance(info["output_kinds_used"], list)
        assert len(info["output_kinds_used"]) > 0

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements", "summary"]
    )
    def test_lists_tasks_referenced(self, command):
        """Explain should describe which tasks are referenced."""
        info = get_explain_info(command)

        assert "tasks_referenced" in info
        assert info["tasks_referenced"]  # Not empty

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements", "summary"]
    )
    def test_does_not_mention_events(self, command):
        """Explain should NOT mention events as a dependency."""
        info = get_explain_info(command)

        # Check data_sources - should not include events
        for src in info.get("data_sources", []):
            assert "event" not in src.lower(), (
                f"Events mentioned in data_sources: {src}"
            )

        # Check notes - should explicitly say "Does NOT use events"
        notes_text = " ".join(info.get("notes", []))
        assert "does not use events" in notes_text.lower(), (
            "Should explicitly state events are not used"
        )

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements", "summary"]
    )
    def test_lists_data_sources(self, command):
        """Explain should list data sources."""
        info = get_explain_info(command)

        assert "data_sources" in info
        assert isinstance(info["data_sources"], list)
        assert len(info["data_sources"]) > 0

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements", "summary"]
    )
    def test_explains_filters(self, command):
        """Explain should describe available filters."""
        info = get_explain_info(command)

        assert "filters" in info
        assert isinstance(info["filters"], list)

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements", "summary"]
    )
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


class TestExplainEventsIndependence:
    """P6-EXPLAIN negative test: explain should be unchanged when events don't exist.

    This verifies that Phase 6 commands truly don't depend on events by:
    1. Running inspect with events directory present
    2. Deleting events directory
    3. Running inspect again - output should be identical
    """

    @pytest.fixture
    def store_with_and_without_events(self, tmp_path: Path):
        """Create a store, run tasks, capture outputs with/without events."""
        store = tmp_path / "store"
        store.mkdir()
        init_store(store)

        # Create corpus
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "test.py").write_text("x = 1\nprint(x)")

        # Create snapshot and batch
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus)

        manager = BatchManager(store)
        batch_id = manager.init_batch(snapshot_id, "full")

        # Run tasks
        runner = ShardRunner(store)
        records = builder.load_file_index(snapshot_id)
        shards = set(object_shard_prefix(r["object"]) for r in records)

        plan = manager.load_plan(batch_id)
        for shard_id in shards:
            for task_def in plan["tasks"]:
                executor = get_executor(task_def["task_id"])
                runner.run_shard(batch_id, task_def["task_id"], shard_id, executor)

        return store, batch_id

    def test_inspect_output_unchanged_without_events(
        self, store_with_and_without_events, capsys
    ):
        """inspect output should be identical with or without events directory."""
        store, batch_id = store_with_and_without_events

        # Run inspect with events present
        args = MockArgs(
            store=str(store),
            batch=batch_id,
            path="test.py",
            kinds=None,
            json=True,
            no_color=True,
            explain=False,
        )
        cmd_inspect(args)
        output_with_events = capsys.readouterr().out

        # Delete events directory if it exists
        events_dir = store / "events"
        if events_dir.exists():
            shutil.rmtree(events_dir)

        # Run inspect again without events
        cmd_inspect(args)
        output_without_events = capsys.readouterr().out

        # Output should be identical
        assert output_with_events == output_without_events, (
            "inspect output changed after deleting events directory - "
            "Phase 6 commands should NOT depend on events"
        )

    def test_explain_output_unchanged_without_events(self, capsys):
        """explain output should be identical regardless of events existence.

        This is a simpler test since explain doesn't need a store.
        """
        # Get explain output
        args = MockArgs(subcommand="inspect", json=True)
        cmd_explain(args)
        output1 = capsys.readouterr().out

        # Get explain output again (events state unchanged, but verifies determinism)
        cmd_explain(args)
        output2 = capsys.readouterr().out

        assert output1 == output2, "explain output should be deterministic"

        # Also verify the explain info explicitly states no events dependency
        info = json.loads(output1)
        notes_text = " ".join(info.get("notes", []))
        assert "does not use events" in notes_text.lower(), (
            "explain should explicitly state that events are NOT used"
        )

    @pytest.mark.parametrize(
        "command", ["inspect", "diff", "regressions", "improvements"]
    )
    def test_explain_never_mentions_events_in_data_sources(self, command):
        """Explain data_sources should never mention events."""
        info = get_explain_info(command)

        # No data source should reference events
        for src in info.get("data_sources", []):
            src_lower = src.lower()
            assert "event" not in src_lower, (
                f"Explain for '{command}' mentions events in data_sources: {src}"
            )
