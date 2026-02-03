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


def _check_treesitter_available() -> bool:
    """Check if tree-sitter is available for JS/TS parsing."""
    try:
        from codebatch.tasks.parse import is_treesitter_available
        return is_treesitter_available()
    except ImportError:
        return False


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

    Gate is optional - skipped if tree-sitter not installed.
    """

    def test_treesitter_availability_check(self):
        """is_treesitter_available() must return correct status."""
        from codebatch.tasks.parse import is_treesitter_available
        # Just verify the function exists and returns a bool
        result = is_treesitter_available()
        assert isinstance(result, bool)

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_produces_real_ast_structure(self):
        """JavaScript must produce structural AST, not token counts."""
        from codebatch.tasks.parse import parse_javascript

        js_code = '''
function fetchData(url) {
    return fetch(url);
}

const API_KEY = "secret";

class DataService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async getData(id) {
        return await fetch(this.baseUrl + "/" + id);
    }
}
'''.strip()

        ast_dict, diagnostics = parse_javascript(js_code, "test.js")

        # Must NOT be token mode
        assert ast_dict is not None
        assert ast_dict.get("ast_mode") == "full", f"Expected full AST, got {ast_dict.get('ast_mode')}"
        assert ast_dict.get("parser") == "tree-sitter", f"Expected tree-sitter, got {ast_dict.get('parser')}"

        # Must have structural children
        assert "children" in ast_dict or ast_dict.get("type") == "program"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_function_names_extracted(self):
        """JavaScript function names must be extracted."""
        from codebatch.tasks.parse import parse_javascript

        js_code = '''
function calculateTotal(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")

        # Find function declaration with name
        def find_functions(node):
            funcs = []
            if node.get("type") == "function_declaration":
                if "name" in node:
                    funcs.append(node["name"])
            for child in node.get("children", []):
                funcs.extend(find_functions(child))
            return funcs

        func_names = find_functions(ast_dict)
        assert "calculateTotal" in func_names, f"Function 'calculateTotal' not found in {func_names}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_class_names_extracted(self):
        """JavaScript class names must be extracted."""
        from codebatch.tasks.parse import parse_javascript

        js_code = '''
class ShoppingCart {
    constructor() {
        this.items = [];
    }

    addItem(item) {
        this.items.push(item);
    }
}
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")

        # Find class declaration with name
        def find_classes(node):
            classes = []
            if node.get("type") == "class_declaration":
                if "name" in node:
                    classes.append(node["name"])
            for child in node.get("children", []):
                classes.extend(find_classes(child))
            return classes

        class_names = find_classes(ast_dict)
        assert "ShoppingCart" in class_names, f"Class 'ShoppingCart' not found in {class_names}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_typescript_produces_real_ast(self):
        """TypeScript must produce structural AST."""
        from codebatch.tasks.parse import parse_javascript

        ts_code = '''
interface User {
    id: number;
    name: string;
}

function greetUser(user: User): string {
    return `Hello, ${user.name}!`;
}

const users: User[] = [];
'''.strip()

        ast_dict, _ = parse_javascript(ts_code, "test.ts")

        # Must be full AST
        assert ast_dict is not None
        assert ast_dict.get("ast_mode") == "full"
        assert ast_dict.get("parser") == "tree-sitter"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_import_extraction(self):
        """JavaScript imports must be extracted."""
        from codebatch.tasks.parse import parse_javascript

        js_code = '''
import React from 'react';
import { useState, useEffect } from 'react';
import * as utils from './utils';
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")

        # Find import statements
        def find_imports(node):
            imports = []
            if node.get("type") == "import_statement":
                if "source" in node:
                    imports.append(node["source"])
            for child in node.get("children", []):
                imports.extend(find_imports(child))
            return imports

        import_sources = find_imports(ast_dict)
        assert "react" in import_sources, f"Import 'react' not found in {import_sources}"

    def test_fallback_when_treesitter_unavailable(self):
        """Fallback tokenization must work when tree-sitter not available."""
        from codebatch.tasks.parse import parse_javascript_fallback

        js_code = '''
function test() {
    return 42;
}
'''.strip()

        ast_dict, _ = parse_javascript_fallback(js_code, "test.js")

        # Must be token mode
        assert ast_dict is not None
        assert ast_dict.get("ast_mode") == "tokens"
        assert ast_dict.get("parser") == "regex-fallback"
        assert "tokens" in ast_dict


class TestGateP8JsSymbols:
    """P8-JS-SYMBOLS: JS/TS symbol extraction must produce real names.

    Gate is optional - skipped if tree-sitter not installed.
    """

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_function_symbols_extracted(self):
        """JavaScript functions must be extracted as symbols."""
        from codebatch.tasks.parse import parse_javascript
        from codebatch.tasks.symbols import extract_js_symbols

        js_code = '''
function calculateTotal(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}

function formatCurrency(amount) {
    return "$" + amount.toFixed(2);
}
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")
        symbols, edges = extract_js_symbols(ast_dict, "test.js")

        symbol_names = [s["name"] for s in symbols if s["kind"] == "symbol"]
        assert "calculateTotal" in symbol_names, f"Function 'calculateTotal' not found in {symbol_names}"
        assert "formatCurrency" in symbol_names, f"Function 'formatCurrency' not found in {symbol_names}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_class_symbols_extracted(self):
        """JavaScript classes must be extracted as symbols."""
        from codebatch.tasks.parse import parse_javascript
        from codebatch.tasks.symbols import extract_js_symbols

        js_code = '''
class ShoppingCart {
    constructor() {
        this.items = [];
    }

    addItem(item) {
        this.items.push(item);
    }

    removeItem(index) {
        this.items.splice(index, 1);
    }
}
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")
        symbols, edges = extract_js_symbols(ast_dict, "test.js")

        symbol_names = [s["name"] for s in symbols if s["kind"] == "symbol"]
        assert "ShoppingCart" in symbol_names, f"Class 'ShoppingCart' not found in {symbol_names}"
        assert "addItem" in symbol_names, f"Method 'addItem' not found in {symbol_names}"
        assert "removeItem" in symbol_names, f"Method 'removeItem' not found in {symbol_names}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_variable_symbols_extracted(self):
        """JavaScript variables (const/let/var) must be extracted."""
        from codebatch.tasks.parse import parse_javascript
        from codebatch.tasks.symbols import extract_js_symbols

        js_code = '''
const API_KEY = "secret";
let counter = 0;
var legacyVar = "old";
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")
        symbols, edges = extract_js_symbols(ast_dict, "test.js")

        symbol_names = [s["name"] for s in symbols if s["kind"] == "symbol"]
        assert "API_KEY" in symbol_names, f"Const 'API_KEY' not found in {symbol_names}"
        assert "counter" in symbol_names, f"Let 'counter' not found in {symbol_names}"
        assert "legacyVar" in symbol_names, f"Var 'legacyVar' not found in {symbol_names}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_import_edges_extracted(self):
        """JavaScript imports must create edge records."""
        from codebatch.tasks.parse import parse_javascript
        from codebatch.tasks.symbols import extract_js_symbols

        js_code = '''
import React from 'react';
import { useState, useEffect } from 'react';
import * as utils from './utils';
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")
        symbols, edges = extract_js_symbols(ast_dict, "test.js")

        import_targets = [e["target"] for e in edges if e.get("edge_type") == "imports"]
        assert "react" in import_targets, f"Import 'react' not found in {import_targets}"
        assert "./utils" in import_targets, f"Import './utils' not found in {import_targets}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_js_class_inheritance_edge(self):
        """JavaScript class extends must create inheritance edge."""
        from codebatch.tasks.parse import parse_javascript
        from codebatch.tasks.symbols import extract_js_symbols

        js_code = '''
class Animal {
    speak() {}
}

class Dog extends Animal {
    bark() {}
}
'''.strip()

        ast_dict, _ = parse_javascript(js_code, "test.js")
        symbols, edges = extract_js_symbols(ast_dict, "test.js")

        inherit_targets = [e["target"] for e in edges if e.get("edge_type") == "inherits"]
        assert "Animal" in inherit_targets, f"Inheritance 'Animal' not found in {inherit_targets}"

    @pytest.mark.skipif(
        not _check_treesitter_available(),
        reason="tree-sitter not installed"
    )
    def test_ts_symbols_extracted(self):
        """TypeScript symbols must be extracted."""
        from codebatch.tasks.parse import parse_javascript
        from codebatch.tasks.symbols import extract_js_symbols

        ts_code = '''
interface User {
    id: number;
    name: string;
}

function greetUser(user: User): string {
    return `Hello, ${user.name}!`;
}

class UserService {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }
}
'''.strip()

        ast_dict, _ = parse_javascript(ts_code, "test.ts")
        symbols, edges = extract_js_symbols(ast_dict, "test.ts")

        symbol_names = [s["name"] for s in symbols if s["kind"] == "symbol"]
        assert "greetUser" in symbol_names, f"Function 'greetUser' not found in {symbol_names}"
        assert "UserService" in symbol_names, f"Class 'UserService' not found in {symbol_names}"
        assert "addUser" in symbol_names, f"Method 'addUser' not found in {symbol_names}"

    def test_js_symbols_fallback_mode(self):
        """Fallback mode should produce basic symbol info."""
        from codebatch.tasks.symbols import extract_js_symbols_fallback

        token_data = {
            "type": "TokenInfo",
            "ast_mode": "tokens",
            "parser": "regex-fallback",
            "tokens": {"keyword": 5, "identifier": 10},
        }

        symbols, edges = extract_js_symbols_fallback(token_data, "test.js")

        # Should have at least a module symbol
        assert len(symbols) >= 1
        assert symbols[0]["symbol_type"] == "module"


class TestGateP8LintAst:
    """P8-LINT-AST: AST-aware linting must detect semantic issues."""

    def test_unused_import_detected(self):
        """Must detect unused imports."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.lint import lint_unused_imports

        code = '''
import os
import sys
from pathlib import Path

def main():
    print(sys.argv)
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        diagnostics = lint_unused_imports(ast_dict, "test.py")

        # Should detect os and Path as unused
        unused_names = [d["message"] for d in diagnostics]
        assert any("'os'" in msg for msg in unused_names), f"Unused 'os' not detected: {unused_names}"
        assert any("'Path'" in msg for msg in unused_names), f"Unused 'Path' not detected: {unused_names}"

        # sys should NOT be flagged (it's used)
        assert not any("'sys'" in msg for msg in unused_names), f"'sys' incorrectly flagged as unused"

    def test_used_import_not_flagged(self):
        """Used imports should not be flagged."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.lint import lint_unused_imports

        code = '''
