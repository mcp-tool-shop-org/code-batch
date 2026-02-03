"""Parse task executor - produces AST and diagnostic outputs.

Supports:
- Python (via ast module) - Full AST with names preserved
- JavaScript/TypeScript (tree-sitter for full AST, regex fallback)
- Text files (line-based tokenization)

Emits:
- kind=ast: AST objects stored in CAS (format=json or format=json+chunks)
- kind=diagnostic: Parse errors/warnings

Enforces chunking threshold (default 16MB) with chunk manifest objects.

Phase 8: Full Python AST with function/class/variable names preserved.
         Tree-sitter for JS/TS when available.
"""

import ast
import json
import re
from typing import Any, Iterable, Optional

from ..common import SCHEMA_VERSION, PRODUCER
from ..runner import ShardRunner


# Tree-sitter imports (optional)
_TREE_SITTER_AVAILABLE = False
_ts_js_language = None
_ts_ts_language = None
_ts_tsx_language = None

try:
    import tree_sitter_javascript as ts_js
    import tree_sitter_typescript as ts_ts
    from tree_sitter import Language, Parser
    _TREE_SITTER_AVAILABLE = True
    _ts_js_language = Language(ts_js.language())
    _ts_ts_language = Language(ts_ts.language_typescript())
    _ts_tsx_language = Language(ts_ts.language_tsx())
except ImportError:
    pass


def is_treesitter_available() -> bool:
    """Check if tree-sitter is available for JS/TS parsing."""
    return _TREE_SITTER_AVAILABLE


# Default chunk size: 16MB
DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024


