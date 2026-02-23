"""Gate runner for executing gates and bundles.

The runner executes gates with context, measures duration, and captures artifacts.
"""

import time
import uuid
from pathlib import Path
from typing import Optional

from .registry import get_registry, GateDefinition
from .result import GateContext, GateResult, GateStatus, BundleResult

# Ensure gates are registered
from . import definitions  # noqa: F401


class GateRunner:
    """Executes gates and produces results."""

    def __init__(self, store_root: Path):
        """Initialize the runner.

        Args:
            store_root: Path to the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.registry = get_registry()

    def run(
        self,
        gate_id_or_alias: str,
        batch_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        task_ids: Optional[list[str]] = None,
    ) -> GateResult:
        """Run a single gate.

        Args:
            gate_id_or_alias: Gate ID or alias.
            batch_id: Batch ID (if required by gate).
            snapshot_id: Snapshot ID (if required by gate).
            task_ids: Task IDs (if required by gate).

        Returns:
            GateResult with pass/fail and details.

        Raises:
            ValueError: If gate not found or missing required inputs.
        """
        gate = self.registry.get(gate_id_or_alias)
        if gate is None:
            suggestions = self.registry.suggest_similar(gate_id_or_alias)
            msg = f"Unknown gate: {gate_id_or_alias}"
            if suggestions:
                msg += f". Did you mean: {', '.join(suggestions)}?"
            raise ValueError(msg)

        # Build context with unique run ID
        run_id = str(uuid.uuid4())[:8]
        ctx = GateContext(
            store_root=self.store_root,
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            task_ids=task_ids,
            run_id=run_id,
        )

        # Validate required inputs
        missing = self.registry.validate_inputs(gate, ctx)
        if missing:
            raise ValueError(f"Gate '{gate.gate_id}' requires: {', '.join(missing)}")

        # Execute with timing
        start = time.perf_counter()
        try:
            result = gate.entrypoint(ctx)
        except Exception as e:
            result = GateResult(
                gate_id=gate.gate_id,
                passed=False,
                status=gate.status,
            )
            result.add_failure(
                message=f"Gate execution error: {e}",
                suggestion="Check gate implementation and inputs",
            )

        end = time.perf_counter()
        result.duration_ms = int((end - start) * 1000)
        result.status = gate.status
        result.context = ctx

        # Collect any artifacts written during gate execution
        artifact_dir = (
            self.store_root / "indexes" / "gate_artifacts" / gate.gate_id / run_id
        )
        if artifact_dir.exists():
            result.artifacts = [
                str(p.relative_to(self.store_root))
                for p in artifact_dir.iterdir()
                if p.is_file()
            ]

        return result

    def run_bundle(
        self,
        bundle_name: str,
        batch_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        task_ids: Optional[list[str]] = None,
        fail_fast: bool = False,
    ) -> BundleResult:
        """Run a bundle of gates.

        Args:
            bundle_name: Bundle name (e.g., 'phase3', 'release').
            batch_id: Batch ID.
            snapshot_id: Snapshot ID.
            task_ids: Task IDs.
            fail_fast: Stop on first failure.

        Returns:
            BundleResult with all gate results.
        """
        gates = self._get_bundle_gates(bundle_name)
        if not gates:
            raise ValueError(f"Unknown bundle or empty: {bundle_name}")

        results: list[GateResult] = []
        passed_count = 0
        failed_count = 0
        skipped_count = 0

        start = time.perf_counter()

        for gate in gates:
            # Skip PLACEHOLDER gates
            if gate.status == GateStatus.PLACEHOLDER:
                skipped_count += 1
                continue

            try:
                result = self.run(
                    gate.gate_id,
                    batch_id=batch_id,
                    snapshot_id=snapshot_id,
                    task_ids=task_ids,
                )
                results.append(result)

                if result.passed:
                    passed_count += 1
                else:
                    failed_count += 1
                    if fail_fast:
                        break

            except ValueError:
                # Missing inputs - skip this gate
                skipped_count += 1
                continue

        end = time.perf_counter()

        # Bundle passes if no ENFORCED gates failed
        enforced_failures = sum(
            1 for r in results if not r.passed and r.status == GateStatus.ENFORCED
        )
        bundle_passed = enforced_failures == 0

        return BundleResult(
            bundle_name=bundle_name,
            passed=bundle_passed,
            total=len(gates),
            passed_count=passed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            duration_ms=int((end - start) * 1000),
            results=results,
        )

    def _get_bundle_gates(self, bundle_name: str) -> list[GateDefinition]:
        """Get gates for a bundle.

        Args:
            bundle_name: Bundle name.

        Returns:
            List of gate definitions in execution order.
        """
        if bundle_name == "phase1":
            return self.registry.list_by_tag("phase1")
        elif bundle_name == "phase2":
            return self.registry.list_by_tag("phase2")
        elif bundle_name == "phase3":
            return self.registry.list_by_tag("phase3")
        elif bundle_name == "release":
            return self.registry.list_by_status(GateStatus.ENFORCED)
        elif bundle_name == "all":
            return self.registry.list_all()
        else:
            return []


def run_gate(
    store_root: Path,
    gate_id: str,
    batch_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    task_ids: Optional[list[str]] = None,
) -> GateResult:
    """Convenience function to run a single gate.

    Args:
        store_root: Path to store.
        gate_id: Gate ID or alias.
        batch_id: Batch ID.
        snapshot_id: Snapshot ID.
        task_ids: Task IDs.

    Returns:
        GateResult.
    """
    runner = GateRunner(store_root)
    return runner.run(gate_id, batch_id, snapshot_id, task_ids)


def run_bundle(
    store_root: Path,
    bundle_name: str,
    batch_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    task_ids: Optional[list[str]] = None,
    fail_fast: bool = False,
) -> BundleResult:
    """Convenience function to run a bundle.

    Args:
        store_root: Path to store.
        bundle_name: Bundle name.
        batch_id: Batch ID.
        snapshot_id: Snapshot ID.
        task_ids: Task IDs.
        fail_fast: Stop on first failure.

    Returns:
        BundleResult.
    """
    runner = GateRunner(store_root)
    return runner.run_bundle(bundle_name, batch_id, snapshot_id, task_ids, fail_fast)
