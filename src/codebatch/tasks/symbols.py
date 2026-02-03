"""Symbols task executor - extracts symbol tables and edges from AST.

Emits:
- kind=symbol: Per-file symbol definitions (functions, classes, variables)
- kind=edge: Import/reference relationships

Inputs:
- Parse outputs (kind=ast) via iter_prior_outputs

This task consumes AST from 01_parse and produces a compact symbol table.
Files without AST are skipped (no symbols emitted).
"""

import json
from typing import Iterable, Optional

from ..runner import ShardRunner


def extract_python_symbols(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols and edges from Python AST data.

    Args:
        ast_data: Parsed AST dict from parse task.
        path: Source file path.

    Returns:
        Tuple of (symbols, edges).
    """
    symbols = []
    edges = []

    # Get body nodes from summary AST
    body = ast_data.get("body", [])

    for node in body:
        node_type = node.get("type", "")
        lineno = node.get("lineno")
        col = node.get("col_offset", 0)

        # Function definitions
        if node_type == "FunctionDef" or node_type == "AsyncFunctionDef":
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": f"function_{lineno}",  # Name not in summary AST
                "symbol_type": "function",
                "line": lineno,
                "col": col,
                "scope": "module",
            })

        # Class definitions
        elif node_type == "ClassDef":
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": f"class_{lineno}",
                "symbol_type": "class",
                "line": lineno,
                "col": col,
                "scope": "module",
            })

        # Import statements -> edges
        elif node_type == "Import":
            edges.append({
                "kind": "edge",
                "path": path,
                "edge_type": "imports",
                "target": f"module_{lineno}",
                "line": lineno,
            })

        elif node_type == "ImportFrom":
            edges.append({
                "kind": "edge",
                "path": path,
                "edge_type": "imports",
                "target": f"from_module_{lineno}",
                "line": lineno,
            })

        # Assignments at module level (potential exports/constants)
        elif node_type == "Assign" or node_type == "AnnAssign":
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": f"variable_{lineno}",
                "symbol_type": "variable",
                "line": lineno,
                "col": col,
                "scope": "module",
            })

    return symbols, edges


def extract_js_symbols(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols from JavaScript/TypeScript token data.

    Since we only have token counts (not full AST), we provide basic counts.

    Args:
        ast_data: Token info dict from parse task.
        path: Source file path.

    Returns:
        Tuple of (symbols, edges).
    """
    symbols = []
    edges = []

    tokens = ast_data.get("tokens", {})

    # If we have functions, emit a summary symbol
    if tokens.get("keyword", 0) > 0:
        symbols.append({
            "kind": "symbol",
            "path": path,
            "name": "js_module",
            "symbol_type": "module",
            "line": 1,
            "col": 0,
            "scope": "file",
        })

    return symbols, edges


def extract_text_symbols(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract minimal info from text files.

    Text files don't have symbols in the traditional sense.

    Args:
        ast_data: Text info dict from parse task.
        path: Source file path.

    Returns:
        Empty lists (no symbols for text files).
    """
    return [], []


def symbols_executor(config: dict, files: Iterable[dict], runner: ShardRunner) -> list[dict]:
    """Execute the symbols task.

    Consumes AST outputs from 01_parse and produces symbol tables and edges.

    Args:
        config: Task configuration.
        files: Iterable of file records (used to get batch/task context).
        runner: ShardRunner for CAS and prior output access.

    Returns:
        List of symbol and edge output records.
    """
    outputs = []

    # Get context from config (set by runner during execution)
    batch_id = config.get("_batch_id")
    shard_id = config.get("_shard_id")

    if not batch_id or not shard_id:
        # Fallback: consume files to establish context
        file_list = list(files)
        if not file_list:
            return []
        # Can't get prior outputs without batch context
        # Return empty - this shouldn't happen in normal execution
        return []

    # Iterate over parse AST outputs for this shard
    for ast_output in runner.iter_prior_outputs(batch_id, "01_parse", shard_id, kind="ast"):
        path = ast_output.get("path")
        object_ref = ast_output.get("object")
        fmt = ast_output.get("format", "json")

        if not path or not object_ref:
            continue

        # Skip chunked ASTs for simplicity (Phase 2)
        if fmt == "json+chunks":
            continue

        try:
            # Load AST from CAS
            ast_bytes = runner.object_store.get_bytes(object_ref)
            ast_data = json.loads(ast_bytes.decode("utf-8"))

            # Extract based on AST type
            ast_type = ast_data.get("type", "")
            ast_mode = ast_data.get("ast_mode", "")

            symbols = []
            edges = []

            if ast_type == "Module" and ast_mode == "summary":
                # Python summary AST
                symbols, edges = extract_python_symbols(ast_data, path)
            elif ast_type == "TokenInfo":
                # JavaScript/TypeScript tokens
                symbols, edges = extract_js_symbols(ast_data, path)
            elif ast_type == "TextInfo":
                # Text file stats
                symbols, edges = extract_text_symbols(ast_data, path)

            outputs.extend(symbols)
            outputs.extend(edges)

        except Exception as e:
            # Emit diagnostic for failures
            outputs.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "SYMBOLS_EXTRACT_ERROR",
                "message": f"Failed to extract symbols: {e}",
                "line": 1,
            })

    return outputs