def _ast_node_to_dict(node: ast.AST, depth: int = 0, max_depth: int = 50) -> dict:
    """Convert an AST node to a dictionary with full fidelity.

    Preserves all important attributes including names, args, etc.
    Uses depth limiting to handle recursive structures.

    Args:
        node: AST node to convert.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        Dictionary representation of the node.
    """
    if depth > max_depth:
        return {"type": node.__class__.__name__, "truncated": True}

    result: dict[str, Any] = {"type": node.__class__.__name__}

    # Add location info if present
    if hasattr(node, "lineno"):
        result["lineno"] = node.lineno
    if hasattr(node, "col_offset"):
        result["col_offset"] = node.col_offset
    if hasattr(node, "end_lineno"):
        result["end_lineno"] = node.end_lineno
    if hasattr(node, "end_col_offset"):
        result["end_col_offset"] = node.end_col_offset

    # Handle specific node types with their important attributes
    node_type = node.__class__.__name__

    # Names and identifiers
    if hasattr(node, "name") and node.name is not None:
        result["name"] = node.name
    if hasattr(node, "id") and node.id is not None:
        result["id"] = node.id
    if hasattr(node, "attr") and node.attr is not None:
        result["attr"] = node.attr
    if hasattr(node, "asname") and node.asname is not None:
        result["asname"] = node.asname
    if hasattr(node, "module") and node.module is not None:
        result["module"] = node.module
    if hasattr(node, "arg") and node.arg is not None:
        result["arg"] = node.arg

    # Function arguments
    if node_type == "FunctionDef" or node_type == "AsyncFunctionDef":
        if hasattr(node, "args") and node.args:
            result["args"] = _convert_arguments(node.args, depth + 1, max_depth)
        if hasattr(node, "decorator_list") and node.decorator_list:
            result["decorators"] = [
                _ast_node_to_dict(d, depth + 1, max_depth)
                for d in node.decorator_list
            ]
        if hasattr(node, "returns") and node.returns:
            result["returns"] = _ast_node_to_dict(node.returns, depth + 1, max_depth)

    # Class bases and keywords
    if node_type == "ClassDef":
        if hasattr(node, "bases") and node.bases:
            result["bases"] = [
                _ast_node_to_dict(b, depth + 1, max_depth)
                for b in node.bases
            ]
        if hasattr(node, "decorator_list") and node.decorator_list:
            result["decorators"] = [
                _ast_node_to_dict(d, depth + 1, max_depth)
                for d in node.decorator_list
            ]

    # Import handling
    if node_type == "Import":
        result["names"] = [
            {"name": alias.name, "asname": alias.asname}
            for alias in node.names
        ]
    if node_type == "ImportFrom":
        result["names"] = [
            {"name": alias.name, "asname": alias.asname}
            for alias in node.names
        ]
        result["level"] = node.level

    # Assignment targets
    if node_type in ("Assign", "AnnAssign", "AugAssign"):
        if hasattr(node, "targets"):
            result["targets"] = [
                _ast_node_to_dict(t, depth + 1, max_depth)
                for t in node.targets
            ]
        if hasattr(node, "target"):
            result["target"] = _ast_node_to_dict(node.target, depth + 1, max_depth)
        if hasattr(node, "annotation") and node.annotation:
            result["annotation"] = _ast_node_to_dict(node.annotation, depth + 1, max_depth)

    # Literals
    if node_type == "Constant":
        # Represent the value safely
        val = node.value
        if isinstance(val, (str, int, float, bool, type(None))):
            result["value"] = val
        elif isinstance(val, bytes):
            result["value"] = f"<bytes:{len(val)}>"
        else:
            result["value"] = f"<{type(val).__name__}>"

    # Expression statements (Expr) - capture the value
    if node_type == "Expr" and hasattr(node, "value") and node.value:
        result["value"] = _ast_node_to_dict(node.value, depth + 1, max_depth)

    # Call expressions
    if node_type == "Call":
        if hasattr(node, "func") and node.func:
            result["func"] = _ast_node_to_dict(node.func, depth + 1, max_depth)
        if hasattr(node, "args") and node.args:
            result["args"] = [
                _ast_node_to_dict(a, depth + 1, max_depth)
                for a in node.args
            ]
        if hasattr(node, "keywords") and node.keywords:
            result["keywords"] = [
                {"arg": kw.arg, "value": _ast_node_to_dict(kw.value, depth + 1, max_depth)}
                for kw in node.keywords
            ]

    # Attribute access
    if node_type == "Attribute" and hasattr(node, "value") and node.value:
        result["value"] = _ast_node_to_dict(node.value, depth + 1, max_depth)

    # Subscript
    if node_type == "Subscript":
        if hasattr(node, "value") and node.value:
            result["value"] = _ast_node_to_dict(node.value, depth + 1, max_depth)
        if hasattr(node, "slice") and node.slice:
            result["slice"] = _ast_node_to_dict(node.slice, depth + 1, max_depth)

    # Binary operations
    if node_type in ("BinOp", "Compare", "BoolOp"):
        if hasattr(node, "left") and node.left:
            result["left"] = _ast_node_to_dict(node.left, depth + 1, max_depth)
        if hasattr(node, "right") and node.right:
            result["right"] = _ast_node_to_dict(node.right, depth + 1, max_depth)
        if hasattr(node, "comparators") and node.comparators:
            result["comparators"] = [
                _ast_node_to_dict(c, depth + 1, max_depth)
                for c in node.comparators
            ]
        if hasattr(node, "values") and node.values:
            result["values"] = [
                _ast_node_to_dict(v, depth + 1, max_depth)
                for v in node.values
            ]

    # Unary operations
    if node_type == "UnaryOp" and hasattr(node, "operand") and node.operand:
        result["operand"] = _ast_node_to_dict(node.operand, depth + 1, max_depth)

    # Return/Yield statements
    if node_type in ("Return", "Yield", "YieldFrom"):
        if hasattr(node, "value") and node.value:
            result["value"] = _ast_node_to_dict(node.value, depth + 1, max_depth)

    # List/Tuple/Set literals
    if node_type in ("List", "Tuple", "Set"):
        if hasattr(node, "elts") and node.elts:
            result["elts"] = [
                _ast_node_to_dict(e, depth + 1, max_depth)
                for e in node.elts
            ]

    # Dict literals
    if node_type == "Dict":
        if hasattr(node, "keys") and node.keys:
            result["keys"] = [
                _ast_node_to_dict(k, depth + 1, max_depth) if k else None
                for k in node.keys
            ]
        if hasattr(node, "values") and node.values:
            result["values"] = [
                _ast_node_to_dict(v, depth + 1, max_depth)
                for v in node.values
            ]

    # For body-containing nodes, include children
    if hasattr(node, "body") and isinstance(node.body, list):
        result["body"] = [
            _ast_node_to_dict(child, depth + 1, max_depth)
            for child in node.body
            if isinstance(child, ast.AST)
        ]

    # orelse for if/for/while/try
    if hasattr(node, "orelse") and isinstance(node.orelse, list) and node.orelse:
        result["orelse"] = [
            _ast_node_to_dict(child, depth + 1, max_depth)
            for child in node.orelse
            if isinstance(child, ast.AST)
        ]

    # handlers for try/except
    if hasattr(node, "handlers") and node.handlers:
        result["handlers"] = [
            _ast_node_to_dict(h, depth + 1, max_depth)
            for h in node.handlers
        ]

    # ExceptHandler specifics
    if node_type == "ExceptHandler":
        if hasattr(node, "type") and node.type:
            result["exc_type"] = _ast_node_to_dict(node.type, depth + 1, max_depth)

    return result


