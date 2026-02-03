"""Phase 8 gate tests - Real workloads.

Gates:
- P8-PARSE: Python AST preserves function/class names
- P8-SYMBOLS: Real symbol identifiers (not placeholders)
- P8-ROUNDTRIP: Parse -> Symbols -> Query returns real names
- P8-TREESITTER: JS/TS real parsing (optional)
- P8-LINT-AST: AST-aware linting
- P8-METRICS: Real code metrics (complexity)
- P8-SELF-HOST: Self-analysis works
"""

import json
import pytest

from codebatch.tasks.parse import parse_python, parse_javascript


class TestGateP8Parse:
    """P8-PARSE: Python AST must preserve function and class names."""

    def test_function_name_preserved(self):
        """FunctionDef nodes must include actual name field."""
        code = '''
def calculate_total(items):
    pass
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        assert ast_dict["ast_mode"] == "full"
        assert len(diagnostics) == 0

        # Find the FunctionDef node
        body = ast_dict["body"]
        assert len(body) >= 1

        func_def = body[0]
        assert func_def["type"] == "FunctionDef"
        assert func_def["name"] == "calculate_total"  # Real name, not placeholder!

    def test_class_name_preserved(self):
        """ClassDef nodes must include actual name field."""
        code = '''
class ShoppingCart:
    pass
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        body = ast_dict["body"]
        assert len(body) >= 1

        class_def = body[0]
        assert class_def["type"] == "ClassDef"
        assert class_def["name"] == "ShoppingCart"  # Real name!

    def test_method_name_preserved(self):
        """Methods inside classes must have real names."""
        code = '''
class Cart:
    def add_item(self, item):
        pass

    def remove_item(self, item):
        pass
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        class_def = ast_dict["body"][0]
        assert class_def["type"] == "ClassDef"
        assert class_def["name"] == "Cart"

        # Methods are in the class body
        methods = class_def["body"]
        assert len(methods) >= 2

        method_names = [m["name"] for m in methods if m["type"] == "FunctionDef"]
        assert "add_item" in method_names
        assert "remove_item" in method_names

    def test_function_arguments_preserved(self):
        """Function arguments must be captured."""
        code = '''
def greet(name: str, times: int = 1) -> str:
    return name * times
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        func_def = ast_dict["body"][0]
        assert func_def["type"] == "FunctionDef"
        assert func_def["name"] == "greet"

        # Check arguments
        args = func_def.get("args", {})
        assert "args" in args
        arg_list = args["args"]
        assert len(arg_list) >= 2

        arg_names = [a["arg"] for a in arg_list]
        assert "name" in arg_names
        assert "times" in arg_names

    def test_variable_name_preserved(self):
        """Variable assignments must capture target names."""
        code = '''
total = 0
count = 10
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        body = ast_dict["body"]

        # Find Assign nodes
        assigns = [n for n in body if n["type"] == "Assign"]
        assert len(assigns) >= 2

        # Check that targets have id fields
        for assign in assigns:
            targets = assign.get("targets", [])
            assert len(targets) >= 1
            # Target should be a Name node with id
            target = targets[0]
            assert target["type"] == "Name"
            assert "id" in target

        # Verify specific variable names
        all_ids = []
        for assign in assigns:
            for target in assign.get("targets", []):
                if target["type"] == "Name":
                    all_ids.append(target["id"])

        assert "total" in all_ids
        assert "count" in all_ids

    def test_import_names_preserved(self):
        """Import statements must capture module names."""
        code = '''
