"""Tests for the symbols task executor.

The symbols task extracts symbol tables and edges from AST:
- kind=symbol: Functions, classes, variables
- kind=edge: Import relationships
"""

import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.query import QueryEngine
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.parse import parse_executor
from codebatch.tasks.symbols import (
    symbols_executor,
    extract_python_symbols,
    extract_js_symbols,
)


@pytest.fixture
def clean_store(tmp_path: Path) -> Path:
    """Create a clean temporary store."""
    store = tmp_path / "store"
    store.mkdir()
    return store


@pytest.fixture
def corpus_dir() -> Path:
    """Get the test corpus directory."""
    return Path(__file__).parent / "fixtures" / "corpus"


class TestExtractPythonSymbols:
    """Unit tests for Python symbol extraction.

    Phase 8: Updated to use full-fidelity AST with real names.
    """

    def test_extracts_function(self):
        """Extracts function definitions with real names."""
        ast_data = {
            "type": "Module",
            "ast_mode": "full",
            "body": [
                {
                    "type": "FunctionDef",
                    "name": "calculate_total",
                    "lineno": 5,
                    "col_offset": 0,
                    "args": {"args": []},
                    "body": [],
                },
            ],
        }
        symbols, edges = extract_python_symbols(ast_data, "test.py")

        assert len(symbols) == 1
        assert symbols[0]["symbol_type"] == "function"
        assert symbols[0]["name"] == "calculate_total"
        assert symbols[0]["line"] == 5

    def test_extracts_class(self):
        """Extracts class definitions with real names."""
        ast_data = {
            "type": "Module",
            "ast_mode": "full",
            "body": [
                {
                    "type": "ClassDef",
                    "name": "ShoppingCart",
                    "lineno": 10,
                    "col_offset": 0,
                    "bases": [],
                    "body": [],
                },
            ],
        }
        symbols, edges = extract_python_symbols(ast_data, "test.py")

        assert len(symbols) == 1
        assert symbols[0]["symbol_type"] == "class"
        assert symbols[0]["name"] == "ShoppingCart"
        assert symbols[0]["line"] == 10

    def test_extracts_import_edges(self):
        """Extracts import edges with real module names."""
        ast_data = {
            "type": "Module",
            "ast_mode": "full",
            "body": [
                {
                    "type": "Import",
                    "lineno": 1,
                    "col_offset": 0,
                    "names": [{"name": "os", "asname": None}],
                },
                {
                    "type": "ImportFrom",
                    "lineno": 2,
                    "col_offset": 0,
                    "module": "pathlib",
                    "names": [{"name": "Path", "asname": None}],
                },
            ],
        }
        symbols, edges = extract_python_symbols(ast_data, "test.py")

        assert len(edges) == 2
        assert edges[0]["edge_type"] == "imports"
        assert edges[0]["target"] == "os"
        assert edges[1]["edge_type"] == "imports"
        assert edges[1]["target"] == "pathlib.Path"

    def test_extracts_variable(self):
        """Extracts variable assignments with real names."""
        ast_data = {
            "type": "Module",
            "ast_mode": "full",
            "body": [
                {
                    "type": "Assign",
                    "lineno": 3,
                    "col_offset": 0,
                    "targets": [{"type": "Name", "id": "total"}],
                },
            ],
        }
        symbols, edges = extract_python_symbols(ast_data, "test.py")

        assert len(symbols) == 1
        assert symbols[0]["symbol_type"] == "variable"
        assert symbols[0]["name"] == "total"

    def test_extracts_nested_class_methods(self):
        """Extracts methods inside classes with proper scope."""
        ast_data = {
            "type": "Module",
            "ast_mode": "full",
            "body": [
                {
                    "type": "ClassDef",
                    "name": "Cart",
                    "lineno": 1,
                    "col_offset": 0,
                    "bases": [],
                    "body": [
                        {
                            "type": "FunctionDef",
                            "name": "add_item",
                            "lineno": 2,
                            "col_offset": 4,
                            "args": {"args": [{"arg": "self"}, {"arg": "item"}]},
                            "body": [],
                        },
                    ],
                },
            ],
        }
        symbols, edges = extract_python_symbols(ast_data, "test.py")

        # Should have class + method + parameter
        class_symbols = [s for s in symbols if s["symbol_type"] == "class"]
        method_symbols = [s for s in symbols if s["symbol_type"] == "function"]
        param_symbols = [s for s in symbols if s["symbol_type"] == "parameter"]

        assert len(class_symbols) == 1
        assert class_symbols[0]["name"] == "Cart"

        assert len(method_symbols) == 1
        assert method_symbols[0]["name"] == "add_item"
        assert method_symbols[0]["scope"] == "Cart"

        # 'item' parameter (self is excluded)
        assert len(param_symbols) == 1
        assert param_symbols[0]["name"] == "item"

    def test_extracts_inheritance_edges(self):
        """Extracts inheritance relationships as edges."""
        ast_data = {
            "type": "Module",
            "ast_mode": "full",
            "body": [
                {
                    "type": "ClassDef",
                    "name": "MyList",
                    "lineno": 1,
                    "col_offset": 0,
                    "bases": [{"type": "Name", "id": "list"}],
                    "body": [],
                },
            ],
        }
        symbols, edges = extract_python_symbols(ast_data, "test.py")

        inherit_edges = [e for e in edges if e["edge_type"] == "inherits"]
        assert len(inherit_edges) == 1
        assert inherit_edges[0]["target"] == "list"