def _convert_arguments(args: ast.arguments, depth: int, max_depth: int) -> dict:
    """Convert function arguments to dict.

    Args:
        args: ast.arguments node.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        Dictionary with argument info.
    """
    result = {}

    if args.args:
        result["args"] = [
            {"arg": a.arg, "annotation": _ast_node_to_dict(a.annotation, depth, max_depth) if a.annotation else None}
            for a in args.args
        ]

    if args.posonlyargs:
        result["posonlyargs"] = [
            {"arg": a.arg, "annotation": _ast_node_to_dict(a.annotation, depth, max_depth) if a.annotation else None}
            for a in args.posonlyargs
        ]

    if args.kwonlyargs:
        result["kwonlyargs"] = [
            {"arg": a.arg, "annotation": _ast_node_to_dict(a.annotation, depth, max_depth) if a.annotation else None}
            for a in args.kwonlyargs
        ]

    if args.vararg:
        result["vararg"] = {"arg": args.vararg.arg}

    if args.kwarg:
        result["kwarg"] = {"arg": args.kwarg.arg}

    return result


def parse_python(content: str, path: str) -> tuple[Optional[dict], list[dict]]:
    """Parse Python source code with full AST fidelity.

    Produces a complete AST with all names preserved:
    - FunctionDef.name, ClassDef.name
    - Name.id, Attribute.attr
    - Import names, function arguments

    Args:
        content: Python source code.
        path: File path for error reporting.

    Returns:
        Tuple of (AST dict or None, list of diagnostics).
    """
    diagnostics = []

    try:
        tree = ast.parse(content, filename=path)

        # Convert full AST to dict with names preserved
        ast_dict = {
            "type": "Module",
            "ast_mode": "full",  # Phase 8: full fidelity mode
            "body": [
                _ast_node_to_dict(node)
                for node in tree.body
            ],
            "stats": {
                "total_nodes": len(list(ast.walk(tree))),
            },
        }
        return ast_dict, diagnostics

    except SyntaxError as e:
        diagnostics.append({
            "severity": "error",
            "code": "E0001",
            "message": str(e.msg) if e.msg else "Syntax error",
            "line": e.lineno or 1,
            "column": e.offset or 1,
        })
        return None, diagnostics


