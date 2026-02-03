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
    """P8-SYMBOLS: Symbol extraction must produce real identifiers."""

    def test_function_symbols_have_real_names(self):
        """Symbol extraction must not use line number placeholders."""
        from codebatch.tasks.symbols import extract_python_symbols

        code = '''
def calculate_total(items):
    pass

def process_order(order_id):
    pass
'''
        ast_dict, _ = parse_python(code.strip(), "test.py")
        symbols, edges = extract_python_symbols(ast_dict, "test.py")

        func_symbols = [s for s in symbols if s["symbol_type"] == "function"]
        func_names = [s["name"] for s in func_symbols]

        # Must have real names, not placeholders
        assert "calculate_total" in func_names
        assert "process_order" in func_names

        # Must NOT have placeholder names
        for name in func_names:
            assert not name.startswith("function_"), f"Placeholder name found: {name}"

    def test_class_symbols_have_real_names(self):
        """Class symbols must have actual class names."""
        from codebatch.tasks.symbols import extract_python_symbols

        code = '''
class ShoppingCart:
    pass

class OrderManager:
    pass
'''
        ast_dict, _ = parse_python(code.strip(), "test.py")
        symbols, edges = extract_python_symbols(ast_dict, "test.py")

        class_symbols = [s for s in symbols if s["symbol_type"] == "class"]
        class_names = [s["name"] for s in class_symbols]

        # Must have real names
        assert "ShoppingCart" in class_names
        assert "OrderManager" in class_names

        # Must NOT have placeholder names
        for name in class_names:
            assert not name.startswith("class_"), f"Placeholder name found: {name}"

    def test_scope_tracking_works(self):
        """Symbols must track their scope correctly."""
        from codebatch.tasks.symbols import extract_python_symbols

        code = '''
class Cart:
    def add_item(self, item):
        count = 0
        return count
'''
        ast_dict, _ = parse_python(code.strip(), "test.py")
        symbols, edges = extract_python_symbols(ast_dict, "test.py")

        # Find class symbol
        cart_symbol = next((s for s in symbols if s["name"] == "Cart"), None)
        assert cart_symbol is not None
        assert cart_symbol["scope"] == "module"

        # Find method symbol
        add_item_symbol = next((s for s in symbols if s["name"] == "add_item"), None)
        assert add_item_symbol is not None
        assert add_item_symbol["scope"] == "Cart"

        # Find variable symbol
        count_symbol = next((s for s in symbols if s["name"] == "count"), None)
        assert count_symbol is not None
        assert count_symbol["scope"] == "add_item"

    def test_import_edges_have_real_targets(self):
        """Import edges must have real module names, not placeholders."""
        from codebatch.tasks.symbols import extract_python_symbols

        code = '''
import os
import sys
from pathlib import Path
from typing import List, Dict
'''
        ast_dict, _ = parse_python(code.strip(), "test.py")
        symbols, edges = extract_python_symbols(ast_dict, "test.py")

        import_edges = [e for e in edges if e["edge_type"] == "imports"]
        targets = [e["target"] for e in import_edges]

        # Must have real module names
        assert "os" in targets
        assert "sys" in targets
        assert "pathlib.Path" in targets
        assert "typing.List" in targets
        assert "typing.Dict" in targets

        # Must NOT have placeholder targets
        for target in targets:
            assert not target.startswith("module_"), f"Placeholder target: {target}"
            assert not target.startswith("from_module_"), f"Placeholder target: {target}"

    def test_no_placeholder_names_anywhere(self):
        """Comprehensive check: no placeholder patterns in any symbol or edge."""
        from codebatch.tasks.symbols import extract_python_symbols
        import re

        code = '''
import os
from collections import defaultdict

CONSTANT = 42

class MyClass:
    my_var = "hello"

    def my_method(self, arg1, arg2):
        local_var = arg1 + arg2
        return local_var

def standalone_func():
    x = 1
    return x
'''
        ast_dict, _ = parse_python(code.strip(), "test.py")
        symbols, edges = extract_python_symbols(ast_dict, "test.py")

        # Placeholder patterns: name_<number> where number is a line number
        placeholder_pattern = re.compile(r'^(function|class|variable|module|from_module)_\d+$')

        # Check all symbol names
        for symbol in symbols:
            name = symbol.get("name", "")
            assert not placeholder_pattern.match(name), f"Placeholder pattern found: {name}"
            # Name should be a real identifier
            assert name.isidentifier() or "." in name, f"Invalid name: {name}"

        # Check all edge targets
        for edge in edges:
            target = edge.get("target", "")
            assert not placeholder_pattern.match(target), f"Placeholder pattern found: {target}"


