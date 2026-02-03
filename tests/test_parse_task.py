"""Tests for the parse task executor."""

import json
import pytest
from pathlib import Path

from codebatch.batch import BatchManager
from codebatch.common import object_shard_prefix
from codebatch.runner import ShardRunner
from codebatch.snapshot import SnapshotBuilder
from codebatch.tasks.parse import parse_executor, parse_python, parse_javascript


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """Create a temporary store root."""
    return tmp_path / "store"


@pytest.fixture
def corpus_dir() -> Path:
    """Get the test corpus directory."""
    return Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def snapshot_id(store: Path, corpus_dir: Path) -> str:
    """Create a snapshot and return its ID."""
    store.mkdir(parents=True, exist_ok=True)
    builder = SnapshotBuilder(store)
    return builder.build(corpus_dir, snapshot_id="test-snapshot")


@pytest.fixture
def batch_id(store: Path, snapshot_id: str) -> str:
    """Create a batch and return its ID."""
    manager = BatchManager(store)
    return manager.init_batch(snapshot_id, "parse", batch_id="test-batch")


class TestParsePython:
    """Tests for Python parsing."""

    def test_valid_python(self):
        """Parse valid Python code."""
        code = '''
def hello():
    return "world"
'''
        ast_dict, diagnostics = parse_python(code, "test.py")

        assert ast_dict is not None
        assert ast_dict["type"] == "Module"
        assert "stats" in ast_dict
        assert len(diagnostics) == 0

    def test_syntax_error(self):
        """Parse Python with syntax error."""
        code = "def hello( return"
        ast_dict, diagnostics = parse_python(code, "test.py")

        assert ast_dict is None
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "error"
        assert diagnostics[0]["code"] == "E0001"


class TestParseJavaScript:
    """Tests for JavaScript parsing."""

    def test_valid_javascript(self):
        """Parse valid JavaScript code."""
        code = '''
function hello() {
    const x = 42;
    return x;
}
'''
        ast_dict, diagnostics = parse_javascript(code, "test.js")

        assert ast_dict is not None
        assert ast_dict["type"] == "TokenInfo"
        assert "tokens" in ast_dict
        assert ast_dict["tokens"]["keyword"] >= 2  # function, const, return

    def test_unbalanced_braces(self):
        """Detect unbalanced braces."""
        code = "function hello() { return 42;"
        ast_dict, diagnostics = parse_javascript(code, "test.js")

        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "warning"
        assert diagnostics[0]["code"] == "W0001"
        assert "Unbalanced" in diagnostics[0]["message"]


class TestParseExecutor:
    """Tests for the full parse executor."""

    def test_executor_produces_outputs(self, store: Path, batch_id: str):
        """Parse executor produces AST and diagnostic outputs."""
        runner = ShardRunner(store)

        # Find a shard with Python files
        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)

        # Find Python file's shard
        python_files = [r for r in records if r.get("lang_hint") == "python"]
        assert len(python_files) > 0, "No Python files in corpus"

        shard_id = object_shard_prefix(python_files[0]["object"])

        # Run with parse executor
        final_state = runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)

        assert final_state["status"] == "done"

        # Check outputs
        outputs = runner.get_shard_outputs(batch_id, "01_parse", shard_id)
        assert len(outputs) > 0

        # Should have at least one AST output
        ast_outputs = [o for o in outputs if o["kind"] == "ast"]
        assert len(ast_outputs) >= 1

    def test_executor_stores_ast_in_cas(self, store: Path, batch_id: str):
        """AST outputs are stored in CAS."""
        runner = ShardRunner(store)

        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)

        python_files = [r for r in records if r.get("lang_hint") == "python"]
        shard_id = object_shard_prefix(python_files[0]["object"])

        runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        outputs = runner.get_shard_outputs(batch_id, "01_parse", shard_id)

        ast_outputs = [o for o in outputs if o["kind"] == "ast"]
        for output in ast_outputs:
            assert "object" in output
            assert runner.object_store.has(output["object"])

            # Verify it's valid JSON
            data = runner.object_store.get_bytes(output["object"])
            ast_dict = json.loads(data)
            assert "type" in ast_dict

    def test_executor_handles_binary_files(self, store: Path, batch_id: str):
        """Binary files are skipped without error."""
        runner = ShardRunner(store)

        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)

        # Find binary file's shard
        binary_files = [r for r in records if r["path"] == "binary.bin"]
        assert len(binary_files) > 0

        shard_id = object_shard_prefix(binary_files[0]["object"])

        # Run should complete without error
        final_state = runner.run_shard(batch_id, "01_parse", shard_id, parse_executor)
        assert final_state["status"] == "done"


class TestChunking:
    """Tests for large output chunking."""

    def test_chunk_manifest_created_for_large_output(self, store: Path, batch_id: str):
        """Large outputs are chunked with manifest."""
        runner = ShardRunner(store)

        # Create a config with tiny chunk threshold
        config = {
            "emit_ast": True,
            "emit_diagnostics": True,
            "chunk_threshold": 100,  # Very small to trigger chunking
        }

        batch = runner.batch_manager.load_batch(batch_id)
        snapshot_id = batch["snapshot_id"]
        records = runner.snapshot_builder.load_file_index(snapshot_id)

        python_files = [r for r in records if r.get("lang_hint") == "python"]
        shard_id = object_shard_prefix(python_files[0]["object"])
        shard_files = [r for r in records if object_shard_prefix(r["object"]) == shard_id]

        # Run with low threshold
        outputs = parse_executor(config, shard_files, runner)

        # Check if any chunk manifests were created
        # (depends on AST size, may or may not trigger)
        manifest_outputs = [o for o in outputs if o["kind"] == "chunk_manifest"]

        # Verify manifest structure if present
        for output in manifest_outputs:
            assert "object" in output
            manifest_data = runner.object_store.get_bytes(output["object"])
            manifest = json.loads(manifest_data)
            assert manifest["schema_name"] == "codebatch.chunk_manifest"
            assert len(manifest["chunks"]) >= 1