import json
from typing import List, Dict

def serialize(data: Dict) -> str:
    items: List[str] = []
    return json.dumps(data)
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        diagnostics = lint_unused_imports(ast_dict, "test.py")

        # All imports are used
        assert len(diagnostics) == 0, f"False positives: {diagnostics}"

    def test_unused_variable_detected(self):
        """Must detect unused variables."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.lint import lint_unused_variables

        code = '''
def process():
    x = 1
    y = 2
    z = 3
    return z
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        diagnostics = lint_unused_variables(ast_dict, "test.py")

        # x and y are unused
        unused_names = [d["message"] for d in diagnostics]
        assert any("'x'" in msg for msg in unused_names), f"Unused 'x' not detected: {unused_names}"
        assert any("'y'" in msg for msg in unused_names), f"Unused 'y' not detected: {unused_names}"

        # z is used
        assert not any("'z'" in msg for msg in unused_names), f"'z' incorrectly flagged as unused"

    def test_underscore_variable_not_flagged(self):
        """Variables starting with _ should not be flagged."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.lint import lint_unused_variables

        code = '''
def process():
    _unused = get_value()
    _ = ignored()
    __dunder = special()
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        diagnostics = lint_unused_variables(ast_dict, "test.py")

        # Underscore-prefixed variables are intentionally unused
        assert len(diagnostics) == 0, f"False positives for underscore vars: {diagnostics}"

    def test_variable_shadowing_detected(self):
        """Must detect variable shadowing."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.lint import lint_variable_shadowing

        code = '''
