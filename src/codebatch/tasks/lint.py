"""Lint task executor - rule-based diagnostics.

Emits:
- kind=diagnostic: Lint warnings/errors with severity, code, message, location

Inputs:
- Parse outputs (kind=ast) via iter_prior_outputs (preferred)
- Falls back to raw file content for simple text rules

Rules (Phase 2 minimal set - text-based):
- L001: Trailing whitespace
- L002: Line too long (>120 chars)
- L003: TODO/FIXME presence
- L004: Tab indentation (prefer spaces)
- L005: Missing newline at end of file

Rules (Phase 8 - AST-aware):
- L101: Unused import
- L102: Unused variable
- L103: Variable shadowing
"""

import json
from typing import Iterable

from ..runner import ShardRunner


# Rule configuration
DEFAULT_MAX_LINE_LENGTH = 120
TODO_PATTERNS = ["TODO", "FIXME", "XXX", "HACK"]

# Built-in names that should not be flagged as undefined
PYTHON_BUILTINS = {
    "abs",
    "all",
    "any",
    "ascii",
    "bin",
    "bool",
    "breakpoint",
    "bytearray",
    "bytes",
    "callable",
    "chr",
    "classmethod",
    "compile",
    "complex",
    "delattr",
    "dict",
    "dir",
    "divmod",
    "enumerate",
    "eval",
    "exec",
    "filter",
    "float",
    "format",
    "frozenset",
    "getattr",
    "globals",
    "hasattr",
    "hash",
    "help",
    "hex",
    "id",
    "input",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "locals",
    "map",
    "max",
    "memoryview",
    "min",
    "next",
    "object",
    "oct",
    "open",
    "ord",
    "pow",
    "print",
    "property",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "setattr",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "sum",
    "super",
    "tuple",
    "type",
    "vars",
    "zip",
    "__import__",
    "__name__",
    "__doc__",
    "__package__",
    "__loader__",
    "__spec__",
    "__annotations__",
    "__builtins__",
    "__file__",
    "__cached__",
    "None",
    "True",
    "False",
    "Ellipsis",
    "NotImplemented",
    "Exception",
    "BaseException",
    "TypeError",
    "ValueError",
    "KeyError",
    "IndexError",
    "AttributeError",
    "ImportError",
    "RuntimeError",
    "StopIteration",
    "GeneratorExit",
    "AssertionError",
    "NameError",
    "ZeroDivisionError",
    "OSError",
    "IOError",
    "FileNotFoundError",
    "PermissionError",
    "TimeoutError",
    "ConnectionError",
    "BrokenPipeError",
    "OverflowError",
    "RecursionError",
    "MemoryError",
    "SystemError",
    "SyntaxError",
    "IndentationError",
    "TabError",
    "UnicodeError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "Warning",
    "UserWarning",
    "DeprecationWarning",
    "PendingDeprecationWarning",
    "RuntimeWarning",
    "SyntaxWarning",
    "ResourceWarning",
    "FutureWarning",
    "ImportWarning",
    "UnicodeWarning",
    "BytesWarning",
    "EncodingWarning",
}


def lint_trailing_whitespace(lines: list[str], path: str) -> list[dict]:
    """L001: Detect trailing whitespace."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        # Don't strip newline, just check for trailing spaces/tabs before it
        stripped = line.rstrip("\n\r")
        if stripped != stripped.rstrip():
            diagnostics.append(
                {
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "warning",
                    "code": "L001",
                    "message": "Trailing whitespace",
                    "line": i,
                    "col": len(stripped.rstrip()) + 1,
                }
            )
    return diagnostics


def lint_line_too_long(
    lines: list[str], path: str, max_length: int = DEFAULT_MAX_LINE_LENGTH
) -> list[dict]:
    """L002: Detect lines exceeding max length."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\n\r")
        if len(stripped) > max_length:
            diagnostics.append(
                {
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "warning",
                    "code": "L002",
                    "message": f"Line too long ({len(stripped)} > {max_length})",
                    "line": i,
                    "col": max_length + 1,
                }
            )
    return diagnostics


