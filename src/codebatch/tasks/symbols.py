"""Symbols task executor - extracts symbol tables and edges from AST.

Emits:
- kind=symbol: Per-file symbol definitions (functions, classes, variables)
- kind=edge: Import/reference relationships

Inputs:
- Parse outputs (kind=ast) via iter_prior_outputs

This task consumes AST from 01_parse and produces a compact symbol table.
Files without AST are skipped (no symbols emitted).

Phase 8: Full symbol extraction with real names from full-fidelity AST.
"""

import json
from typing import Any, Iterable, Optional

from ..runner import ShardRunner


def _extract_name_from_target(target: dict) -> Optional[str]:
    """Extract variable name from an assignment target.

    Args:
        target: AST node dict for assignment target.

    Returns:
        Variable name if extractable, None otherwise.
    """
    node_type = target.get("type", "")

    if node_type == "Name":
        return target.get("id")
    elif node_type == "Attribute":
        # For self.x = ..., we could return "x" but skip for now
        return None
    elif node_type == "Tuple" or node_type == "List":
        # Multiple assignment - skip for now
        return None

    return None


def _extract_symbols_from_node(
    node: dict,
    path: str,
    scope: str,
    symbols: list[dict],
    edges: list[dict],
) -> None:
    """Recursively extract symbols from an AST node.

    Args:
        node: AST node dict.
        path: Source file path.
        scope: Current scope name (e.g., "module", "ClassName", "function_name").
        symbols: List to append symbol records to.
        edges: List to append edge records to.
    """
    node_type = node.get("type", "")
    lineno = node.get("lineno")
    col = node.get("col_offset", 0)

    # Function definitions
    if node_type in ("FunctionDef", "AsyncFunctionDef"):
        name = node.get("name")
        if name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": name,
                "symbol_type": "function",
                "line": lineno,
                "col": col,
                "scope": scope,
            })

            # Extract parameters as symbols
            args = node.get("args", {})
            for arg_info in args.get("args", []):
                arg_name = arg_info.get("arg")
                if arg_name and arg_name != "self" and arg_name != "cls":
                    symbols.append({
                        "kind": "symbol",
                        "path": path,
                        "name": arg_name,
                        "symbol_type": "parameter",
                        "line": lineno,
                        "col": col,
                        "scope": name,
                    })

            # Recurse into function body with new scope
            for child in node.get("body", []):
                _extract_symbols_from_node(child, path, name, symbols, edges)

    # Class definitions
    elif node_type == "ClassDef":
        name = node.get("name")
        if name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": name,
                "symbol_type": "class",
                "line": lineno,
                "col": col,
                "scope": scope,
            })

            # Extract base classes as edges
            for base in node.get("bases", []):
                base_name = None
                if base.get("type") == "Name":
                    base_name = base.get("id")
                elif base.get("type") == "Attribute":
                    base_name = base.get("attr")

                if base_name:
                    edges.append({
                        "kind": "edge",
                        "path": path,
                        "edge_type": "inherits",
                        "target": base_name,
                        "line": lineno,
                    })

            # Recurse into class body with class as scope
            for child in node.get("body", []):
                _extract_symbols_from_node(child, path, name, symbols, edges)

    # Import statements
    elif node_type == "Import":
        for name_info in node.get("names", []):
            module_name = name_info.get("name")
            alias = name_info.get("asname")
            if module_name:
                edges.append({
                    "kind": "edge",
                    "path": path,
                    "edge_type": "imports",
                    "target": module_name,
                    "line": lineno,
                })
                # If aliased, also create a symbol for the alias
                if alias:
                    symbols.append({
                        "kind": "symbol",
                        "path": path,
                        "name": alias,
                        "symbol_type": "import_alias",
                        "line": lineno,
                        "col": col,
                        "scope": scope,
                    })

    elif node_type == "ImportFrom":
        module = node.get("module") or ""
        for name_info in node.get("names", []):
            import_name = name_info.get("name")
            alias = name_info.get("asname")
            if import_name:
                full_target = f"{module}.{import_name}" if module else import_name
                edges.append({
                    "kind": "edge",
                    "path": path,
                    "edge_type": "imports",
                    "target": full_target,
                    "line": lineno,
                })
                # If aliased, create symbol for alias
                if alias:
                    symbols.append({
                        "kind": "symbol",
                        "path": path,
                        "name": alias,
                        "symbol_type": "import_alias",
                        "line": lineno,
                        "col": col,
                        "scope": scope,
                    })

    # Assignments
    elif node_type == "Assign":
        for target in node.get("targets", []):
            var_name = _extract_name_from_target(target)
            if var_name:
                symbols.append({
                    "kind": "symbol",
                    "path": path,
                    "name": var_name,
                    "symbol_type": "variable",
                    "line": lineno,
                    "col": col,
                    "scope": scope,
                })

    elif node_type == "AnnAssign":
        target = node.get("target")
        if target:
            var_name = _extract_name_from_target(target)
            if var_name:
                symbols.append({
                    "kind": "symbol",
                    "path": path,
                    "name": var_name,
                    "symbol_type": "variable",
                    "line": lineno,
                    "col": col,
                    "scope": scope,
                })

    # For/While/If/With - recurse into body and orelse
    elif node_type in ("For", "While", "If", "With", "AsyncFor", "AsyncWith"):
        for child in node.get("body", []):
            _extract_symbols_from_node(child, path, scope, symbols, edges)
        for child in node.get("orelse", []):
            _extract_symbols_from_node(child, path, scope, symbols, edges)

    # Try/Except
    elif node_type == "Try":
        for child in node.get("body", []):
            _extract_symbols_from_node(child, path, scope, symbols, edges)
        for handler in node.get("handlers", []):
            _extract_symbols_from_node(handler, path, scope, symbols, edges)
        for child in node.get("orelse", []):
            _extract_symbols_from_node(child, path, scope, symbols, edges)

    # ExceptHandler
    elif node_type == "ExceptHandler":
        # Exception variable (e.g., `except ValueError as e:`)
        exc_name = node.get("name")
        if exc_name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": exc_name,
                "symbol_type": "variable",
                "line": lineno,
                "col": col,
                "scope": scope,
            })
        for child in node.get("body", []):
            _extract_symbols_from_node(child, path, scope, symbols, edges)


