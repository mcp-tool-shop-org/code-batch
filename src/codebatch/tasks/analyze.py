"""Analyze task executor - produces file-level metrics.

Emits:
- kind=metric: File-level metrics (bytes, loc, lang, parse_status, complexity)

Inputs:
- Snapshot file records for this shard
- Optionally parse outputs to determine parse_status and complexity

Metrics are stable and cheap - no deep analysis.

Phase 8: Added cyclomatic complexity from AST.
"""

import json
from typing import Iterable, Optional

from ..runner import ShardRunner


def count_lines(content: str) -> int:
    """Count lines of code (non-empty lines)."""
    lines = content.split("\n")
    return sum(1 for line in lines if line.strip())


def calculate_complexity_from_node(node: dict) -> int:
    """Calculate cyclomatic complexity contribution from a single AST node.

    Cyclomatic complexity counts:
    - +1 for each function/method (base)
    - +1 for each if/elif
    - +1 for each for/while loop
    - +1 for each except handler
    - +1 for each and/or in boolean expression
    - +1 for each assert/comprehension/ternary

    Args:
        node: AST node dict.

    Returns:
        Complexity contribution from this node.
    """
    node_type = node.get("type", "")
    complexity = 0

    # Decision points that increase complexity
    if node_type in ("If", "IfExp"):  # if and ternary
        complexity += 1
    elif node_type in ("For", "While", "AsyncFor"):
        complexity += 1
    elif node_type == "ExceptHandler":
        complexity += 1
    elif node_type == "Assert":
        complexity += 1
    elif node_type in ("ListComp", "SetComp", "DictComp", "GeneratorExp"):
        complexity += 1
    elif node_type == "BoolOp":
        # and/or - each adds a decision point
        # Number of operands - 1 = number of operators
        values = node.get("values", [])
        complexity += max(0, len(values) - 1)

    # Recurse into children
    for key in ("body", "orelse", "handlers", "finalbody", "values", "elts", "args"):
        children = node.get(key, [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    complexity += calculate_complexity_from_node(child)
        elif isinstance(children, dict):
            complexity += calculate_complexity_from_node(children)

    # Also check common single-child keys
    for key in ("value", "test", "func", "left", "right", "target", "iter", "slice"):
        child = node.get(key)
        if isinstance(child, dict):
            complexity += calculate_complexity_from_node(child)

    return complexity


def calculate_function_complexity(func_node: dict) -> int:
    """Calculate cyclomatic complexity of a function.

    Args:
        func_node: FunctionDef or AsyncFunctionDef AST node.

    Returns:
        Cyclomatic complexity (minimum 1).
    """
    # Base complexity is 1
    complexity = 1

    # Add complexity from body
    for child in func_node.get("body", []):
        if isinstance(child, dict):
            complexity += calculate_complexity_from_node(child)

    return complexity


def extract_complexity_metrics(ast_data: dict, path: str) -> list[dict]:
    """Extract complexity metrics from Python AST.

    Produces:
    - complexity: Total cyclomatic complexity
    - max_complexity: Maximum function complexity
    - function_count: Number of functions
    - class_count: Number of classes
    - import_count: Number of imports

    Args:
        ast_data: Parsed Python AST dict.
        path: Source file path.

    Returns:
        List of metric records.
    """
    metrics = []

    total_complexity = 0
    max_complexity = 0
    function_count = 0
    class_count = 0
    import_count = 0

    def process_node(node: dict) -> None:
        nonlocal \
            total_complexity, \
            max_complexity, \
            function_count, \
            class_count, \
            import_count

        node_type = node.get("type", "")

        # Function definition
        if node_type in ("FunctionDef", "AsyncFunctionDef"):
            function_count += 1
            func_complexity = calculate_function_complexity(node)
            total_complexity += func_complexity
            max_complexity = max(max_complexity, func_complexity)

            # Process nested functions/classes
            for child in node.get("body", []):
                if isinstance(child, dict):
                    process_node(child)
            return

        # Class definition
        if node_type == "ClassDef":
            class_count += 1
            # Process methods
            for child in node.get("body", []):
                if isinstance(child, dict):
                    process_node(child)
            return

        # Import
        if node_type == "Import":
            import_count += len(node.get("names", []))
        elif node_type == "ImportFrom":
            import_count += len(node.get("names", []))

    # Process all top-level nodes
    for node in ast_data.get("body", []):
        process_node(node)

    # Emit metrics
    metrics.append(
        {
            "kind": "metric",
            "path": path,
            "metric": "complexity",
            "value": total_complexity,
        }
    )

    metrics.append(
        {
            "kind": "metric",
            "path": path,
            "metric": "max_complexity",
            "value": max_complexity,
        }
    )

    metrics.append(
        {
            "kind": "metric",
            "path": path,
            "metric": "function_count",
            "value": function_count,
        }
    )

    metrics.append(
        {
            "kind": "metric",
            "path": path,
            "metric": "class_count",
            "value": class_count,
        }
    )

    metrics.append(
        {
            "kind": "metric",
            "path": path,
            "metric": "import_count",
            "value": import_count,
        }
    )

    return metrics


def analyze_executor(
    config: dict, files: Iterable[dict], runner: ShardRunner
) -> list[dict]:
    """Execute the analyze task.

    Produces file-level metrics for each file in the shard:
    - bytes: File size from snapshot
    - loc: Lines of code (non-empty lines, text files only)
    - lang: Language hint from snapshot
    - complexity: Cyclomatic complexity (Python only, from AST)
    - max_complexity: Maximum function complexity
    - function_count, class_count, import_count

    Args:
        config: Task configuration.
        files: Iterable of file records for this shard.
        runner: ShardRunner for CAS access.

    Returns:
        List of metric output records.
    """
    outputs = []

    # Get execution context for AST access
    batch_id = config.get("_batch_id")
    shard_id = config.get("_shard_id")

    # Materialize files for potential multi-pass
    file_list = list(files)

    # Track which files we've computed complexity for
    complexity_paths: set[str] = set()

    # First pass: Extract complexity metrics from AST (if available)
    if batch_id and shard_id:
        for ast_output in runner.iter_prior_outputs(
            batch_id, "01_parse", shard_id, kind="ast"
        ):
            path = ast_output.get("path")
            object_ref = ast_output.get("object")

            if not path or not object_ref or path in complexity_paths:
                continue

            # Skip chunked ASTs
            if ast_output.get("format") == "json+chunks":
                continue

            try:
                # Load AST
                ast_bytes = runner.object_store.get_bytes(object_ref)
                ast_data = json.loads(ast_bytes.decode("utf-8"))

                # Check if this is a Python AST
                ast_type = ast_data.get("type", "")
                ast_mode = ast_data.get("ast_mode", "")

                if ast_type == "Module" and ast_mode == "full":
                    # Extract complexity metrics
                    complexity_metrics = extract_complexity_metrics(ast_data, path)
                    outputs.extend(complexity_metrics)
                    complexity_paths.add(path)

            except Exception:
                # Skip complexity if AST can't be loaded
                pass

    # Second pass: Basic metrics for all files
    for file_record in file_list:
        path = file_record["path"]
        object_ref = file_record["object"]
        lang_hint = file_record.get("lang_hint", "unknown")

        try:
            # Get file content from CAS
            data = runner.object_store.get_bytes(object_ref)
            file_bytes = len(data)

            # Try to decode as text for LOC
            loc: Optional[int] = None
            try:
                content = data.decode("utf-8")
                loc = count_lines(content)
            except UnicodeDecodeError:
                # Binary file - no LOC
                pass

            # Emit bytes metric
            outputs.append(
                {
                    "kind": "metric",
                    "path": path,
                    "metric": "bytes",
                    "value": file_bytes,
                }
            )

            # Emit LOC metric (if text)
            if loc is not None:
                outputs.append(
                    {
                        "kind": "metric",
                        "path": path,
                        "metric": "loc",
                        "value": loc,
                    }
                )

            # Emit lang metric
            outputs.append(
                {
                    "kind": "metric",
                    "path": path,
                    "metric": "lang",
                    "value": lang_hint,
                }
            )

        except Exception as e:
            # Emit error metric
            outputs.append(
                {
                    "kind": "metric",
                    "path": path,
                    "metric": "error",
                    "value": str(e),
                }
            )

    return outputs
