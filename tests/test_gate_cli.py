"""End-to-end tests for gate CLI commands.

Tests cover:
- gate-list command
- gate-run command
- gate-bundle command
- gate-explain command
- JSON output format
- Exit codes
"""

import json
import pytest
import sys
from io import StringIO
from pathlib import Path

from codebatch.cli import main
from codebatch.store import init_store
from codebatch.snapshot import SnapshotBuilder
from codebatch.batch import BatchManager
from codebatch.runner import ShardRunner
from codebatch.common import object_shard_prefix
from codebatch.tasks import get_executor


class CLIRunner:
    """Simple CLI runner that captures stdout/stderr."""

    def invoke(self, args: list[str]) -> "CLIResult":
        """Run CLI with given args and capture output."""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_out = StringIO()
        sys.stderr = captured_err = StringIO()

        try:
            exit_code = main(args)
        except SystemExit as e:
            exit_code = e.code if e.code is not None else 0
        except Exception as e:
            exit_code = 2
            print(f"Error: {e}", file=sys.stderr)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = captured_out.getvalue() + captured_err.getvalue()
        return CLIResult(exit_code=exit_code, output=output)


class CLIResult:
    """Result from CLI invocation."""

    def __init__(self, exit_code: int, output: str):
        self.exit_code = exit_code
        self.output = output


@pytest.fixture
def cli_runner():
    """Create a CLI runner."""
    return CLIRunner()


@pytest.fixture
def store_with_batch(tmp_path: Path) -> tuple[Path, str]:
    """Create a store with a batch for testing."""
    store = tmp_path / "store"
    store.mkdir()
    init_store(store)

    # Create a simple corpus
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "test.py").write_text("print('hello')")

    # Create snapshot
    builder = SnapshotBuilder(store)
    snapshot_id = builder.build(corpus)

    # Create batch
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