x = 10

def outer():
    x = 20

    def inner():
        x = 30
        return x

    return inner()
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        diagnostics = lint_variable_shadowing(ast_dict, "test.py")

        # Should detect shadowing
        assert len(diagnostics) >= 1, f"No shadowing detected: {diagnostics}"
        assert any("shadows" in d["message"].lower() for d in diagnostics)

    def test_lint_python_ast_integration(self):
        """lint_python_ast should run all AST rules."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.lint import lint_python_ast

        code = '''
import os

def process():
    x = 1
    return 42
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        diagnostics = lint_python_ast(ast_dict, "test.py", {})

        # Should have both L101 (unused import) and L102 (unused variable)
        codes = [d["code"] for d in diagnostics]
        assert "L101" in codes, f"L101 not in {codes}"
        assert "L102" in codes, f"L102 not in {codes}"

    def test_lint_executor_uses_ast_rules(self, tmp_path):
        """lint_executor should use AST rules when AST available."""
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.lint import lint_executor

        # Create test corpus with unused import
        corpus = tmp_path / "corpus"
        corpus.mkdir()

        test_file = corpus / "test.py"
        test_file.write_text('''
import os
import sys

print(sys.version)
'''.strip())

        # Initialize store and create snapshot
        store = tmp_path / "store"
        init_store(store)

        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run parse first (lint depends on parse output)
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "04_lint", shard_id, lint_executor)

        # Query lint outputs
        from codebatch.query import QueryEngine
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "04_lint")

        diagnostics = [o for o in all_outputs if o.get("kind") == "diagnostic"]
        codes = [d.get("code") for d in diagnostics]

        # Should have L101 for unused 'os' import
        assert "L101" in codes, f"L101 not found in lint output. Codes: {codes}"


class TestGateP8Metrics:
    """P8-METRICS: Analyze task must produce cyclomatic complexity."""

    def test_simple_complexity(self):
        """Simple function should have complexity 1."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.analyze import calculate_function_complexity

        code = '''
def simple():
    return 42
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        func_node = ast_dict["body"][0]

        complexity = calculate_function_complexity(func_node)
        assert complexity == 1, f"Simple function should have complexity 1, got {complexity}"

    def test_if_statement_complexity(self):
        """If statement increases complexity."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.analyze import calculate_function_complexity

        code = '''
