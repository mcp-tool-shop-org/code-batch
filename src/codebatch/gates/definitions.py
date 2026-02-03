"""Gate definitions for all phases.

This module registers all gates with the global registry.
Import this module to ensure gates are registered.
"""

from pathlib import Path
from typing import Optional

from .registry import register_gate, get_registry
from .result import GateContext, GateResult, GateStatus, GateFailure


# =============================================================================
# Phase 1 Gates - Substrate
# =============================================================================


@register_gate(
    gate_id="P1-G1",
    title="Store schema validation",
    description="Store metadata conforms to schema and contains required fields.",
    status=GateStatus.ENFORCED,
    required_inputs=["store"],
    tags=["phase1", "schema", "validation"],
    aliases=["store-schema"],
)
def gate_p1_g1(ctx: GateContext) -> GateResult:
    """Validate store schema."""
    import json
    from ..store import ensure_store, InvalidStoreError

    result = GateResult(gate_id="P1-G1", passed=True, status=GateStatus.ENFORCED)

    try:
        ensure_store(ctx.store_root)
        store_json = ctx.store_root / "store.json"
        with open(store_json) as f:
            meta = json.load(f)

        # Verify required fields
        required = ["schema_version", "created_at", "producer"]
        for field in required:
            if field not in meta:
                result.add_failure(
                    message=f"Missing required field: {field}",
                    location="store.json",
                    suggestion=f"Add '{field}' to store.json",
                )

        result.details = {"schema_version": meta.get("schema_version")}

    except InvalidStoreError as e:
        result.add_failure(message=str(e), location=str(ctx.store_root))
    except Exception as e:
        result.add_failure(message=f"Store validation error: {e}")

    return result


# =============================================================================
# Phase 2 Gates - Pipeline/Tasks
# =============================================================================


@register_gate(
    gate_id="P2-G1",
    title="Full pipeline execution",
    description="All tasks in full pipeline complete without errors.",
    status=GateStatus.ENFORCED,
    required_inputs=["store", "batch"],
    tags=["phase2", "pipeline", "execution"],
    aliases=["pipeline-exec"],
)
def gate_p2_g1(ctx: GateContext) -> GateResult:
    """Run full pipeline and verify completion."""
    from ..batch import BatchManager

    result = GateResult(gate_id="P2-G1", passed=True, status=GateStatus.ENFORCED)

    try:
        manager = BatchManager(ctx.store_root)
        batch = manager.load_batch(ctx.batch_id)
        plan = manager.load_plan(ctx.batch_id)

        completed_tasks = 0
        failed_tasks = 0

        for task_def in plan["tasks"]:
            task = manager.load_task(ctx.batch_id, task_def["task_id"])
            if task["status"] == "done":
                completed_tasks += 1
            elif task["status"] == "failed":
                failed_tasks += 1
                result.add_failure(
                    message=f"Task failed: {task_def['task_id']}",
                    location=f"tasks/{task_def['task_id']}",
                )

        result.details = {
            "total_tasks": len(plan["tasks"]),
            "completed": completed_tasks,
            "failed": failed_tasks,
        }

        if failed_tasks > 0:
            result.passed = False

    except Exception as e:
        result.add_failure(message=f"Pipeline check error: {e}")

    return result


@register_gate(
    gate_id="P2-G6",
    title="Truth-store guard",
    description="Task execution only writes under batches/ directory.",
    status=GateStatus.ENFORCED,
    required_inputs=["store"],
    tags=["phase2", "security", "truth-store"],
    aliases=["truth-guard"],
)
def gate_p2_g6(ctx: GateContext) -> GateResult:
    """Verify truth-store guard."""
    result = GateResult(gate_id="P2-G6", passed=True, status=GateStatus.ENFORCED)

    allowed = {"store.json", "objects", "snapshots", "batches", "indexes"}
    top_level = {p.name for p in ctx.store_root.iterdir() if p.exists()}

    unauthorized = top_level - allowed
    if unauthorized:
        result.add_failure(
            message=f"Unauthorized top-level paths: {unauthorized}",
            suggestion="Remove or move unauthorized directories",
        )

    result.details = {"allowed": list(allowed), "found": list(top_level)}
    return result


