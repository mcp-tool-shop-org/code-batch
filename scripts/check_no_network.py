#!/usr/bin/env python3
"""CI Rule B: No network surface guard.

Fails if code imports network/server libraries.

Usage:
    python scripts/check_no_network.py [directory]

Arguments:
    directory: Directory to scan (default: src/)

Exit codes:
    0: No network imports found
    1: Network imports detected
    2: Error
"""

import ast
import sys
from pathlib import Path


# Forbidden imports - network/server libraries
FORBIDDEN_IMPORTS = {
    # Python stdlib network
    "socket",
    "socketserver",
    "http.server",
    "xmlrpc.server",
    "asyncio.Server",

    # Web frameworks
    "fastapi",
    "flask",
    "django",
    "starlette",
    "uvicorn",
    "gunicorn",
    "hypercorn",

    # Async web
    "aiohttp.web",
    "tornado.web",
    "sanic",

    # WebSocket
    "websockets",
    "websocket",

    # RPC
    "grpc",
    "thrift",
    "zerorpc",
}

# Partial matches (module starts with these)
FORBIDDEN_PREFIXES = [
    "http.server",
    "xmlrpc.server",
    "aiohttp.web",
    "tornado.web",
]


def check_imports(filepath: Path) -> list[str]:
    """Check a Python file for forbidden imports."""
    violations = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [f"Could not read file: {e}"]

    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module in FORBIDDEN_IMPORTS:
                    violations.append(f"Line {node.lineno}: import {module}")
                for prefix in FORBIDDEN_PREFIXES:
                    if module.startswith(prefix):
                        violations.append(f"Line {node.lineno}: import {module}")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_IMPORTS:
                violations.append(f"Line {node.lineno}: from {module} import ...")
            for prefix in FORBIDDEN_PREFIXES:
                if module.startswith(prefix):
                    violations.append(f"Line {node.lineno}: from {module} import ...")

    return violations


def main():
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src")

    if not directory.exists():
        print(f"ERROR: Directory not found: {directory}")
        sys.exit(2)

    all_violations = {}

    for filepath in directory.rglob("*.py"):
        violations = check_imports(filepath)
        if violations:
            all_violations[str(filepath)] = violations

    if all_violations:
        print("ERROR: Network/server imports detected")
        print("\nPhase 2 forbids network services. Remove these imports:\n")
        for filepath, violations in sorted(all_violations.items()):
            print(f"{filepath}:")
            for v in violations:
                print(f"  {v}")
        print("\nForbidden categories:")
        print("  - HTTP servers (http.server, flask, fastapi, etc.)")
        print("  - WebSocket servers")
        print("  - RPC frameworks")
        sys.exit(1)

    print(f"OK: No network imports found in {directory}")
    sys.exit(0)


if __name__ == "__main__":
    main()