def lint_todo_fixme(lines: list[str], path: str) -> list[dict]:
    """L003: Detect TODO/FIXME/XXX/HACK comments."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        upper_line = line.upper()
        for pattern in TODO_PATTERNS:
            if pattern in upper_line:
                col = line.upper().find(pattern) + 1
                diagnostics.append(
                    {
                        "kind": "diagnostic",
                        "path": path,
                        "severity": "info",
                        "code": "L003",
                        "message": f"Found {pattern} comment",
                        "line": i,
                        "col": col,
                    }
                )
                break  # Only report once per line
    return diagnostics


def lint_tab_indentation(lines: list[str], path: str) -> list[dict]:
    """L004: Detect tab indentation (prefer spaces)."""
    diagnostics = []
    for i, line in enumerate(lines, 1):
        if line.startswith("\t"):
            diagnostics.append(
                {
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "warning",
                    "code": "L004",
                    "message": "Tab indentation (prefer spaces)",
                    "line": i,
                    "col": 1,
                }
            )
    return diagnostics


def lint_missing_final_newline(content: str, path: str) -> list[dict]:
    """L005: Detect missing newline at end of file."""
    diagnostics = []
    if content and not content.endswith("\n"):
        lines = content.split("\n")
        diagnostics.append(
            {
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "L005",
                "message": "Missing newline at end of file",
                "line": len(lines),
                "col": len(lines[-1]) + 1 if lines else 1,
            }
        )
    return diagnostics


def lint_content(content: str, path: str, config: dict) -> list[dict]:
    """Run all lint rules on content.

    Args:
        content: File content as string.
        path: File path.
        config: Lint configuration.

    Returns:
        List of diagnostic records.
    """
    diagnostics = []
    lines = content.split("\n")

    # Get config options
    max_line_length = config.get("max_line_length", DEFAULT_MAX_LINE_LENGTH)
    check_trailing = config.get("check_trailing_whitespace", True)
    check_line_length = config.get("check_line_length", True)
    check_todo = config.get("check_todo", True)
    check_tabs = config.get("check_tab_indentation", True)
    check_final_newline = config.get("check_final_newline", True)

    if check_trailing:
        diagnostics.extend(lint_trailing_whitespace(lines, path))

    if check_line_length:
        diagnostics.extend(lint_line_too_long(lines, path, max_line_length))

    if check_todo:
        diagnostics.extend(lint_todo_fixme(lines, path))

    if check_tabs:
        diagnostics.extend(lint_tab_indentation(lines, path))

    if check_final_newline:
        diagnostics.extend(lint_missing_final_newline(content, path))

    return diagnostics


# =============================================================================
# AST-aware lint rules (Phase 8)
# =============================================================================


def _collect_names_from_node(
    node: dict, names: set[str], scope: str = "module", in_target: bool = False
) -> None:
    """Recursively collect all Name references from AST node.

    Args:
        node: AST node dict.
        names: Set to add referenced names to.
        scope: Current scope (for context).
        in_target: Whether we're inside an assignment target (don't collect these as uses).
    """
    node_type = node.get("type", "")

    # Name node - this is a reference to a name
    # But NOT if we're in an assignment target (those are definitions, not uses)
    if node_type == "Name" and not in_target:
        name_id = node.get("id")
        if name_id:
            names.add(name_id)

    # Attribute access - the base could be a name
    if node_type == "Attribute":
        # Recurse into value (the object being accessed)
        value = node.get("value")
        if value:
            _collect_names_from_node(value, names, scope, in_target)

    # Assignment - targets are definitions, values are uses
    if node_type == "Assign":
        # Collect names from value (right side) - these are uses
        value = node.get("value")
        if value:
            _collect_names_from_node(value, names, scope, in_target=False)
        # Don't recurse into targets - those are definitions
        return

    # Annotated assignment
    if node_type == "AnnAssign":
        # Annotation contains type references (uses)
        annotation = node.get("annotation")
        if annotation:
            _collect_names_from_node(annotation, names, scope, in_target=False)
        # Value is a use
        value = node.get("value")
        if value:
            _collect_names_from_node(value, names, scope, in_target=False)
        # Target is a definition - don't recurse
        return

    # Augmented assignment (x += 1) - the target is both read and written
    if node_type == "AugAssign":
        target = node.get("target")
        if target:
            _collect_names_from_node(target, names, scope, in_target=False)  # Read
        value = node.get("value")
        if value:
            _collect_names_from_node(value, names, scope, in_target=False)
        return

    # Function definitions - collect names from annotations
    if node_type in ("FunctionDef", "AsyncFunctionDef"):
        # Return annotation
        returns = node.get("returns")
        if returns:
            _collect_names_from_node(returns, names, scope, in_target=False)
        # Argument annotations
        args_info = node.get("args", {})
        for arg_info in args_info.get("args", []):
            annotation = arg_info.get("annotation")
            if annotation:
                _collect_names_from_node(annotation, names, scope, in_target=False)
        # Decorators
        for decorator in node.get("decorators", []):
            _collect_names_from_node(decorator, names, scope, in_target=False)
        # Recurse into body
        for child in node.get("body", []):
            if isinstance(child, dict):
                _collect_names_from_node(child, names, scope, in_target=False)
        return  # Don't recurse further - we handled it

    # For loop - target is a definition, iter is a use
    if node_type in ("For", "AsyncFor"):
        # iter is a use
        iter_node = node.get("iter")
        if iter_node:
            _collect_names_from_node(iter_node, names, scope, in_target=False)
        # body and orelse
        for child in node.get("body", []):
            if isinstance(child, dict):
                _collect_names_from_node(child, names, scope, in_target=False)
        for child in node.get("orelse", []):
            if isinstance(child, dict):
                _collect_names_from_node(child, names, scope, in_target=False)
        return

    # Recurse into common child containers (but not targets)
    for key in (
        "body",
        "orelse",
        "handlers",
        "finalbody",
        "args",
        "keywords",
        "elts",
        "keys",
        "values",
    ):
        children = node.get(key, [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    _collect_names_from_node(child, names, scope, in_target)
        elif isinstance(children, dict):
            _collect_names_from_node(children, names, scope, in_target)

    # Function call arguments
    if node_type == "Call":
        func = node.get("func")
        if func:
            _collect_names_from_node(func, names, scope, in_target=False)
        for arg in node.get("args", []):
            if isinstance(arg, dict):
                _collect_names_from_node(arg, names, scope, in_target=False)
        for kw in node.get("keywords", []):
            if isinstance(kw, dict) and "value" in kw:
                _collect_names_from_node(kw["value"], names, scope, in_target=False)

    # Subscript
    if node_type == "Subscript":
        value = node.get("value")
        if value:
            _collect_names_from_node(value, names, scope, in_target)
        slice_node = node.get("slice")
        if slice_node:
            _collect_names_from_node(slice_node, names, scope, in_target=False)

    # Binary/Compare operations
    for key in ("left", "right", "comparators", "test", "value", "operand"):
        child = node.get(key)
        if isinstance(child, dict):
            _collect_names_from_node(child, names, scope, in_target=False)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    _collect_names_from_node(item, names, scope, in_target=False)


def _collect_defined_names(
    node: dict, defined: dict[str, dict], scope: str = "module"
) -> None:
    """Collect all defined names (variables, functions, classes, imports).

    Args:
        node: AST node dict.
        defined: Dict mapping name to definition info.
        scope: Current scope name.
    """
    node_type = node.get("type", "")
    lineno = node.get("lineno", 1)

    # Function definition
    if node_type in ("FunctionDef", "AsyncFunctionDef"):
        name = node.get("name")
        if name:
            defined[name] = {"type": "function", "line": lineno, "scope": scope}
            # Parameters are defined within the function
            args = node.get("args", {})
            for arg_info in args.get("args", []):
                arg_name = arg_info.get("arg")
                if arg_name:
                    defined[arg_name] = {
                        "type": "parameter",
                        "line": lineno,
                        "scope": name,
                    }
            # Recurse into function body with new scope
            for child in node.get("body", []):
                _collect_defined_names(child, defined, name)
        return

    # Class definition
    if node_type == "ClassDef":
        name = node.get("name")
        if name:
            defined[name] = {"type": "class", "line": lineno, "scope": scope}
            for child in node.get("body", []):
                _collect_defined_names(child, defined, name)
        return

    # Import
    if node_type == "Import":
        for name_info in node.get("names", []):
            import_name = name_info.get("asname") or name_info.get("name")
            if import_name:
                # Handle dotted imports - use first part
                if "." in import_name:
                    import_name = import_name.split(".")[0]
                defined[import_name] = {
                    "type": "import",
                    "line": lineno,
                    "scope": scope,
                }

    # ImportFrom
    if node_type == "ImportFrom":
        for name_info in node.get("names", []):
            import_name = name_info.get("asname") or name_info.get("name")
            if import_name and import_name != "*":
                defined[import_name] = {
                    "type": "import",
                    "line": lineno,
                    "scope": scope,
                }

    # Assignment
    if node_type == "Assign":
        for target in node.get("targets", []):
            if target.get("type") == "Name":
                var_name = target.get("id")
                if var_name:
                    defined[var_name] = {
                        "type": "variable",
                        "line": lineno,
                        "scope": scope,
                    }

    # Annotated assignment
    if node_type == "AnnAssign":
        target = node.get("target")
        if target and target.get("type") == "Name":
            var_name = target.get("id")
            if var_name:
                defined[var_name] = {"type": "variable", "line": lineno, "scope": scope}

    # For loop target
    if node_type == "For":
        target = node.get("target")
        if target and target.get("type") == "Name":
            var_name = target.get("id")
            if var_name:
                defined[var_name] = {"type": "variable", "line": lineno, "scope": scope}

    # Exception handler
    if node_type == "ExceptHandler":
        exc_name = node.get("name")
        if exc_name:
            defined[exc_name] = {"type": "variable", "line": lineno, "scope": scope}

    # With statement
    if node_type == "With":
        for item in node.get("items", []):
            optional_vars = item.get("optional_vars")
            if optional_vars and optional_vars.get("type") == "Name":
                var_name = optional_vars.get("id")
                if var_name:
                    defined[var_name] = {
                        "type": "variable",
                        "line": lineno,
                        "scope": scope,
                    }

    # Recurse into body
    for key in ("body", "orelse", "handlers", "finalbody"):
        for child in node.get(key, []):
            if isinstance(child, dict):
                _collect_defined_names(child, defined, scope)


def lint_unused_imports(ast_data: dict, path: str) -> list[dict]:
    """L101: Detect unused imports.

    Args:
        ast_data: Parsed Python AST dict.
        path: Source file path.

    Returns:
        List of diagnostic records for unused imports.
    """
    diagnostics = []

    # Collect all imports
    imports: dict[str, dict] = {}

    def collect_imports(node: dict) -> None:
        node_type = node.get("type", "")
        lineno = node.get("lineno", 1)

        if node_type == "Import":
            for name_info in node.get("names", []):
                import_name = name_info.get("asname") or name_info.get("name")
                if import_name:
                    # Handle dotted imports - use first part as the accessible name
                    accessible_name = (
                        import_name.split(".")[0] if "." in import_name else import_name
                    )
                    imports[accessible_name] = {
                        "line": lineno,
                        "full_name": name_info.get("name"),
                    }

        elif node_type == "ImportFrom":
            module = node.get("module", "")
            for name_info in node.get("names", []):
                import_name = name_info.get("asname") or name_info.get("name")
                if import_name and import_name != "*":
                    imports[import_name] = {
                        "line": lineno,
                        "full_name": f"{module}.{name_info.get('name')}",
                    }

        # Recurse
        for child in node.get("body", []):
            if isinstance(child, dict):
                collect_imports(child)

    # Collect imports from module body
    for node in ast_data.get("body", []):
        collect_imports(node)

    # Collect all name references
    used_names: set[str] = set()
    for node in ast_data.get("body", []):
        # Skip import statements themselves
        if node.get("type") not in ("Import", "ImportFrom"):
            _collect_names_from_node(node, used_names)

    # Find unused imports
    for import_name, info in imports.items():
        if import_name not in used_names:
            diagnostics.append(
                {
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "warning",
                    "code": "L101",
                    "message": f"Unused import '{import_name}'",
                    "line": info["line"],
                    "col": 1,
                }
            )

    return diagnostics


def lint_unused_variables(ast_data: dict, path: str) -> list[dict]:
    """L102: Detect unused variables.

    Args:
        ast_data: Parsed Python AST dict.
        path: Source file path.

    Returns:
        List of diagnostic records for unused variables.
    """
    diagnostics = []

    # Collect all defined names
    defined: dict[str, dict] = {}
    for node in ast_data.get("body", []):
        _collect_defined_names(node, defined)

    # Collect all used names
    used_names: set[str] = set()
    for node in ast_data.get("body", []):
        _collect_names_from_node(node, used_names)

    # Find unused variables (not imports, functions, classes, or parameters)
    for var_name, info in defined.items():
        # Skip underscore variables (intentionally unused)
        if var_name.startswith("_"):
            continue

        # Skip imports (handled by L101)
        if info["type"] == "import":
            continue

        # Skip functions and classes (they may be exported)
        if info["type"] in ("function", "class"):
            continue

        # Skip parameters (they may be part of interface)
        if info["type"] == "parameter":
            continue

        # Check if used
        if var_name not in used_names:
            diagnostics.append(
                {
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "warning",
                    "code": "L102",
                    "message": f"Unused variable '{var_name}'",
                    "line": info["line"],
                    "col": 1,
                }
            )

    return diagnostics


def lint_variable_shadowing(ast_data: dict, path: str) -> list[dict]:
    """L103: Detect variable shadowing (inner scope shadows outer).

    Args:
        ast_data: Parsed Python AST dict.
        path: Source file path.

    Returns:
        List of diagnostic records for shadowed variables.
    """
    diagnostics = []

    # Track definitions by scope
    scopes: dict[str, dict[str, int]] = {"module": {}}

    def check_shadowing(node: dict, scope: str, parent_scopes: list[str]) -> None:
        node_type = node.get("type", "")
        lineno = node.get("lineno", 1)

        # Function - creates new scope
        if node_type in ("FunctionDef", "AsyncFunctionDef"):
            name = node.get("name")
            if name:
                new_scope = f"{scope}.{name}"
                scopes[new_scope] = {}

                # Check parameters for shadowing
                args = node.get("args", {})
                for arg_info in args.get("args", []):
                    arg_name = arg_info.get("arg")
                    if arg_name and arg_name != "self" and arg_name != "cls":
                        # Check if this shadows something in parent scopes
                        for parent in parent_scopes:
                            if arg_name in scopes.get(parent, {}):
                                diagnostics.append(
                                    {
                                        "kind": "diagnostic",
                                        "path": path,
                                        "severity": "info",
                                        "code": "L103",
                                        "message": f"Parameter '{arg_name}' shadows variable from outer scope",
                                        "line": lineno,
                                        "col": 1,
                                    }
                                )
                                break
                        scopes[new_scope][arg_name] = lineno

                # Recurse with new scope
                for child in node.get("body", []):
                    check_shadowing(child, new_scope, parent_scopes + [scope])
                return

        # Class - creates new scope
        if node_type == "ClassDef":
            name = node.get("name")
            if name:
                new_scope = f"{scope}.{name}"
                scopes[new_scope] = {}
                for child in node.get("body", []):
                    check_shadowing(child, new_scope, parent_scopes + [scope])
                return

        # Variable assignment - check for shadowing
        if node_type == "Assign":
            for target in node.get("targets", []):
                if target.get("type") == "Name":
                    var_name = target.get("id")
                    if var_name and not var_name.startswith("_"):
                        # Check parent scopes
                        for parent in parent_scopes:
                            if var_name in scopes.get(parent, {}):
                                diagnostics.append(
                                    {
                                        "kind": "diagnostic",
                                        "path": path,
                                        "severity": "info",
                                        "code": "L103",
                                        "message": f"Variable '{var_name}' shadows variable from outer scope",
                                        "line": lineno,
                                        "col": 1,
                                    }
                                )
                                break
                        if scope not in scopes:
                            scopes[scope] = {}
                        scopes[scope][var_name] = lineno

        # Recurse into body
        for key in ("body", "orelse", "handlers", "finalbody"):
            for child in node.get(key, []):
                if isinstance(child, dict):
                    check_shadowing(child, scope, parent_scopes)

    # Start from module level
    for node in ast_data.get("body", []):
        check_shadowing(node, "module", [])

    return diagnostics


# =============================================================================
# JS/TS AST-aware lint rules (tree-sitter)
# =============================================================================


def _js_collect_import_names(node: dict) -> dict[str, int]:
    """Collect all imported names from a tree-sitter JS/TS AST.

    Returns:
        Dict mapping imported name to line number.
    """
    imports: dict[str, int] = {}

    def walk(n: dict) -> None:
        ntype = n.get("type", "")
        lineno = n.get("start_point", {}).get("row", 0) + 1

        if ntype == "import_statement":
            # Collect identifiers from import clauses
            for child in n.get("children", []):
                _js_collect_import_identifiers(child, imports, lineno)
            return  # Don't recurse further into import

        for child in n.get("children", []):
            walk(child)

    walk(node)
    return imports


def _js_collect_import_identifiers(
    node: dict, imports: dict[str, int], lineno: int
) -> None:
    """Recursively collect imported identifier names."""
    ntype = node.get("type", "")

    if ntype == "identifier" and node.get("name"):
        imports[node["name"]] = lineno
    elif ntype == "import_specifier":
        # { foo as bar } — the local name is the last identifier
        children = node.get("children", [])
        # Find the local binding name (last identifier child, or the aliased name)
        ids = [c for c in children if c.get("type") == "identifier" and c.get("name")]
        if ids:
            # Last identifier is the local name (alias or original)
            imports[ids[-1]["name"]] = lineno
        return
    elif ntype == "namespace_import":
        # import * as name
        for child in node.get("children", []):
            if child.get("type") == "identifier" and child.get("name"):
                imports[child["name"]] = lineno
        return

    for child in node.get("children", []):
        _js_collect_import_identifiers(child, imports, lineno)


def _js_collect_used_names(node: dict, skip_declarations: bool = False) -> set[str]:
    """Collect all identifier references used in expressions (not declarations).

    Args:
        node: Tree-sitter AST node dict.
        skip_declarations: If True, skip declaration sites.

    Returns:
        Set of referenced identifier names.
    """
    used: set[str] = set()

    def walk(n: dict, in_decl: bool = False) -> None:
        ntype = n.get("type", "")

        # Skip import statements entirely — they're declarations
        if ntype == "import_statement":
            return

        # Variable declarator: name child is a declaration, value child is usage
        if ntype == "variable_declarator":
            children = n.get("children", [])
            for i, child in enumerate(children):
                if child.get("type") == "identifier" and i == 0:
                    continue  # Skip the declared name (first identifier)
                walk(child, False)
            return

        # Function/class declaration: name is a declaration, body is usage
        if ntype in ("function_declaration", "class_declaration"):
            children = n.get("children", [])
            for child in children:
                if child.get("type") == "identifier":
                    continue  # Skip function/class name
                walk(child, False)
            return

        # Parameters: names are declarations
        if ntype in ("formal_parameters", "required_parameter", "optional_parameter"):
            # Don't collect parameter names as uses
            for child in n.get("children", []):
                if child.get("type") not in ("identifier", "type_identifier"):
                    walk(child, True)
            return

        # Identifiers in expression context are uses
        if ntype == "identifier" and not in_decl:
            name = n.get("name")
            if name:
                used.add(name)

        for child in n.get("children", []):
            walk(child, in_decl)

    walk(node)
    return used


def _js_collect_declared_variables(node: dict) -> dict[str, dict]:
    """Collect all variable declarations (const/let/var) from JS/TS AST.

    Returns:
        Dict mapping variable name to {line, scope, type}.
    """
    declared: dict[str, dict] = {}

    def walk(n: dict, scope: str = "module") -> None:
        ntype = n.get("type", "")
        lineno = n.get("start_point", {}).get("row", 0) + 1

        # Function declaration — name is declared, creates new scope
        if ntype == "function_declaration":
            name = n.get("name")
            if name:
                declared[name] = {"line": lineno, "scope": scope, "type": "function"}
            for child in n.get("children", []):
                walk(child, name or scope)
            return

        # Class declaration
        if ntype == "class_declaration":
            name = n.get("name")
            if name:
                declared[name] = {"line": lineno, "scope": scope, "type": "class"}
            for child in n.get("children", []):
                walk(child, name or scope)
            return

        # Variable declarator
        if ntype == "variable_declarator":
            name = n.get("name")
            if name:
                declared[name] = {"line": lineno, "scope": scope, "type": "variable"}
            return

        # Method definition — creates new scope
        if ntype == "method_definition":
            name = n.get("name")
            for child in n.get("children", []):
                walk(child, name or scope)
            return

        # Arrow function — creates new scope
        if ntype == "arrow_function":
            for child in n.get("children", []):
                walk(child, scope)
            return

        for child in n.get("children", []):
            walk(child, scope)

    walk(node)
    return declared


def _js_collect_scoped_declarations(
    node: dict,
) -> dict[str, dict[str, int]]:
    """Collect declarations grouped by scope for shadowing detection.

    Returns:
        Dict mapping scope name to {variable_name: line_number}.
    """
    scopes: dict[str, dict[str, int]] = {"module": {}}

    def walk(n: dict, scope: str = "module", parent_scopes: list[str] | None = None) -> None:
        if parent_scopes is None:
            parent_scopes = []
        ntype = n.get("type", "")
        lineno = n.get("start_point", {}).get("row", 0) + 1

        # Function declaration — creates new scope
        if ntype == "function_declaration":
            name = n.get("name")
            if name:
                if scope not in scopes:
                    scopes[scope] = {}
                scopes[scope][name] = lineno
                new_scope = f"{scope}.{name}"
                scopes[new_scope] = {}
                for child in n.get("children", []):
                    walk(child, new_scope, parent_scopes + [scope])
                return

        # Class declaration
        if ntype == "class_declaration":
            name = n.get("name")
            if name:
                if scope not in scopes:
                    scopes[scope] = {}
                scopes[scope][name] = lineno
                new_scope = f"{scope}.{name}"
                scopes[new_scope] = {}
                for child in n.get("children", []):
                    walk(child, new_scope, parent_scopes + [scope])
                return

        # Method definition
        if ntype == "method_definition":
            name = n.get("name")
            if name:
                new_scope = f"{scope}.{name}"
                scopes[new_scope] = {}
                for child in n.get("children", []):
                    walk(child, new_scope, parent_scopes + [scope])
                return

        # Arrow function — anonymous scope
        if ntype == "arrow_function":
            new_scope = f"{scope}.<arrow:{lineno}>"
            scopes[new_scope] = {}
            for child in n.get("children", []):
                walk(child, new_scope, parent_scopes + [scope])
            return

        # Variable declarator — register in current scope
        if ntype == "variable_declarator":
            name = n.get("name")
            if name:
                if scope not in scopes:
                    scopes[scope] = {}
                scopes[scope][name] = lineno
            return

        # Formal parameters — register in current scope
        if ntype in ("required_parameter", "optional_parameter"):
            for child in n.get("children", []):
                if child.get("type") == "identifier" and child.get("name"):
                    if scope not in scopes:
                        scopes[scope] = {}
                    scopes[scope][child["name"]] = lineno
            return

        if ntype == "identifier" and n.get("name"):
            # Only collect if parent is formal_parameters
            pass  # Handled by required_parameter/optional_parameter above

        for child in n.get("children", []):
            walk(child, scope, parent_scopes)

    walk(node)
    return scopes


def lint_js_unused_imports(ast_data: dict, path: str) -> list[dict]:
    """L101: Detect unused imports in JS/TS tree-sitter AST.

    Args:
        ast_data: Tree-sitter AST dict.
        path: Source file path.

    Returns:
        List of diagnostic records.
    """
    imports = _js_collect_import_names(ast_data)
    if not imports:
        return []

    used = _js_collect_used_names(ast_data)

    diagnostics = []
    for name, lineno in imports.items():
        if name not in used:
            diagnostics.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "L101",
                "message": f"Unused import '{name}'",
                "line": lineno,
                "col": 1,
            })
    return diagnostics


def lint_js_unused_variables(ast_data: dict, path: str) -> list[dict]:
    """L102: Detect unused variables in JS/TS tree-sitter AST.

    Args:
        ast_data: Tree-sitter AST dict.
        path: Source file path.

    Returns:
        List of diagnostic records.
    """
    declared = _js_collect_declared_variables(ast_data)
    used = _js_collect_used_names(ast_data)

    diagnostics = []
    for name, info in declared.items():
        # Skip functions and classes (may be exported)
        if info["type"] in ("function", "class"):
            continue
        # Skip underscore-prefixed (intentionally unused)
        if name.startswith("_"):
            continue
        if name not in used:
            diagnostics.append({
                "kind": "diagnostic",
                "path": path,
                "severity": "warning",
                "code": "L102",
                "message": f"Unused variable '{name}'",
                "line": info["line"],
                "col": 1,
            })
    return diagnostics


def lint_js_variable_shadowing(ast_data: dict, path: str) -> list[dict]:
    """L103: Detect variable shadowing in JS/TS tree-sitter AST.

    Args:
        ast_data: Tree-sitter AST dict.
        path: Source file path.

    Returns:
        List of diagnostic records.
    """
    diagnostics: list[dict] = []

    def walk(
        node: dict, scope: str, parent_names: dict[str, int]
    ) -> None:
        ntype = node.get("type", "")
        lineno = node.get("start_point", {}).get("row", 0) + 1

        # Scope-creating nodes
        if ntype in ("function_declaration", "method_definition", "arrow_function"):
            name = node.get("name")
            inner_names: dict[str, int] = {}

            # Collect parameters
            for child in node.get("children", []):
                if child.get("type") == "formal_parameters":
                    _collect_param_names(child, inner_names, lineno)

            # Check params for shadowing
            for pname, pline in inner_names.items():
                if pname in parent_names:
                    diagnostics.append({
                        "kind": "diagnostic",
                        "path": path,
                        "severity": "info",
                        "code": "L103",
                        "message": f"Parameter '{pname}' shadows variable from outer scope",
                        "line": pline,
                        "col": 1,
                    })

            merged = {**parent_names, **inner_names}
            for child in node.get("children", []):
                walk(child, name or scope, merged)
            return

        # Variable declarator — check for shadowing
        if ntype == "variable_declarator":
            vname = node.get("name")
            if vname and vname in parent_names and not vname.startswith("_"):
                diagnostics.append({
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "info",
                    "code": "L103",
                    "message": f"Variable '{vname}' shadows variable from outer scope",
                    "line": lineno,
                    "col": 1,
                })
            return

        for child in node.get("children", []):
            walk(child, scope, parent_names)

    # Build top-level names first
    top_names: dict[str, int] = {}
    for child in ast_data.get("children", []):
        _collect_toplevel_names(child, top_names)

    # Walk for shadowing — pass empty parent_names at module level
    # (top-level declarations don't shadow each other; only inner scopes shadow outer)
    for child in ast_data.get("children", []):
        ntype = child.get("type", "")
        # For scope-creating nodes, pass top_names as parent so inner decls get checked
        if ntype in ("function_declaration", "method_definition", "arrow_function"):
            walk(child, "module", top_names)
        elif ntype == "export_statement":
            # Walk into exported declarations
            for sub in child.get("children", []):
                if sub.get("type") in ("function_declaration", "class_declaration"):
                    walk(sub, "module", top_names)
                else:
                    walk(sub, "module", {})
        else:
            # Top-level declarations — don't check against themselves
            walk(child, "module", {})

    return diagnostics


def _collect_param_names(node: dict, names: dict[str, int], default_line: int) -> None:
    """Collect parameter names from formal_parameters node."""
    for child in node.get("children", []):
        ctype = child.get("type", "")
        if ctype == "identifier" and child.get("name"):
            lineno = child.get("start_point", {}).get("row", default_line - 1) + 1
            names[child["name"]] = lineno
        elif ctype in ("required_parameter", "optional_parameter"):
            for sub in child.get("children", []):
                if sub.get("type") == "identifier" and sub.get("name"):
                    lineno = sub.get("start_point", {}).get("row", default_line - 1) + 1
                    names[sub["name"]] = lineno
                    break  # First identifier is the param name


def _collect_toplevel_names(node: dict, names: dict[str, int]) -> None:
    """Collect top-level declared names (variables, functions, classes)."""
    ntype = node.get("type", "")
    lineno = node.get("start_point", {}).get("row", 0) + 1

    if ntype in ("function_declaration", "class_declaration"):
        name = node.get("name")
        if name:
            names[name] = lineno
    elif ntype == "lexical_declaration":
        for child in node.get("children", []):
            if child.get("type") == "variable_declarator" and child.get("name"):
                names[child["name"]] = lineno
    elif ntype == "variable_declaration":
        for child in node.get("children", []):
            if child.get("type") == "variable_declarator" and child.get("name"):
                names[child["name"]] = lineno
    elif ntype == "export_statement":
        for child in node.get("children", []):
            _collect_toplevel_names(child, names)
    elif ntype == "import_statement":
        # Imports are top-level names
        for child in node.get("children", []):
            _collect_import_toplevel(child, names, lineno)


def _collect_import_toplevel(node: dict, names: dict[str, int], lineno: int) -> None:
    """Collect imported names as top-level names."""
    ntype = node.get("type", "")
    if ntype == "identifier" and node.get("name"):
        names[node["name"]] = lineno
    elif ntype == "import_specifier":
        ids = [c for c in node.get("children", []) if c.get("type") == "identifier" and c.get("name")]
        if ids:
            names[ids[-1]["name"]] = lineno
        return
    elif ntype == "namespace_import":
        for child in node.get("children", []):
            if child.get("type") == "identifier" and child.get("name"):
                names[child["name"]] = lineno
        return
    for child in node.get("children", []):
        _collect_import_toplevel(child, names, lineno)


def lint_js_ast(ast_data: dict, path: str, config: dict) -> list[dict]:
    """Run AST-aware lint rules on JavaScript/TypeScript code.

    Args:
        ast_data: Tree-sitter AST dict.
        path: Source file path.
        config: Lint configuration.

    Returns:
        List of diagnostic records.
    """
    diagnostics = []

    check_unused_imports = config.get("check_unused_imports", True)
    check_unused_variables = config.get("check_unused_variables", True)
    check_shadowing = config.get("check_variable_shadowing", True)

    if check_unused_imports:
        diagnostics.extend(lint_js_unused_imports(ast_data, path))

    if check_unused_variables:
        diagnostics.extend(lint_js_unused_variables(ast_data, path))

    if check_shadowing:
        diagnostics.extend(lint_js_variable_shadowing(ast_data, path))

    return diagnostics


def lint_python_ast(ast_data: dict, path: str, config: dict) -> list[dict]:
    """Run AST-aware lint rules on Python code.

    Args:
        ast_data: Parsed Python AST dict.
        path: Source file path.
        config: Lint configuration.

    Returns:
        List of diagnostic records.
    """
    diagnostics = []

    # Get config options
    check_unused_imports = config.get("check_unused_imports", True)
    check_unused_variables = config.get("check_unused_variables", True)
    check_shadowing = config.get("check_variable_shadowing", True)

    if check_unused_imports:
        diagnostics.extend(lint_unused_imports(ast_data, path))

    if check_unused_variables:
        diagnostics.extend(lint_unused_variables(ast_data, path))

    if check_shadowing:
        diagnostics.extend(lint_variable_shadowing(ast_data, path))

    return diagnostics


def lint_executor(
    config: dict, files: Iterable[dict], runner: ShardRunner
) -> list[dict]:
    """Execute the lint task.

    Runs lint rules on files in the shard. Uses AST-based linting for
    Python files when AST is available, plus text-based rules for all files.

    Args:
        config: Task configuration.
        files: Iterable of file records for this shard.
        runner: ShardRunner for CAS access.

    Returns:
        List of diagnostic output records.
    """
    outputs = []

    # Get execution context
    batch_id = config.get("_batch_id")
    shard_id = config.get("_shard_id")

    # Track which files we've linted with AST rules
    ast_linted_paths: set[str] = set()

    # First pass: AST-aware linting for files that have AST (from parse task)
    if batch_id and shard_id:
        for ast_output in runner.iter_prior_outputs(
            batch_id, "01_parse", shard_id, kind="ast"
        ):
            path = ast_output.get("path")
            object_ref = ast_output.get("object")

            if not path or not object_ref or path in ast_linted_paths:
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
                    # Run AST-aware Python lint rules
                    ast_diagnostics = lint_python_ast(ast_data, path, config)
                    outputs.extend(ast_diagnostics)
                    ast_linted_paths.add(path)
                elif ast_type == "program" and ast_data.get("parser") == "tree-sitter":
                    # Run AST-aware JS/TS lint rules
                    ast_diagnostics = lint_js_ast(ast_data, path, config)
                    outputs.extend(ast_diagnostics)
                    ast_linted_paths.add(path)

            except Exception as e:
                outputs.append(
                    {
                        "kind": "diagnostic",
                        "path": path,
                        "severity": "warning",
                        "code": "L998",
                        "message": f"AST lint error: {e}",
                        "line": 1,
                        "col": 1,
                    }
                )

    # Second pass: text-based lint rules for all files
    file_list = list(files)
    for file_record in file_list:
        path = file_record["path"]
        object_ref = file_record["object"]

        try:
            # Get file content from CAS
            data = runner.object_store.get_bytes(object_ref)

            # Try to decode as text
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                # Binary file - skip
                continue

            # Run text-based lint rules
            diagnostics = lint_content(content, path, config)
            outputs.extend(diagnostics)

        except Exception as e:
            outputs.append(
                {
                    "kind": "diagnostic",
                    "path": path,
                    "severity": "error",
                    "code": "L999",
                    "message": f"Lint error: {e}",
                    "line": 1,
                    "col": 1,
                }
            )

    return outputs