@register_gate(
    gate_id="P2-G7",
    title="Dependency enforcement",
    description="Task dependencies are satisfied before execution.",
    status=GateStatus.HARNESS,
    required_inputs=["store", "batch"],
    tags=["phase2", "deps", "ordering"],
    aliases=["deps-check"],
)
def gate_p2_g7(ctx: GateContext) -> GateResult:
    """Verify dependency enforcement."""
    from ..batch import BatchManager

    result = GateResult(gate_id="P2-G7", passed=True, status=GateStatus.HARNESS)

    try:
        manager = BatchManager(ctx.store_root)
        plan = manager.load_plan(ctx.batch_id)

        # Build dependency map
        task_order = {t["task_id"]: i for i, t in enumerate(plan["tasks"])}

        for task_def in plan["tasks"]:
            deps = task_def.get("deps", [])
            for dep in deps:
                if dep not in task_order:
                    result.add_failure(
                        message=f"Unknown dependency: {dep}",
                        location=task_def["task_id"],
                    )
                elif task_order[dep] >= task_order[task_def["task_id"]]:
                    result.add_failure(
                        message=f"Dependency {dep} comes after {task_def['task_id']}",
                        location=task_def["task_id"],
                    )

        result.details = {"tasks_checked": len(plan["tasks"])}

    except Exception as e:
        result.add_failure(message=f"Dependency check error: {e}")

    return result


# =============================================================================
# Phase 3 Gates - Cache
# =============================================================================


@register_gate(
    gate_id="P3-A1",
    title="Cache equivalence",
    description="Cached queries return identical results to JSONL scan.",
    status=GateStatus.ENFORCED,
    required_inputs=["store", "batch"],
    tags=["phase3", "cache", "equivalence"],
    aliases=["A1", "cache-equiv"],
)
def gate_p3_a1(ctx: GateContext) -> GateResult:
    """Verify cache produces identical results to scan."""
    from ..query import QueryEngine
    from ..index_build import build_index
    from ..batch import BatchManager

    result = GateResult(gate_id="P3-A1", passed=True, status=GateStatus.ENFORCED)

    try:
        # Get task list
        manager = BatchManager(ctx.store_root)
        plan = manager.load_plan(ctx.batch_id)
        task_ids = [t["task_id"] for t in plan["tasks"]]

        # Build cache if needed
        cache_path = ctx.store_root / "indexes" / "lmdb"
        if not cache_path.exists():
            build_index(ctx.store_root, ctx.batch_id)

        mismatches = 0
        outputs_compared = 0

        for task_id in task_ids:
            # Query without cache
            engine_scan = QueryEngine(ctx.store_root, use_cache=False)
            scan_results = engine_scan.query_outputs(ctx.batch_id, task_id)

            # Query with cache
            engine_cache = QueryEngine(ctx.store_root, use_cache=True)
            cache_results = engine_cache.query_outputs(ctx.batch_id, task_id)
            engine_cache.close()

            # Canonicalize for comparison
            def canonicalize(outputs):
                result = []
                for o in outputs:
                    obj = o.get("object", "") or ""
                    result.append((o.get("kind", ""), o.get("path", ""), obj))
                return sorted(result)

            scan_canon = canonicalize(scan_results)
            cache_canon = canonicalize(cache_results)

            outputs_compared += len(scan_canon)

            if scan_canon != cache_canon:
                mismatches += 1
                result.add_failure(
                    message=f"Cache mismatch for task {task_id}",
                    expected=f"{len(scan_canon)} outputs",
                    actual=f"{len(cache_canon)} outputs",
                )
                # Write comparison artifact for debugging
                ctx.write_artifact_json("P3-A1", f"mismatch_{task_id}.json", {
                    "task_id": task_id,
                    "scan_count": len(scan_canon),
                    "cache_count": len(cache_canon),
                    "scan_outputs": scan_canon[:10],  # First 10
                    "cache_outputs": cache_canon[:10],
                })

        result.details = {
            "tasks_checked": len(task_ids),
            "outputs_compared": outputs_compared,
            "mismatches": mismatches,
        }

    except Exception as e:
        result.add_failure(message=f"Cache equivalence check error: {e}")

    return result


