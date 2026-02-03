"""Tests for the gate system.

Tests cover:
- Registry operations (registration, lookup, aliases)
- Runner execution
- Bundle execution
- CLI output format
"""

import json
import pytest
from pathlib import Path

from codebatch.gates.result import (
    GateResult,
    GateStatus,
    GateContext,
    GateFailure,
    GateEnvironment,
    BundleResult,
)
from codebatch.gates.registry import (
    GateRegistry,
    GateDefinition,
    get_registry,
    list_gates,
)
from codebatch.gates.runner import GateRunner, run_gate, run_bundle
from codebatch.gates import definitions  # Ensure gates are registered


class TestGateResult:
    """Tests for GateResult dataclass."""

    def test_create_passing_result(self):
        """Should create a passing result."""
        result = GateResult(
            gate_id="P3-A1",
            passed=True,
            status=GateStatus.ENFORCED,
        )
        assert result.passed is True
        assert result.gate_id == "P3-A1"
        assert result.status == GateStatus.ENFORCED

    def test_create_failing_result(self):
        """Should create a failing result with failures."""
        result = GateResult(
            gate_id="P3-A1",
            passed=False,
            status=GateStatus.ENFORCED,
        )
        result.add_failure(
            message="Cache mismatch",
            expected="100 outputs",
            actual="95 outputs",
        )
        assert result.passed is False
        assert len(result.failures) == 1
        assert result.failures[0].message == "Cache mismatch"

    def test_to_dict(self):
        """Should convert to dictionary."""
        result = GateResult(
            gate_id="P3-A1",
            passed=True,
            status=GateStatus.ENFORCED,
            duration_ms=1234,
            details={"outputs": 100},
        )
        d = result.to_dict()

        assert d["gate_id"] == "P3-A1"
        assert d["passed"] is True
        assert d["status"] == "ENFORCED"
        assert d["duration_ms"] == 1234
        assert d["details"]["outputs"] == 100

    def test_to_json(self):
        """Should convert to JSON string."""
        result = GateResult(gate_id="P3-A1", passed=True)
        j = result.to_json()

        parsed = json.loads(j)
        assert parsed["gate_id"] == "P3-A1"
        assert parsed["passed"] is True

    def test_from_dict(self):
        """Should create from dictionary."""
        data = {
            "gate_id": "P3-A1",
            "passed": True,
            "status": "ENFORCED",
            "duration_ms": 500,
            "details": {"x": 1},
            "failures": [],
            "artifacts": [],
        }
        result = GateResult.from_dict(data)

        assert result.gate_id == "P3-A1"
        assert result.passed is True
        assert result.status == GateStatus.ENFORCED


class TestGateRegistry:
    """Tests for GateRegistry."""

    def test_register_gate(self):
        """Should register a gate."""
        registry = GateRegistry()

        def test_gate(ctx):
            return GateResult(gate_id="TEST-1", passed=True)

        registry.register(
            gate_id="TEST-1",
            title="Test gate",
            description="A test gate.",
            status=GateStatus.HARNESS,
            required_inputs=["store"],
            tags=["test"],
            entrypoint=test_gate,
        )

        gate = registry.get("TEST-1")
        assert gate is not None
        assert gate.gate_id == "TEST-1"
        assert gate.title == "Test gate"

    def test_register_with_alias(self):
        """Should register gate with alias."""
        registry = GateRegistry()

        def test_gate(ctx):
            return GateResult(gate_id="TEST-2", passed=True)

        registry.register(
            gate_id="TEST-2",
            title="Test gate 2",
            description="Another test gate.",
            status=GateStatus.HARNESS,
            required_inputs=["store"],
            tags=["test"],
            entrypoint=test_gate,
            aliases=["T2"],
        )

        # Get by ID
        gate = registry.get("TEST-2")
        assert gate is not None

        # Get by alias
        gate2 = registry.get("T2")
        assert gate2 is not None
        assert gate2.gate_id == "TEST-2"

    def test_suggest_similar(self):
        """Should suggest similar gate IDs."""
        registry = GateRegistry()

        def test_gate(ctx):
            return GateResult(gate_id="P3-A1", passed=True)

        registry.register(
            gate_id="P3-A1",
            title="Cache equivalence",
            description="Test.",
            status=GateStatus.ENFORCED,
            required_inputs=["store"],
            tags=["cache"],
            entrypoint=test_gate,
        )

        suggestions = registry.suggest_similar("P3-A")
        assert "P3-A1" in suggestions

    def test_list_by_status(self):
        """Should list gates by status."""
        registry = GateRegistry()

        def gate1(ctx):
            return GateResult(gate_id="G1", passed=True)

        def gate2(ctx):
            return GateResult(gate_id="G2", passed=True)

        registry.register("G1", "G1", "", GateStatus.ENFORCED, [], [], gate1)
        registry.register("G2", "G2", "", GateStatus.HARNESS, [], [], gate2)

        enforced = registry.list_by_status(GateStatus.ENFORCED)
        assert len(enforced) == 1
        assert enforced[0].gate_id == "G1"

    def test_list_by_tag(self):
        """Should list gates by tag."""
        registry = GateRegistry()

        def gate1(ctx):
            return GateResult(gate_id="G1", passed=True)

        registry.register("G1", "G1", "", GateStatus.ENFORCED, [], ["cache", "phase3"], gate1)

        cached = registry.list_by_tag("cache")
        assert len(cached) == 1
        assert cached[0].gate_id == "G1"