def _ts_node_to_dict(node, source_bytes: bytes, depth: int = 0, max_depth: int = 50) -> dict:
    """Convert a tree-sitter node to dictionary with full fidelity.

    Args:
        node: Tree-sitter Node object.
        source_bytes: Original source code as bytes.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        Dictionary representation of the node.
    """
    if depth > max_depth:
        return {"type": node.type, "truncated": True}

    result: dict[str, Any] = {"type": node.type}

    # Add location info
    result["start_point"] = {"row": node.start_point[0], "column": node.start_point[1]}
    result["end_point"] = {"row": node.end_point[0], "column": node.end_point[1]}

    # Extract name for named constructs
    # Common patterns: function name is identifier child, class name is identifier child
    if node.type in (
        "function_declaration", "method_definition", "class_declaration",
        "variable_declarator", "lexical_declaration", "function_expression",
        "arrow_function", "export_statement", "import_statement",
    ):
        # Look for identifier or property_identifier children
        for child in node.children:
            if child.type == "identifier":
                result["name"] = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break
            if child.type == "property_identifier":
                result["name"] = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break

    # For identifiers, capture the actual name
    if node.type in ("identifier", "property_identifier", "type_identifier"):
        result["name"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    # For import/export, capture source
    if node.type == "import_statement":
        for child in node.children:
            if child.type == "string":
                text = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                result["source"] = text.strip("'\"")
                break

    # For string/number literals, capture value
    if node.type in ("string", "number", "template_string"):
        result["value"] = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    # Recurse into children for structural nodes
    if node.child_count > 0 and node.type not in ("comment", "string", "number", "template_string"):
        children = []
        for child in node.children:
            # Skip comments for cleaner AST
            if child.type not in ("comment", ):
                children.append(_ts_node_to_dict(child, source_bytes, depth + 1, max_depth))
        if children:
            result["children"] = children

    return result


def parse_javascript_treesitter(content: str, path: str, is_typescript: bool = False) -> tuple[Optional[dict], list[dict]]:
    """Parse JavaScript/TypeScript using tree-sitter.

    Args:
        content: JS/TS source code.
        path: File path.
        is_typescript: Whether to use TypeScript grammar.

    Returns:
        Tuple of (AST dict or None, list of diagnostics).
    """
    diagnostics = []
    source_bytes = content.encode("utf-8")

    # Select language
    if is_typescript:
        if path.endswith(".tsx"):
            language = _ts_tsx_language
        else:
            language = _ts_ts_language
    else:
        language = _ts_js_language

    from tree_sitter import Parser
    parser = Parser(language)
    tree = parser.parse(source_bytes)

    # Check for parse errors
    if tree.root_node.has_error:
        # Find error nodes
        def find_errors(node):
            errors = []
            if node.type == "ERROR" or node.is_missing:
                errors.append({
                    "severity": "error",
                    "code": "E0002",
                    "message": f"Parse error at {node.type}",
                    "line": node.start_point[0] + 1,
                    "column": node.start_point[1] + 1,
                })
            for child in node.children:
                errors.extend(find_errors(child))
            return errors
        diagnostics.extend(find_errors(tree.root_node))

    # Convert to dict
    ast_dict = _ts_node_to_dict(tree.root_node, source_bytes)
    ast_dict["ast_mode"] = "full"  # Full AST from tree-sitter
    ast_dict["parser"] = "tree-sitter"
    ast_dict["stats"] = {
        "total_nodes": _count_ts_nodes(tree.root_node),
    }

    return ast_dict, diagnostics


def _count_ts_nodes(node) -> int:
    """Count total nodes in tree-sitter tree."""
    count = 1
    for child in node.children:
        count += _count_ts_nodes(child)
    return count


def parse_javascript_fallback(content: str, path: str) -> tuple[Optional[dict], list[dict]]:
    """Fallback JavaScript/TypeScript tokenization when tree-sitter unavailable.

    This is a basic tokenizer, not a full parser.

    Args:
        content: JS/TS source code.
        path: File path.

    Returns:
        Tuple of (token info dict or None, list of diagnostics).
    """
    diagnostics = []

    # Simple token patterns
    patterns = {
        "keyword": r'\b(function|const|let|var|if|else|for|while|return|class|import|export|async|await)\b',
        "string": r'(["\'])(?:(?!\1)[^\\]|\\.)*\1',
        "number": r'\b\d+(?:\.\d+)?\b',
        "comment": r'//.*|/\*[\s\S]*?\*/',
        "identifier": r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b',
    }

    token_counts = {}
    for token_type, pattern in patterns.items():
        matches = re.findall(pattern, content)
        # Handle tuple returns from capture groups
        if matches and isinstance(matches[0], tuple):
            token_counts[token_type] = len(matches)
        else:
            token_counts[token_type] = len(matches)

    # Check for common issues
    # Unbalanced braces
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces != close_braces:
        diagnostics.append({
            "severity": "warning",
            "code": "W0001",
            "message": f"Unbalanced braces: {open_braces} open, {close_braces} close",
            "line": 1,
            "column": 1,
        })

    ast_dict = {
        "type": "TokenInfo",
        "ast_mode": "tokens",
        "parser": "regex-fallback",
        "tokens": token_counts,
        "stats": {
            "lines": content.count('\n') + 1,
            "characters": len(content),
        },
    }

    return ast_dict, diagnostics


def parse_javascript(content: str, path: str) -> tuple[Optional[dict], list[dict]]:
    """Parse JavaScript/TypeScript source code.

    Uses tree-sitter for full AST when available, falls back to
    simple tokenization otherwise.

    Args:
        content: JS/TS source code.
        path: File path.

    Returns:
        Tuple of (AST/token info dict or None, list of diagnostics).
    """
    if _TREE_SITTER_AVAILABLE:
        is_ts = path.endswith((".ts", ".tsx"))
        return parse_javascript_treesitter(content, path, is_typescript=is_ts)
    else:
        return parse_javascript_fallback(content, path)


def parse_text(content: str, path: str) -> tuple[Optional[dict], list[dict]]:
    """Simple text file tokenization.

    Args:
        content: Text content.
        path: File path.

    Returns:
        Tuple of (token info dict, empty diagnostics).
    """
    lines = content.split('\n')
    words = content.split()

    ast_dict = {
        "type": "TextInfo",
        "ast_mode": "text_stats",
        "stats": {
            "lines": len(lines),
            "words": len(words),
            "characters": len(content),
            "non_empty_lines": sum(1 for line in lines if line.strip()),
        },
    }

    return ast_dict, []


def create_chunk_manifest(
    data: bytes,
    kind: str,
    fmt: str,
    runner: ShardRunner,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[str, dict]:
    """Create a chunk manifest for large data.

    Args:
        data: Raw bytes to chunk.
        kind: Output kind.
        fmt: Base format identifier (will be suffixed with +chunks).
        runner: ShardRunner for CAS access.
        chunk_size: Target chunk size.

    Returns:
        Tuple of (manifest object ref, manifest dict).
    """
    chunks = []
    total_bytes = len(data)

    for i in range(0, total_bytes, chunk_size):
        chunk_data = data[i:i + chunk_size]
        chunk_ref = runner.object_store.put_bytes(chunk_data)
        chunks.append({
            "object": chunk_ref,
            "size": len(chunk_data),
            "index": len(chunks),
        })

    manifest = {
        "schema_name": "codebatch.chunk_manifest",
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "kind": kind,
        "format": fmt,
        "chunks": chunks,
        "total_bytes": total_bytes,
        "chunk_size": chunk_size,
    }

    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_ref = runner.object_store.put_bytes(manifest_bytes)

    return manifest_ref, manifest


def parse_executor(config: dict, files: Iterable[dict], runner: ShardRunner) -> list[dict]:
    """Execute the parse task.

    Args:
        config: Task configuration.
        files: Iterable of file records for this shard (may be iterator).
        runner: ShardRunner for CAS access.

    Returns:
        List of output records.
    """
    outputs = []
    chunk_threshold = config.get("chunk_threshold", DEFAULT_CHUNK_SIZE)
    emit_ast = config.get("emit_ast", True)
    emit_diagnostics = config.get("emit_diagnostics", True)

    for file_record in files:
        path = file_record["path"]
        object_ref = file_record["object"]
        lang_hint = file_record.get("lang_hint")

        try:
            # Get file content from CAS
            data = runner.object_store.get_bytes(object_ref)

            # Try to decode as text
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                # Binary file - skip
                continue

            # Parse based on language
            ast_dict = None
            diagnostics = []

            if lang_hint == "python":
                ast_dict, diagnostics = parse_python(content, path)
            elif lang_hint in ("javascript", "typescript"):
                ast_dict, diagnostics = parse_javascript(content, path)
            elif lang_hint in ("markdown", "json", "yaml", "xml", "html", "css"):
                # Text-based formats
                ast_dict, diagnostics = parse_text(content, path)
            else:
                # Default text tokenization for unknown types
                ast_dict, diagnostics = parse_text(content, path)

            # Emit AST output
            if emit_ast and ast_dict is not None:
                ast_bytes = json.dumps(ast_dict, separators=(",", ":")).encode("utf-8")

                if len(ast_bytes) > chunk_threshold:
                    # Create chunk manifest - kind stays "ast", format becomes "json+chunks"
                    manifest_ref, _ = create_chunk_manifest(
                        ast_bytes, "ast", "json", runner, chunk_threshold
                    )
                    outputs.append({
                        "path": path,
                        "kind": "ast",  # Semantic kind stays ast
                        "object": manifest_ref,
                        "format": "json+chunks",  # Format indicates chunking
                    })
                else:
                    # Store directly
                    ast_ref = runner.object_store.put_bytes(ast_bytes)
                    outputs.append({
                        "path": path,
                        "kind": "ast",
                        "object": ast_ref,
                        "format": "json",
                    })

            # Emit diagnostics
            if emit_diagnostics:
                for diag in diagnostics:
                    outputs.append({
                        "path": path,
                        "kind": "diagnostic",
                        "severity": diag["severity"],
                        "code": diag["code"],
                        "message": diag["message"],
                        "line": diag.get("line"),
                        "column": diag.get("column"),
                    })

        except Exception as e:
            # Emit error diagnostic
            if emit_diagnostics:
                outputs.append({
                    "path": path,
                    "kind": "diagnostic",
                    "severity": "error",
                    "code": "E9999",
                    "message": f"Parse error: {str(e)}",
                    "line": 1,
                    "column": 1,
                })

    return outputs