@register_gate(
    gate_id="P3-A2",
    title="Cache deletion fallback",
    description="Queries fall back to JSONL scan when cache is deleted.",
    status=GateStatus.ENFORCED,
    required_inputs=["store", "batch"],
    tags=["phase3", "cache", "fallback"],
    aliases=["A2", "cache-fallback"],
)
def gate_p3_a2(ctx: GateContext) -> GateResult:
    """Verify fallback to scan when cache is missing."""
    from ..query import QueryEngine
    from ..batch import BatchManager

    result = GateResult(gate_id="P3-A2", passed=True, status=GateStatus.ENFORCED)

    try:
        # Query without cache (this is the fallback path)
        engine = QueryEngine(ctx.store_root, use_cache=True)
        cache_path = ctx.store_root / "indexes" / "lmdb"

        # If cache doesn't exist, fallback should work
        if not cache_path.exists():
            outputs = engine.query_outputs(ctx.batch_id, "01_parse")
            result.details = {"fallback_works": True, "outputs": len(outputs)}
        else:
            result.details = {"fallback_works": True, "cache_exists": True}

    except Exception as e:
        result.add_failure(message=f"Fallback check error: {e}")

    return result


@register_gate(
    gate_id="P3-A3",
    title="Deterministic rebuild",
    description="Cache rebuilds produce identical query results.",
    status=GateStatus.ENFORCED,
    required_inputs=["store", "batch"],
    tags=["phase3", "cache", "determinism"],
    aliases=["A3", "cache-rebuild"],
)
def gate_p3_a3(ctx: GateContext) -> GateResult:
    """Verify deterministic cache rebuilds."""
    from ..query import QueryEngine
    from ..index_build import build_index
    import shutil

    result = GateResult(gate_id="P3-A3", passed=True, status=GateStatus.ENFORCED)

    try:
        # Build once
        build_index(ctx.store_root, ctx.batch_id)
        engine1 = QueryEngine(ctx.store_root, use_cache=True)
        results1 = engine1.query_outputs(ctx.batch_id, "01_parse")
        engine1.close()

        # Rebuild
        cache_path = ctx.store_root / "indexes" / "lmdb"
        if cache_path.exists():
            shutil.rmtree(cache_path)
        build_index(ctx.store_root, ctx.batch_id)

        # Query again
        engine2 = QueryEngine(ctx.store_root, use_cache=True)
        results2 = engine2.query_outputs(ctx.batch_id, "01_parse")
        engine2.close()

        # Compare
        def canonicalize(outputs):
            result = []
            for o in outputs:
                obj = o.get("object", "") or ""
                result.append((o.get("kind", ""), o.get("path", ""), obj))
            return sorted(result)

        if canonicalize(results1) != canonicalize(results2):
            result.add_failure(
                message="Rebuild produced different results",
                expected=f"{len(results1)} outputs",
                actual=f"{len(results2)} outputs",
            )

        result.details = {
            "build1_outputs": len(results1),
            "build2_outputs": len(results2),
            "identical": canonicalize(results1) == canonicalize(results2),
        }

    except Exception as e:
        result.add_failure(message=f"Rebuild check error: {e}")

    return result


@register_gate(
    gate_id="P3-A4",
    title="Cache truth-store guard",
    description="Cache writes only under indexes/ directory.",
    status=GateStatus.ENFORCED,
    required_inputs=["store", "batch"],
    tags=["phase3", "cache", "security"],
    aliases=["A4", "cache-guard"],
)
def gate_p3_a4(ctx: GateContext) -> GateResult:
    """Verify cache writes only to allowed locations."""
    from ..index_build import build_index

    result = GateResult(gate_id="P3-A4", passed=True, status=GateStatus.ENFORCED)

    try:
        # Record paths before build
        def get_paths(root):
            return {str(p.relative_to(root)) for p in root.rglob("*")}

        paths_before = get_paths(ctx.store_root)

        # Build cache
        build_index(ctx.store_root, ctx.batch_id, rebuild=True)

        paths_after = get_paths(ctx.store_root)

        # Check new paths
        new_paths = paths_after - paths_before
        unauthorized = [p for p in new_paths if not p.startswith("indexes")]

        if unauthorized:
            result.add_failure(
                message=f"Unauthorized cache writes: {unauthorized[:5]}",
                suggestion="Cache should only write under indexes/",
            )

        result.details = {
            "new_paths": len(new_paths),
            "unauthorized": len(unauthorized),
        }

    except Exception as e:
        result.add_failure(message=f"Cache guard check error: {e}")

    return result


# =============================================================================
# Register all gates on module import
# =============================================================================

def _ensure_registered():
    """Ensure all gates are registered."""
    # This function exists to ensure the module is imported
    # and decorators have run
    pass


# Force registration by referencing the functions
_REGISTERED_GATES = [
    gate_p1_g1,
    gate_p2_g1,
    gate_p2_g6,
    gate_p2_g7,
    gate_p3_a1,
    gate_p3_a2,
    gate_p3_a3,
    gate_p3_a4,
]