def extract_python_symbols(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols and edges from Python AST data.

    Phase 8: Full extraction with real names from full-fidelity AST.

    Args:
        ast_data: Parsed AST dict from parse task.
        path: Source file path.

    Returns:
        Tuple of (symbols, edges).
    """
    symbols: list[dict] = []
    edges: list[dict] = []

    # Get body nodes from AST
    body = ast_data.get("body", [])

    # Process each top-level node
    for node in body:
        _extract_symbols_from_node(node, path, "module", symbols, edges)

    return symbols, edges


def _extract_js_symbols_from_node(
    node: dict,
    path: str,
    scope: str,
    symbols: list[dict],
    edges: list[dict],
) -> None:
    """Recursively extract symbols from a tree-sitter JS/TS AST node.

    Args:
        node: Tree-sitter AST node dict.
        path: Source file path.
        scope: Current scope name.
        symbols: List to append symbol records to.
        edges: List to append edge records to.
    """
    node_type = node.get("type", "")
    start_point = node.get("start_point", {})
    lineno = start_point.get("row", 0) + 1  # tree-sitter is 0-indexed
    col = start_point.get("column", 0)

    # Function declarations
    if node_type == "function_declaration":
        name = node.get("name")
        if name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": name,
                "symbol_type": "function",
                "line": lineno,
                "col": col,
                "scope": scope,
            })
            # Recurse into function body with new scope
            for child in node.get("children", []):
                _extract_js_symbols_from_node(child, path, name, symbols, edges)
            return  # Don't recurse again

    # Arrow functions (when assigned to const/let/var)
    # These are handled via variable_declarator

    # Method definitions (inside classes)
    if node_type == "method_definition":
        name = node.get("name")
        if name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": name,
                "symbol_type": "function",
                "line": lineno,
                "col": col,
                "scope": scope,
            })
            for child in node.get("children", []):
                _extract_js_symbols_from_node(child, path, name, symbols, edges)
            return

    # Class declarations
    if node_type == "class_declaration":
        name = node.get("name")
        # For TypeScript, class name may be in type_identifier child
        if not name:
            for child in node.get("children", []):
                if child.get("type") in ("identifier", "type_identifier"):
                    name = child.get("name")
                    break
        if name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": name,
                "symbol_type": "class",
                "line": lineno,
                "col": col,
                "scope": scope,
            })
            # Look for extends clause
            for child in node.get("children", []):
                if child.get("type") == "class_heritage":
                    # Find the extended class name
                    for heritage_child in child.get("children", []):
                        if heritage_child.get("type") in ("identifier", "type_identifier"):
                            base_name = heritage_child.get("name")
                            if base_name:
                                edges.append({
                                    "kind": "edge",
                                    "path": path,
                                    "edge_type": "inherits",
                                    "target": base_name,
                                    "line": lineno,
                                })
            # Recurse with class as scope
            for child in node.get("children", []):
                _extract_js_symbols_from_node(child, path, name, symbols, edges)
            return

    # Variable declarations (const, let, var)
    if node_type == "variable_declarator":
        name = node.get("name")
        if name:
            symbols.append({
                "kind": "symbol",
                "path": path,
                "name": name,
                "symbol_type": "variable",
                "line": lineno,
                "col": col,
                "scope": scope,
            })

    # Import statements
    if node_type == "import_statement":
        source = node.get("source")
        if source:
            edges.append({
                "kind": "edge",
                "path": path,
                "edge_type": "imports",
                "target": source,
                "line": lineno,
            })
        # Extract imported identifiers
        for child in node.get("children", []):
            if child.get("type") == "import_clause":
                _extract_import_identifiers(child, path, scope, symbols, lineno, col)
            elif child.get("type") == "named_imports":
                _extract_import_identifiers(child, path, scope, symbols, lineno, col)

    # Export statements
    if node_type == "export_statement":
        # Look for default export or named exports
        for child in node.get("children", []):
            child_type = child.get("type")
            if child_type in ("function_declaration", "class_declaration"):
                _extract_js_symbols_from_node(child, path, scope, symbols, edges)
            elif child_type == "export_clause":
                # Named exports
                for export_child in child.get("children", []):
                    if export_child.get("type") == "export_specifier":
                        export_name = export_child.get("name")
                        if export_name:
                            edges.append({
                                "kind": "edge",
                                "path": path,
                                "edge_type": "exports",
                                "target": export_name,
                                "line": lineno,
                            })
        return  # Handled above

    # Recurse into children by default
    for child in node.get("children", []):
        _extract_js_symbols_from_node(child, path, scope, symbols, edges)


def _extract_import_identifiers(
    node: dict,
    path: str,
    scope: str,
    symbols: list[dict],
    lineno: int,
    col: int,
) -> None:
    """Extract imported identifiers from import clause.

    Args:
        node: Import clause or named_imports node.
        path: Source file path.
        scope: Current scope.
        symbols: List to append symbols to.
        lineno: Line number.
        col: Column offset.
    """
    for child in node.get("children", []):
        child_type = child.get("type")
        if child_type == "identifier":
            name = child.get("name")
            if name:
                symbols.append({
                    "kind": "symbol",
                    "path": path,
                    "name": name,
                    "symbol_type": "import_alias",
                    "line": lineno,
                    "col": col,
                    "scope": scope,
                })
        elif child_type == "import_specifier":
            # { foo as bar }
            name = child.get("name")
            if name:
                symbols.append({
                    "kind": "symbol",
                    "path": path,
                    "name": name,
                    "symbol_type": "import_alias",
                    "line": lineno,
                    "col": col,
                    "scope": scope,
                })
        elif child_type == "named_imports":
            _extract_import_identifiers(child, path, scope, symbols, lineno, col)


def extract_js_symbols_treesitter(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols from tree-sitter JavaScript/TypeScript AST.

    Args:
        ast_data: Tree-sitter AST dict from parse task.
        path: Source file path.

    Returns:
        Tuple of (symbols, edges).
    """
    symbols: list[dict] = []
    edges: list[dict] = []

    # Process top-level children
    for child in ast_data.get("children", []):
        _extract_js_symbols_from_node(child, path, "module", symbols, edges)

    return symbols, edges


def extract_js_symbols_fallback(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols from fallback JavaScript/TypeScript token data.

    Since we only have token counts (not full AST), we provide basic info.

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


def extract_js_symbols(ast_data: dict, path: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols from JavaScript/TypeScript AST or token data.

    Handles both tree-sitter full AST and fallback token modes.

    Args:
        ast_data: AST or token info dict from parse task.
        path: Source file path.

    Returns:
        Tuple of (symbols, edges).
    """
    ast_mode = ast_data.get("ast_mode", "")
    parser = ast_data.get("parser", "")

    if ast_mode == "full" and parser == "tree-sitter":
        return extract_js_symbols_treesitter(ast_data, path)
    else:
        return extract_js_symbols_fallback(ast_data, path)


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
            parser = ast_data.get("parser", "")

            symbols = []
            edges = []

            if ast_type == "Module" and ast_mode in ("full", "summary"):
                # Python AST (full or legacy summary mode)
                symbols, edges = extract_python_symbols(ast_data, path)
            elif ast_type == "program" and parser == "tree-sitter":
                # Tree-sitter JavaScript/TypeScript AST
                symbols, edges = extract_js_symbols(ast_data, path)
            elif ast_type == "TokenInfo":
                # JavaScript/TypeScript fallback tokens
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