class TestExtractJsSymbols:
    """Unit tests for JavaScript symbol extraction."""

    def test_extracts_module_symbol(self):
        """Extracts module symbol for JS files with keywords."""
        ast_data = {
            "type": "TokenInfo",
            "ast_mode": "tokens",
            "tokens": {"keyword": 5},
        }
        symbols, edges = extract_js_symbols(ast_data, "test.js")

        assert len(symbols) == 1
        assert symbols[0]["symbol_type"] == "module"

    def test_empty_for_no_keywords(self):
        """No symbols for JS files without keywords."""
        ast_data = {
            "type": "TokenInfo",
            "ast_mode": "tokens",
            "tokens": {"keyword": 0},
        }
        symbols, edges = extract_js_symbols(ast_data, "test.js")

        assert len(symbols) == 0


class TestSymbolsExecutor:
    """Tests for the symbols_executor function."""

    def test_produces_symbols(self, clean_store: Path, corpus_dir: Path):
        """Symbols task produces symbol records from Python AST."""
        # Setup
        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)

        # Find Python file shard
        python_records = [r for r in records if r.get("lang_hint") == "python"]
        if not python_records:
            pytest.skip("No Python files in corpus")

        shard_id = object_shard_prefix(python_records[0]["object"])

        # Run parse first
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        # Run symbols - need to add to batch first
        # For now, create a manual batch with symbols task
        from codebatch.batch import PIPELINES

        PIPELINES["parse_symbols"] = {
            "description": "Parse and extract symbols",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {
                    "task_id": "03_symbols",
                    "type": "symbols",
                    "depends_on": ["01_parse"],
                    "config": {},
                },
            ],
        }

        batch_id = batch_manager.init_batch(
            snapshot_id, "parse_symbols", batch_id="batch-symbols-test"
        )
        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        state = runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        assert state["status"] == "done"

        # Check outputs
        outputs = runner.get_shard_outputs(batch_id, "03_symbols", shard_id)

        # Should have some outputs (symbols or edges)
        symbol_outputs = [o for o in outputs if o.get("kind") == "symbol"]
        edge_outputs = [o for o in outputs if o.get("kind") == "edge"]

        assert len(symbol_outputs) > 0 or len(edge_outputs) > 0, (
            "No symbols or edges produced from Python file"
        )

    def test_symbols_have_required_fields(self, clean_store: Path, corpus_dir: Path):
        """Symbol records have all required fields."""
        from codebatch.batch import PIPELINES

        PIPELINES["parse_symbols"] = {
            "description": "Parse and extract symbols",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {
                    "task_id": "03_symbols",
                    "type": "symbols",
                    "depends_on": ["01_parse"],
                    "config": {},
                },
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_symbols")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        python_records = [r for r in records if r.get("lang_hint") == "python"]

        if not python_records:
            pytest.skip("No Python files in corpus")

        shard_id = object_shard_prefix(python_records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        outputs = runner.get_shard_outputs(batch_id, "03_symbols", shard_id)
        symbol_outputs = [o for o in outputs if o.get("kind") == "symbol"]

        for s in symbol_outputs:
            assert "path" in s, "Symbol missing path"
            assert "name" in s, "Symbol missing name"
            assert "symbol_type" in s, "Symbol missing symbol_type"
            assert "line" in s, "Symbol missing line"

    def test_edges_have_required_fields(self, clean_store: Path, corpus_dir: Path):
        """Edge records have all required fields."""
        from codebatch.batch import PIPELINES

        PIPELINES["parse_symbols"] = {
            "description": "Parse and extract symbols",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {
                    "task_id": "03_symbols",
                    "type": "symbols",
                    "depends_on": ["01_parse"],
                    "config": {},
                },
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_symbols")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        python_records = [r for r in records if r.get("lang_hint") == "python"]

        if not python_records:
            pytest.skip("No Python files in corpus")

        shard_id = object_shard_prefix(python_records[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        outputs = runner.get_shard_outputs(batch_id, "03_symbols", shard_id)
        edge_outputs = [o for o in outputs if o.get("kind") == "edge"]

        for e in edge_outputs:
            assert "path" in e, "Edge missing path"
            assert "edge_type" in e, "Edge missing edge_type"
            assert "target" in e, "Edge missing target"
            assert "line" in e, "Edge missing line"


class TestSymbolsIntegration:
    """Integration tests for symbols in the pipeline."""

    def test_join_query_files_with_symbols(self, clean_store: Path, corpus_dir: Path):
        """Can query files that have symbols vs those that don't."""
        from codebatch.batch import PIPELINES

        PIPELINES["parse_symbols"] = {
            "description": "Parse and extract symbols",
            "tasks": [
                {"task_id": "01_parse", "type": "parse", "config": {}},
                {
                    "task_id": "03_symbols",
                    "type": "symbols",
                    "depends_on": ["01_parse"],
                    "config": {},
                },
            ],
        }

        snapshot_builder = SnapshotBuilder(clean_store)
        snapshot_id = snapshot_builder.build(corpus_dir)

        batch_manager = BatchManager(clean_store)
        batch_id = batch_manager.init_batch(snapshot_id, "parse_symbols")

        runner = ShardRunner(clean_store)
        records = snapshot_builder.load_file_index(snapshot_id)
        shards_with_files = set(object_shard_prefix(r["object"]) for r in records)

        for shard_id in shards_with_files:
            runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
            runner.run_shard(batch_id, "03_symbols", shard_id, symbols_executor)

        # Query symbols
        engine = QueryEngine(clean_store)
        all_outputs = engine.query_outputs(batch_id, "03_symbols")

        # Group by path
        paths_with_symbols = set(
            o["path"] for o in all_outputs if o.get("kind") == "symbol"
        )
        paths_with_edges = set(
            o["path"] for o in all_outputs if o.get("kind") == "edge"
        )

        # At least some paths should have symbols or edges
        all_paths_with_output = paths_with_symbols | paths_with_edges
        assert len(all_paths_with_output) > 0, "No paths produced symbols or edges"