def conditional(x):
    if x > 0:
        return "positive"
    return "non-positive"
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        func_node = ast_dict["body"][0]

        complexity = calculate_function_complexity(func_node)
        assert complexity == 2, f"Expected complexity 2 (1 base + 1 if), got {complexity}"

    def test_nested_if_complexity(self):
        """Nested if statements add complexity."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.analyze import calculate_function_complexity

        code = '''
def nested(x):
    if x > 0:
        if x > 10:
            return "large"
        return "small"
    return "negative"
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        func_node = ast_dict["body"][0]

        complexity = calculate_function_complexity(func_node)
        assert complexity == 3, f"Expected complexity 3 (1 base + 2 ifs), got {complexity}"

    def test_loop_complexity(self):
        """Loops increase complexity."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.analyze import calculate_function_complexity

        code = '''
def loopy(items):
    for item in items:
        while item > 0:
            item -= 1
    return items
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        func_node = ast_dict["body"][0]

        complexity = calculate_function_complexity(func_node)
        assert complexity == 3, f"Expected complexity 3 (1 base + 1 for + 1 while), got {complexity}"

    def test_boolean_ops_complexity(self):
        """Boolean operators increase complexity."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.analyze import calculate_function_complexity

        code = '''
def check(a, b, c):
    if a and b or c:
        return True
    return False
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        func_node = ast_dict["body"][0]

        complexity = calculate_function_complexity(func_node)
        # 1 base + 1 if + 2 (and, or)
        assert complexity == 4, f"Expected complexity 4, got {complexity}"

    def test_extract_complexity_metrics(self):
        """extract_complexity_metrics should produce all metrics."""
        from codebatch.tasks.parse import parse_python
        from codebatch.tasks.analyze import extract_complexity_metrics

        code = '''
import os
import sys

class Calculator:
    def add(self, a, b):
        return a + b

    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b

def main():
    calc = Calculator()
    print(calc.add(1, 2))
'''.strip()

        ast_dict, _ = parse_python(code, "test.py")
        metrics = extract_complexity_metrics(ast_dict, "test.py")

        # Convert to dict for easy lookup
        metrics_dict = {m["metric"]: m["value"] for m in metrics}

        assert "complexity" in metrics_dict
        assert "max_complexity" in metrics_dict
        assert "function_count" in metrics_dict
        assert "class_count" in metrics_dict
        assert "import_count" in metrics_dict

        assert metrics_dict["class_count"] == 1, f"Expected 1 class, got {metrics_dict['class_count']}"
        assert metrics_dict["function_count"] == 3, f"Expected 3 functions (add, divide, main), got {metrics_dict['function_count']}"
        assert metrics_dict["import_count"] == 2, f"Expected 2 imports, got {metrics_dict['import_count']}"
        assert metrics_dict["max_complexity"] == 2, f"Expected max complexity 2 (divide has if), got {metrics_dict['max_complexity']}"

    def test_analyze_executor_produces_complexity(self, tmp_path):
        """analyze_executor should produce complexity metrics."""
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.analyze import analyze_executor

        # Create test corpus
        corpus = tmp_path / "corpus"
        corpus.mkdir()

        test_file = corpus / "test.py"
        test_file.write_text('''
def process(items):
    for item in items:
        if item > 0:
            print(item)
'''.strip())

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(corpus)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run parse first, then analyze
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)

        # Query analyze outputs
        from codebatch.query import QueryEngine
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "02_analyze")

        metrics = [o for o in all_outputs if o.get("kind") == "metric"]
        metric_names = [m.get("metric") for m in metrics]

        # Should have complexity metric
        assert "complexity" in metric_names, f"complexity not found in {metric_names}"

        # Find complexity value
        complexity_metric = next(m for m in metrics if m.get("metric") == "complexity")
        # 1 base + 1 for + 1 if = 3
        assert complexity_metric["value"] == 3, f"Expected complexity 3, got {complexity_metric['value']}"