class TestGateP8Roundtrip:
    """P8-ROUNDTRIP: Parse -> Symbols -> Query must work end-to-end."""

    def test_full_pipeline_produces_queryable_symbols(self, tmp_path):
        """Full pipeline must produce symbols queryable by name."""
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.query import QueryEngine
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.symbols import symbols_executor
        import json

        # Create test corpus
        corpus = tmp_path / "corpus"
        corpus.mkdir()

        test_file = corpus / "example.py"
        test_file.write_text('''
import os
from pathlib import Path

class Calculator:
    """A simple calculator class."""

    def add(self, a, b):
        result = a + b
        return result

    def subtract(self, a, b):
        return a - b

def main():
    calc = Calculator()
    print(calc.add(1, 2))
'''.strip())

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        # Create snapshot
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus)

        # Create batch with full pipeline
        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards with files
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run tasks using proper API
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        # Query symbols
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "03_symbols")

        # Filter to symbol kind
        symbols = [o for o in all_outputs if o.get("kind") == "symbol"]
        symbol_names = [s.get("name") for s in symbols]

        # Verify real names are present
        assert "Calculator" in symbol_names, f"Class 'Calculator' not found in {symbol_names}"
        assert "add" in symbol_names, f"Method 'add' not found in {symbol_names}"
        assert "subtract" in symbol_names, f"Method 'subtract' not found in {symbol_names}"
        assert "main" in symbol_names, f"Function 'main' not found in {symbol_names}"

        # Verify no placeholder names
        for name in symbol_names:
            assert not name.startswith("function_"), f"Placeholder: {name}"
            assert not name.startswith("class_"), f"Placeholder: {name}"

        # Filter edges
        edges = [o for o in all_outputs if o.get("kind") == "edge"]
        edge_targets = [e.get("target") for e in edges]

        # Verify import edges have real names
        assert "os" in edge_targets, f"Import 'os' not found in {edge_targets}"
        assert "pathlib.Path" in edge_targets, f"Import 'pathlib.Path' not found in {edge_targets}"

    def test_symbols_have_correct_scope(self, tmp_path):
        """Symbols must have correct scope tracking through pipeline."""
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.query import QueryEngine
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.symbols import symbols_executor

        # Create test corpus
        corpus = tmp_path / "corpus"
        corpus.mkdir()

        test_file = corpus / "scoped.py"
        test_file.write_text('''
class Outer:
    class_attr = 1

    def method(self, x):
        local_var = x * 2
        return local_var
'''.strip())

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        # Create snapshot and batch
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards with files
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run tasks
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        # Query symbols
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "03_symbols")
        symbols = [o for o in all_outputs if o.get("kind") == "symbol"]

        # Find specific symbols and check scope
        outer = next((s for s in symbols if s["name"] == "Outer"), None)
        assert outer is not None
        assert outer["scope"] == "module"

        method = next((s for s in symbols if s["name"] == "method"), None)
        assert method is not None
        assert method["scope"] == "Outer"

        local_var = next((s for s in symbols if s["name"] == "local_var"), None)
        assert local_var is not None
        assert local_var["scope"] == "method"


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