class TestGlobalRegistry:
    """Tests for the global registry with registered gates."""

    def test_gates_registered(self):
        """Should have gates registered from definitions module."""
        gates = list_gates()
        assert len(gates) >= 8  # At least 8 gates registered

    def test_get_p3_a1(self):
        """Should get P3-A1 gate."""
        registry = get_registry()
        gate = registry.get("P3-A1")

        assert gate is not None
        assert gate.gate_id == "P3-A1"
        assert "cache" in gate.tags

    def test_alias_a1(self):
        """Should resolve A1 alias to P3-A1."""
        registry = get_registry()
        gate = registry.get("A1")

        assert gate is not None
        assert gate.gate_id == "P3-A1"


class TestGateRunner:
    """Tests for GateRunner."""

    @pytest.fixture
    def store_with_batch(self, tmp_path: Path) -> tuple[Path, str]:
        """Create a store with a batch for testing."""
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.common import object_shard_prefix
        from codebatch.tasks import get_executor

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

    def test_run_unknown_gate(self, tmp_path: Path):
        """Should raise error for unknown gate."""
        store = tmp_path / "store"
        store.mkdir()

        runner = GateRunner(store)

        with pytest.raises(ValueError, match="Unknown gate"):
            runner.run("NONEXISTENT-GATE")

    def test_run_p1_g1(self, store_with_batch):
        """Should run P1-G1 store validation gate."""
        store, batch_id = store_with_batch

        runner = GateRunner(store)
        result = runner.run("P1-G1")

        assert result.gate_id == "P1-G1"
        assert result.passed is True
        assert result.status == GateStatus.ENFORCED
        assert result.duration_ms >= 0

    def test_run_p2_g6(self, store_with_batch):
        """Should run P2-G6 truth-store guard gate."""
        store, batch_id = store_with_batch

        runner = GateRunner(store)
        result = runner.run("P2-G6")

        assert result.passed is True
        assert "found" in result.details

    def test_run_bundle_phase1(self, store_with_batch):
        """Should run phase1 bundle."""
        store, batch_id = store_with_batch

        runner = GateRunner(store)
        result = runner.run_bundle("phase1")

        assert result.bundle_name == "phase1"
        assert result.passed_count >= 0
        assert result.total >= 1

    def test_run_bundle_release(self, store_with_batch):
        """Should run release bundle (all ENFORCED gates)."""
        store, batch_id = store_with_batch

        runner = GateRunner(store)
        result = runner.run_bundle("release", batch_id=batch_id)

        assert result.bundle_name == "release"
        assert len(result.results) > 0
        # All gates should have ENFORCED status
        for r in result.results:
            assert r.status == GateStatus.ENFORCED


class TestBundleResult:
    """Tests for BundleResult."""

    def test_bundle_result_to_dict(self):
        """Should convert to dictionary."""
        result = BundleResult(
            bundle_name="release",
            passed=True,
            total=5,
            passed_count=4,
            failed_count=0,
            skipped_count=1,
            duration_ms=1000,
            results=[],
        )
        d = result.to_dict()

        assert d["bundle_name"] == "release"
        assert d["passed"] is True
        assert d["total"] == 5
        assert d["passed_count"] == 4

    def test_bundle_result_to_json(self):
        """Should convert to JSON."""
        result = BundleResult(
            bundle_name="test",
            passed=True,
            total=1,
            passed_count=1,
            failed_count=0,
            skipped_count=0,
            duration_ms=100,
        )
        j = result.to_json()
        parsed = json.loads(j)

        assert parsed["bundle_name"] == "test"


class TestGateContext:
    """Tests for GateContext."""

    def test_context_to_dict(self):
        """Should convert to dictionary."""
        ctx = GateContext(
            store_root=Path("/tmp/store"),
            batch_id="batch-123",
            snapshot_id="snap-456",
        )
        d = ctx.to_dict()

        assert "store" in d
        assert d["batch_id"] == "batch-123"
        assert d["snapshot_id"] == "snap-456"

    def test_get_artifact_dir(self, tmp_path: Path):
        """Should create artifact directory."""
        ctx = GateContext(
            store_root=tmp_path,
            run_id="abc123",
        )
        artifact_dir = ctx.get_artifact_dir("P3-A1")

        assert artifact_dir.exists()
        assert artifact_dir == tmp_path / "indexes" / "gate_artifacts" / "P3-A1" / "abc123"

    def test_write_artifact(self, tmp_path: Path):
        """Should write artifact file."""
        ctx = GateContext(
            store_root=tmp_path,
            run_id="test-run",
        )
        path = ctx.write_artifact("P3-A1", "diff.txt", "line1\nline2\n")

        assert path.exists()
        assert path.read_text() == "line1\nline2\n"
        assert "gate_artifacts" in str(path)

    def test_write_artifact_json(self, tmp_path: Path):
        """Should write JSON artifact file."""
        import json

        ctx = GateContext(
            store_root=tmp_path,
            run_id="test-run",
        )
        data = {"count": 42, "items": ["a", "b"]}
        path = ctx.write_artifact_json("P3-A1", "report.json", data)

        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded == data


class TestGateFailure:
    """Tests for GateFailure."""

    def test_failure_to_dict(self):
        """Should convert to dictionary."""
        failure = GateFailure(
            message="Something went wrong",
            location="file.py:10",
            expected="foo",
            actual="bar",
            suggestion="Try X instead",
        )
        d = failure.to_dict()

        assert d["message"] == "Something went wrong"
        assert d["location"] == "file.py:10"
        assert d["expected"] == "foo"
        assert d["actual"] == "bar"
        assert d["suggestion"] == "Try X instead"

    def test_failure_omits_none(self):
        """Should omit None values from dict."""
        failure = GateFailure(message="Error")
        d = failure.to_dict()

        assert "message" in d
        assert "location" not in d
        assert "expected" not in d