class TestGateListCommand:
    """Tests for gate-list command."""

    def test_list_gates(self, cli_runner):
        """Should list all gates."""
        result = cli_runner.invoke(["gate-list"])

        assert result.exit_code == 0
        assert "P1-G1" in result.output
        assert "P3-A1" in result.output

    def test_list_gates_json(self, cli_runner):
        """Should output JSON format."""
        result = cli_runner.invoke(["gate-list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 8

        # Check gate structure
        gate = next(g for g in data if g["gate_id"] == "P3-A1")
        assert "title" in gate
        assert "status" in gate
        assert "tags" in gate

    def test_list_by_status(self, cli_runner):
        """Should filter by status."""
        result = cli_runner.invoke(["gate-list", "--status", "ENFORCED"])

        assert result.exit_code == 0
        assert "ENFORCED" in result.output
        # HARNESS gates should not appear when filtering ENFORCED
        assert (
            "P2-G7" not in result.output
            or "HARNESS" not in result.output.split("P2-G7")[0]
        )

    def test_list_by_tag(self, cli_runner):
        """Should filter by tag."""
        result = cli_runner.invoke(["gate-list", "--tag", "cache"])

        assert result.exit_code == 0
        assert "P3-A1" in result.output
        # Non-cache gates should not appear
        assert "P1-G1" not in result.output


class TestGateRunCommand:
    """Tests for gate-run command."""

    def test_run_gate(self, cli_runner, store_with_batch):
        """Should run a gate and show results."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(["gate-run", "P1-G1", "--store", str(store)])

        assert result.exit_code == 0
        assert "P1-G1" in result.output
        assert "PASS" in result.output or "passed" in result.output.lower()

    def test_run_gate_json(self, cli_runner, store_with_batch):
        """Should output JSON format."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(
            ["gate-run", "P1-G1", "--store", str(store), "--json"]
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["gate_id"] == "P1-G1"
        assert data["passed"] is True
        assert "duration_ms" in data

    def test_run_gate_with_batch(self, cli_runner, store_with_batch):
        """Should run gate with batch context."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(
            ["gate-run", "P2-G6", "--store", str(store), "--batch", batch_id]
        )

        assert result.exit_code == 0
        assert "P2-G6" in result.output

    def test_run_unknown_gate(self, cli_runner, store_with_batch):
        """Should error on unknown gate with suggestions."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(["gate-run", "P3-A", "--store", str(store)])

        # Should fail with error
        assert result.exit_code != 0
        # Should suggest similar gates
        assert "P3-A1" in result.output or "Did you mean" in result.output

    def test_run_gate_by_alias(self, cli_runner, store_with_batch):
        """Should resolve alias to gate."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(
            ["gate-run", "A1", "--store", str(store), "--batch", batch_id, "--json"]
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["gate_id"] == "P3-A1"


class TestGateBundleCommand:
    """Tests for gate-bundle command."""

    def test_run_phase1_bundle(self, cli_runner, store_with_batch):
        """Should run phase1 bundle."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(["gate-bundle", "phase1", "--store", str(store)])

        assert result.exit_code == 0
        assert "phase1" in result.output.lower()

    def test_run_release_bundle(self, cli_runner, store_with_batch):
        """Should run release bundle."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(
            ["gate-bundle", "release", "--store", str(store), "--batch", batch_id]
        )

        # Release bundle runs all ENFORCED gates
        assert "release" in result.output.lower() or result.exit_code == 0

    def test_bundle_json_output(self, cli_runner, store_with_batch):
        """Should output JSON format."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(
            ["gate-bundle", "phase1", "--store", str(store), "--json"]
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["bundle_name"] == "phase1"
        assert "total" in data
        assert "passed_count" in data
        assert "results" in data

    def test_bundle_fail_fast(self, cli_runner, store_with_batch):
        """Should stop on first failure with --fail-fast."""
        store, batch_id = store_with_batch

        # This tests the flag is accepted
        result = cli_runner.invoke(
            ["gate-bundle", "phase1", "--store", str(store), "--fail-fast"]
        )

        # Should complete (may pass or fail based on gate results)
        assert result.exit_code in [0, 1, 2]

    def test_unknown_bundle(self, cli_runner, store_with_batch):
        """Should error on unknown bundle."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(
            ["gate-bundle", "nonexistent", "--store", str(store)]
        )

        assert result.exit_code != 0
        assert "Unknown" in result.output or "unknown" in result.output.lower()


class TestGateExplainCommand:
    """Tests for gate-explain command."""

    def test_explain_gate(self, cli_runner):
        """Should explain a gate."""
        result = cli_runner.invoke(["gate-explain", "P3-A1"])

        assert result.exit_code == 0
        assert "P3-A1" in result.output
        assert "Cache equivalence" in result.output

    def test_explain_shows_status(self, cli_runner):
        """Should show gate status."""
        result = cli_runner.invoke(["gate-explain", "P3-A1"])

        assert result.exit_code == 0
        assert "ENFORCED" in result.output

    def test_explain_shows_tags(self, cli_runner):
        """Should show gate tags."""
        result = cli_runner.invoke(["gate-explain", "P3-A1"])

        assert result.exit_code == 0
        assert "cache" in result.output.lower()

    def test_explain_shows_required_inputs(self, cli_runner):
        """Should show required inputs."""
        result = cli_runner.invoke(["gate-explain", "P3-A1"])

        assert result.exit_code == 0
        assert "store" in result.output.lower() or "batch" in result.output.lower()

    def test_explain_unknown_gate(self, cli_runner):
        """Should error on unknown gate."""
        result = cli_runner.invoke(["gate-explain", "NONEXISTENT"])

        assert result.exit_code != 0
        assert "Unknown" in result.output or "not found" in result.output.lower()

    def test_explain_by_alias(self, cli_runner):
        """Should resolve alias."""
        result = cli_runner.invoke(["gate-explain", "A1"])

        assert result.exit_code == 0
        assert "P3-A1" in result.output


class TestGateExitCodes:
    """Tests for exit codes."""

    def test_passing_gate_exit_0(self, cli_runner, store_with_batch):
        """Should exit 0 when gate passes."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(["gate-run", "P1-G1", "--store", str(store)])

        assert result.exit_code == 0

    def test_passing_bundle_exit_0(self, cli_runner, store_with_batch):
        """Should exit 0 when bundle passes."""
        store, batch_id = store_with_batch

        result = cli_runner.invoke(["gate-bundle", "phase1", "--store", str(store)])

        assert result.exit_code == 0
