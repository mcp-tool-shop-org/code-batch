"""Parse task executor - produces AST and diagnostic outputs.

For Phase 1, supports:
- Python (via ast module)
- JavaScript/TypeScript (simple tokenization)
- Text files (line-based tokenization)

Emits:
- kind=ast: AST objects stored in CAS (format=json or format=json+chunks)
- kind=diagnostic: Parse errors/warnings

Enforces chunking threshold (default 16MB) with chunk manifest objects.
"""

import ast
import json
import re
from typing import Iterable, Optional

from ..common import SCHEMA_VERSION, PRODUCER
from ..runner import ShardRunner


# Default chunk size: 16MB
DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024


def parse_python(content: str, path: str) -> tuple[Optional[dict], list[dict]]:
    """Parse Python source code.

    Args:
        content: Python source code.
        path: File path for error reporting.

    Returns:
        Tuple of (AST dict or None, list of diagnostics).
    """
    diagnostics = []

    try:
        tree = ast.parse(content, filename=path)
        # Convert AST to dict - summarized mode for reasonable size
        ast_dict = {
            "type": "Module",
            "ast_mode": "summary",  # Explicit about summarization
            "body": [
                {
                    "type": node.__class__.__name__,
                    "lineno": getattr(node, "lineno", None),
                    "col_offset": getattr(node, "col_offset", None),
                }
                for node in ast.walk(tree)
                if hasattr(node, "lineno")
            ][:100],  # Limit for reasonable size
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


def parse_javascript(content: str, path: str) -> tuple[Optional[dict], list[dict]]:
    """Simple JavaScript/TypeScript tokenization.

    This is a basic tokenizer, not a full parser.
    For Phase 1, we just identify tokens and structure.

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
        "tokens": token_counts,
        "stats": {
            "lines": content.count('\n') + 1,
            "characters": len(content),
        },
    }

    return ast_dict, diagnostics


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
