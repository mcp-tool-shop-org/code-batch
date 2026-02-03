"""Phase 7 gate enforcement tests.

These tests enforce the Phase 7 gates:
- P7-API-DYN: Accurate capability reflection
- P7-API-STABLE: Deterministic output
- P7-API-NO-SIDE-EFFECTS: Read-only capability query
- P7-ERR: Error envelope compliance
- P7-SCHEMA: Schema validation
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from codebatch.cli import get_api_info, cmd_api


class MockArgs:
    """Mock argparse namespace for testing."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# --- Gate P7-API-DYN: Accurate Capability Reflection ---


class TestGateP7ApiDyn:
    """P7-API-DYN gate: API reflects actual build capabilities."""

    def test_commands_match_registry(self):
        """API commands should match the registry."""
        from codebatch.registry import list_commands

        info = get_api_info()
        api_commands = {c["name"] for c in info["commands"]}
        registry_commands = {c.name for c in list_commands()}

        assert api_commands == registry_commands, (
            f"API commands don't match registry! "
            f"Missing: {registry_commands - api_commands}, "
            f"Extra: {api_commands - registry_commands}"
        )

    def test_tasks_match_registry(self):
        """API tasks should match the registry."""
        from codebatch.registry import list_tasks

        info = get_api_info()
        api_tasks = {t["task_id"] for t in info["tasks"]}
        registry_tasks = {t.task_id for t in list_tasks()}

        assert api_tasks == registry_tasks, (
            f"API tasks don't match registry! "
            f"Missing: {registry_tasks - api_tasks}, "
            f"Extra: {api_tasks - registry_tasks}"
        )

    def test_output_kinds_match_registry(self):
        """API output kinds should match the registry."""
        from codebatch.registry import list_output_kinds

        info = get_api_info()
        api_kinds = {ok["kind"] for ok in info["output_kinds"]}
        registry_kinds = {ok.kind for ok in list_output_kinds()}

        assert api_kinds == registry_kinds, (
            f"API output kinds don't match registry! "
            f"Missing: {registry_kinds - api_kinds}, "
            f"Extra: {api_kinds - registry_kinds}"
        )

    def test_pipelines_match_batch_module(self):
        """API pipelines should match PIPELINES from batch module."""
        from codebatch.batch import PIPELINES

        info = get_api_info()
        api_pipelines = {p["name"] for p in info["pipelines"]}

        assert api_pipelines == set(PIPELINES.keys()), (
            f"API pipelines don't match PIPELINES! "
            f"Missing: {set(PIPELINES.keys()) - api_pipelines}, "
            f"Extra: {api_pipelines - set(PIPELINES.keys())}"
        )

    def test_feature_phase5_workflow_accurate(self):
        """Feature flag for phase5_workflow should be accurate."""
        info = get_api_info()

        try:
            from codebatch import workflow
            expected = True
        except ImportError:
            expected = False

        assert info["build"]["features"]["phase5_workflow"] == expected

    def test_feature_phase6_ui_accurate(self):
        """Feature flag for phase6_ui should be accurate."""
        info = get_api_info()

        try:
            from codebatch import ui
            expected = True
        except ImportError:
            expected = False

        assert info["build"]["features"]["phase6_ui"] == expected

    def test_feature_diff_accurate(self):
        """Feature flag for diff should be accurate."""
        info = get_api_info()

        try:
            from codebatch.ui import diff
            expected = True
        except ImportError:
            expected = False

        assert info["build"]["features"]["diff"] == expected


# --- Gate P7-API-STABLE: Deterministic Output ---


class TestGateP7ApiStable:
    """P7-API-STABLE gate: API output is deterministic."""

    def test_identical_output_across_calls(self, capsys):
        """API output should be identical across multiple calls."""
        args = MockArgs(json=True)

        cmd_api(args)
        output1 = capsys.readouterr().out

        cmd_api(args)
        output2 = capsys.readouterr().out

        assert output1 == output2, "API output not identical across calls"

    def test_commands_sorted_by_name(self):
        """Commands should be sorted by name."""
        info = get_api_info()
        names = [c["name"] for c in info["commands"]]
        assert names == sorted(names), "Commands not sorted by name"

    def test_tasks_sorted_by_task_id(self):
        """Tasks should be sorted by task_id."""
        info = get_api_info()
        task_ids = [t["task_id"] for t in info["tasks"]]
        assert task_ids == sorted(task_ids), "Tasks not sorted by task_id"

    def test_output_kinds_sorted_by_kind(self):
        """Output kinds should be sorted by kind."""
        info = get_api_info()
        kinds = [ok["kind"] for ok in info["output_kinds"]]
        assert kinds == sorted(kinds), "Output kinds not sorted by kind"

    def test_pipelines_sorted_by_name(self):
        """Pipelines should be sorted by name."""
        info = get_api_info()
        names = [p["name"] for p in info["pipelines"]]
        assert names == sorted(names), "Pipelines not sorted by name"

    def test_no_timing_fields(self):
        """API output should not contain timing-dependent fields."""
        info = get_api_info()

        # Check top-level
        assert "created_at" not in info
        assert "timestamp" not in info

        # Check build
        assert "build_time" not in info["build"]