import os
import sys
from pathlib import Path
from typing import List, Dict
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        body = ast_dict["body"]

        # Find Import nodes
        imports = [n for n in body if n["type"] == "Import"]
        assert len(imports) >= 2

        # Check import names
        import_names = []
        for imp in imports:
            for name_info in imp.get("names", []):
                import_names.append(name_info["name"])

        assert "os" in import_names
        assert "sys" in import_names

        # Find ImportFrom nodes
        from_imports = [n for n in body if n["type"] == "ImportFrom"]
        assert len(from_imports) >= 2

        # Check module names
        for imp in from_imports:
            assert "module" in imp
            assert "names" in imp

    def test_no_100_node_truncation(self):
        """Large files should not be truncated to 100 nodes."""
        # Generate a file with many functions
        functions = [f"def func_{i}(): pass" for i in range(150)]
        code = "\n".join(functions)

        ast_dict, diagnostics = parse_python(code, "test.py")

        assert ast_dict is not None
        body = ast_dict["body"]

        # Should have all 150 functions, not just 100
        assert len(body) >= 150

    def test_nested_functions_preserved(self):
        """Nested functions should have their names preserved."""
        code = '''
def outer():
    def inner():
        def deep():
            pass
        return deep
    return inner
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        outer = ast_dict["body"][0]
        assert outer["name"] == "outer"

        # Find inner function
        inner = None
        for node in outer.get("body", []):
            if node.get("type") == "FunctionDef":
                inner = node
                break

        assert inner is not None
        assert inner["name"] == "inner"

        # Find deep function
        deep = None
        for node in inner.get("body", []):
            if node.get("type") == "FunctionDef":
                deep = node
                break

        assert deep is not None
        assert deep["name"] == "deep"

    def test_async_function_name_preserved(self):
        """Async functions must have their names preserved."""
        code = '''
async def fetch_data(url: str):
    pass
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        func_def = ast_dict["body"][0]
        assert func_def["type"] == "AsyncFunctionDef"
        assert func_def["name"] == "fetch_data"

    def test_decorator_preserved(self):
        """Decorators should be captured."""
        code = '''
@staticmethod
def helper():
    pass
'''
        ast_dict, diagnostics = parse_python(code.strip(), "test.py")

        assert ast_dict is not None
        func_def = ast_dict["body"][0]
        assert func_def["name"] == "helper"
        assert "decorators" in func_def
        assert len(func_def["decorators"]) >= 1


class TestGateP8Symbols:
    """P8-SYMBOLS: Symbol extraction must produce real identifiers.

    These tests will be fully implemented in Commit 3.
    For now, they serve as placeholders that will fail until
    the symbols task is updated.
    """

    @pytest.mark.skip(reason="Commit 3 - symbols task not yet updated")
    def test_function_symbols_have_real_names(self):
        """Symbol extraction must not use line number placeholders."""
        pass

    @pytest.mark.skip(reason="Commit 3 - symbols task not yet updated")
    def test_class_symbols_have_real_names(self):
        """Class symbols must have actual class names."""
        pass

    @pytest.mark.skip(reason="Commit 3 - symbols task not yet updated")
    def test_scope_tracking_works(self):
        """Symbols must track their scope correctly."""
        pass


class TestGateP8Roundtrip:
    """P8-ROUNDTRIP: Parse -> Symbols -> Query must work end-to-end.

    These tests will be fully implemented in Commit 4.
    """

    @pytest.mark.skip(reason="Commit 4 - roundtrip tests not yet implemented")
    def test_full_pipeline_produces_queryable_symbols(self):
        """Full pipeline must produce symbols queryable by name."""
        pass


class TestGateP8TreeSitter:
    """P8-TREESITTER: JS/TS must have real AST via tree-sitter.

    These tests will be implemented in Commit 5.
    Gate is optional - skipped if tree-sitter not installed.
    """

    @pytest.mark.skip(reason="Commit 5 - tree-sitter not yet integrated")
    def test_js_produces_real_ast(self):
        """JavaScript must produce structural AST, not token counts."""
        pass


class TestGateP8LintAst:
    """P8-LINT-AST: AST-aware linting must detect semantic issues.

    These tests will be implemented in Commit 7.
    """

    @pytest.mark.skip(reason="Commit 7 - AST linting not yet implemented")
    def test_unused_import_detected(self):
        """Must detect unused imports."""
        pass

    @pytest.mark.skip(reason="Commit 7 - AST linting not yet implemented")
    def test_unused_variable_detected(self):
        """Must detect unused variables."""
        pass


class TestGateP8Metrics:
    """P8-METRICS: Analyze task must produce cyclomatic complexity.

    These tests will be implemented in Commit 8.
    """

    @pytest.mark.skip(reason="Commit 8 - complexity metrics not yet implemented")
    def test_complexity_calculated(self):
        """Must calculate cyclomatic complexity."""
        pass


class TestGateP8SelfHost:
    """P8-SELF-HOST: CodeBatch must analyze its own source meaningfully.

    These tests will be implemented in Commit 9.
    """

    @pytest.mark.skip(reason="Commit 9 - self-host tests not yet implemented")
    def test_self_analysis_produces_symbols(self):
        """Analyzing codebatch source must produce real symbols."""
        pass