class TestGateP8SelfHost:
    """P8-SELF-HOST: CodeBatch must analyze its own source meaningfully."""

    def test_self_analysis_produces_symbols(self, tmp_path):
        """Analyzing codebatch source must produce real symbols."""
        import re
        from pathlib import Path
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.query import QueryEngine
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.symbols import symbols_executor

        # Find the codebatch source directory
        src_dir = Path(__file__).parent.parent / "src" / "codebatch"
        assert src_dir.exists(), f"Source directory not found: {src_dir}"

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        # Create snapshot of codebatch source
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(src_dir)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards with files
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run parse and symbols tasks
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        # Query symbols
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "03_symbols")

        symbols = [o for o in all_outputs if o.get("kind") == "symbol"]
        symbol_names = [s.get("name") for s in symbols]

        # Must have at least 50 symbols (functions, classes, variables)
        assert len(symbols) >= 50, f"Expected at least 50 symbols, got {len(symbols)}"

        # Must include real function names from codebatch source
        # These are known functions that should exist
        expected_functions = [
            "init_store",  # store.py
            "parse_python",  # tasks/parse.py
            "symbols_executor",  # tasks/symbols.py
        ]

        for func_name in expected_functions:
            assert func_name in symbol_names, f"Expected function '{func_name}' not found in symbols"

        # Must NOT have placeholder names
        placeholder_pattern = re.compile(r'^(function|class|variable|module)_\d+$')
        placeholders = [name for name in symbol_names if placeholder_pattern.match(str(name))]
        assert len(placeholders) == 0, f"Found placeholder symbols: {placeholders[:10]}"

    def test_self_analysis_produces_imports(self, tmp_path):
        """Analyzing codebatch source must produce import edges."""
        from pathlib import Path
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.query import QueryEngine
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.symbols import symbols_executor

        # Find the codebatch source directory
        src_dir = Path(__file__).parent.parent / "src" / "codebatch"

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        # Create snapshot
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(src_dir)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run parse and symbols
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        # Query outputs
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "03_symbols")

        edges = [o for o in all_outputs if o.get("kind") == "edge"]
        import_edges = [e for e in edges if e.get("edge_type") == "imports"]
        import_targets = [e.get("target") for e in import_edges]

        # Must have import edges
        assert len(import_edges) >= 10, f"Expected at least 10 import edges, got {len(import_edges)}"

        # Must include real module imports
        expected_imports = ["json", "typing"]
        for imp in expected_imports:
            # Check if any import target starts with or equals the expected
            found = any(t == imp or (t and t.startswith(f"{imp}.")) for t in import_targets)
            assert found, f"Expected import '{imp}' not found in imports"

    def test_self_analysis_produces_metrics(self, tmp_path):
        """Analyzing codebatch source must produce real metrics."""
        from pathlib import Path
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.query import QueryEngine
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.analyze import analyze_executor

        # Find the codebatch source directory
        src_dir = Path(__file__).parent.parent / "src" / "codebatch"

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        # Create snapshot
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(src_dir)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run parse and analyze
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)

        # Query outputs
        engine = QueryEngine(store)
        all_outputs = engine.query_outputs(batch_id, "02_analyze")

        metrics = [o for o in all_outputs if o.get("kind") == "metric"]
        metric_types = set(m.get("metric") for m in metrics)

        # Must have complexity metrics
        assert "complexity" in metric_types, f"complexity not in {metric_types}"
        assert "function_count" in metric_types, f"function_count not in {metric_types}"
        assert "class_count" in metric_types, f"class_count not in {metric_types}"

        # Get total complexity
        complexity_metrics = [m for m in metrics if m.get("metric") == "complexity"]
        total_complexity = sum(m.get("value", 0) for m in complexity_metrics)

        # Codebatch source should have non-trivial complexity
        assert total_complexity >= 20, f"Expected complexity >= 20, got {total_complexity}"

    def test_full_pipeline_end_to_end(self, tmp_path):
        """Full pipeline must complete successfully on codebatch source."""
        from pathlib import Path
        from codebatch.store import init_store
        from codebatch.snapshot import SnapshotBuilder
        from codebatch.batch import BatchManager
        from codebatch.runner import ShardRunner
        from codebatch.query import QueryEngine
        from codebatch.common import object_shard_prefix
        from codebatch.tasks.parse import parse_executor
        from codebatch.tasks.analyze import analyze_executor
        from codebatch.tasks.symbols import symbols_executor
        from codebatch.tasks.lint import lint_executor

        # Find the codebatch source directory
        src_dir = Path(__file__).parent.parent / "src" / "codebatch"

        # Initialize store
        store = tmp_path / "store"
        init_store(store)

        # Create snapshot
        builder = SnapshotBuilder(store)
        snapshot_id = builder.build(src_dir)

        batch_mgr = BatchManager(store)
        batch_id = batch_mgr.init_batch(snapshot_id, pipeline="full")

        # Get shards
        records = builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        # Run all tasks in order
        runner = ShardRunner(store)
        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "02_analyze", shard_id, analyze_executor)
            runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)
            runner.run_shard(batch_id, "04_lint", shard_id, lint_executor)

        # Query all task outputs
        engine = QueryEngine(store)

        parse_outputs = engine.query_outputs(batch_id, "01_parse")
        analyze_outputs = engine.query_outputs(batch_id, "02_analyze")
        symbol_outputs = engine.query_outputs(batch_id, "03_symbols")
        lint_outputs = engine.query_outputs(batch_id, "04_lint")

        # All tasks should produce outputs
        assert len(parse_outputs) > 0, "No parse outputs"
        assert len(analyze_outputs) > 0, "No analyze outputs"
        assert len(symbol_outputs) > 0, "No symbol outputs"
        assert len(lint_outputs) > 0, "No lint outputs"

        # Count different output types
        ast_count = sum(1 for o in parse_outputs if o.get("kind") == "ast")
        symbol_count = sum(1 for o in symbol_outputs if o.get("kind") == "symbol")
        metric_count = sum(1 for o in analyze_outputs if o.get("kind") == "metric")
        diagnostic_count = sum(1 for o in lint_outputs if o.get("kind") == "diagnostic")

        # Verify meaningful output counts
        assert ast_count > 0, "No AST outputs"
        assert symbol_count > 0, "No symbol outputs"
        assert metric_count > 0, "No metric outputs"
        # Lint diagnostics may or may not exist depending on code quality
        # Just verify we got the outputs

        print(f"Self-host analysis complete:")
        print(f"  AST outputs: {ast_count}")
        print(f"  Symbol outputs: {symbol_count}")
        print(f"  Metric outputs: {metric_count}")
        print(f"  Diagnostic outputs: {diagnostic_count}")