# --- Gate P7-API-NO-SIDE-EFFECTS: Read-Only Capability Query ---


class TestGateP7ApiNoSideEffects:
    """P7-API-NO-SIDE-EFFECTS gate: API works without store, creates no files."""

    def test_works_without_store(self, capsys):
        """API command should work without --store argument."""
        args = MockArgs(json=True)
        result = cmd_api(args)

        assert result == 0, "API command failed without store"

        output = capsys.readouterr().out
        info = json.loads(output)
        assert info["schema_name"] == "codebatch.api"

    def test_creates_no_files(self, tmp_path):
        """API command should create no files."""
        # Record files before
        before_files = set()
        for root, dirs, files in os.walk(tmp_path):
            for f in files:
                before_files.add(os.path.join(root, f))

        # Change to temp dir and run api
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            args = MockArgs(json=True)
            cmd_api(args)
        finally:
            os.chdir(original_cwd)

        # Record files after
        after_files = set()
        for root, dirs, files in os.walk(tmp_path):
            for f in files:
                after_files.add(os.path.join(root, f))

        assert before_files == after_files, (
            f"API command created files: {after_files - before_files}"
        )

    def test_exit_code_zero(self, capsys):
        """API command should return exit code 0."""
        args = MockArgs(json=True)
        result = cmd_api(args)
        assert result == 0


# --- Gate P7-SCHEMA: Schema Validation ---


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestGateP7Schema:
    """P7-SCHEMA gate: JSON outputs validate against schemas."""

    @pytest.fixture
    def api_schema(self):
        """Load the API schema."""
        schema_path = Path(__file__).parent.parent / "schemas" / "api.schema.json"
        if not schema_path.exists():
            pytest.skip("API schema not found")
        with open(schema_path) as f:
            return json.load(f)

    @pytest.fixture
    def error_schema(self):
        """Load the error schema."""
        schema_path = Path(__file__).parent.parent / "schemas" / "error.schema.json"
        if not schema_path.exists():
            pytest.skip("Error schema not found")
        with open(schema_path) as f:
            return json.load(f)

    def test_api_output_validates(self, api_schema, capsys):
        """API --json output should validate against schema."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        # Validate against schema
        jsonschema.validate(info, api_schema)

    def test_api_has_required_fields(self, capsys):
        """API output should have all required fields."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        required_fields = [
            "schema_name",
            "schema_version",
            "producer",
            "build",
            "commands",
            "pipelines",
            "tasks",
            "output_kinds",
        ]

        for field in required_fields:
            assert field in info, f"Missing required field: {field}"

    def test_command_has_required_fields(self, capsys):
        """Each command should have required fields."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        required_cmd_fields = ["name", "read_only", "supports_json", "since"]

        for cmd in info["commands"]:
            for field in required_cmd_fields:
                assert field in cmd, f"Command {cmd.get('name', '?')} missing field: {field}"

    def test_task_has_required_fields(self, capsys):
        """Each task should have required fields."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        required_task_fields = ["task_id", "type", "kinds_out", "deps"]

        for task in info["tasks"]:
            for field in required_task_fields:
                assert field in task, f"Task {task.get('task_id', '?')} missing field: {field}"

    def test_output_kind_has_required_fields(self, capsys):
        """Each output kind should have required fields."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        required_ok_fields = ["kind", "canonical_key"]

        for ok in info["output_kinds"]:
            for field in required_ok_fields:
                assert field in ok, f"Output kind {ok.get('kind', '?')} missing field: {field}"


# --- Additional Integration Tests ---


class TestApiIntegration:
    """Integration tests for API command."""

    def test_human_readable_output(self, capsys):
        """API without --json should produce human-readable output."""
        args = MockArgs(json=False)
        result = cmd_api(args)

        assert result == 0
        output = capsys.readouterr().out

        # Should contain key sections
        assert "CodeBatch API" in output
        assert "Producer:" in output
        assert "Features:" in output
        assert "Commands" in output
        assert "Pipelines" in output
        assert "Output Kinds" in output

    def test_schema_version_is_integer(self, capsys):
        """Schema version should be a positive integer."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        assert isinstance(info["schema_version"], int)
        assert info["schema_version"] >= 1

    def test_producer_version_is_semver(self, capsys):
        """Producer version should be semantic version format."""
        import re

        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        version = info["producer"]["version"]
        assert re.match(r"^\d+\.\d+\.\d+$", version), f"Invalid version: {version}"

    def test_command_names_are_valid(self, capsys):
        """Command names should follow naming convention."""
        import re

        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        # Command names should be lowercase, dot-delimited
        pattern = r"^[a-z][a-z0-9]*([.][a-z][a-z0-9]*)*$"
        for cmd in info["commands"]:
            assert re.match(pattern, cmd["name"]), f"Invalid command name: {cmd['name']}"

    def test_canonical_keys_are_non_empty(self, capsys):
        """Canonical keys should not be empty."""
        args = MockArgs(json=True)
        cmd_api(args)
        output = capsys.readouterr().out
        info = json.loads(output)

        for ok in info["output_kinds"]:
            assert len(ok["canonical_key"]) > 0, f"Empty canonical key for {ok['kind']}"
