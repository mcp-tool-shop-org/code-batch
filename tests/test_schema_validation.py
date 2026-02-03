"""Tests for schema validation of all record types."""

import json
import pytest
from pathlib import Path
import jsonschema


SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_schema(name: str) -> dict:
    """Load a schema by name."""
    path = SCHEMAS_DIR / f"{name}.schema.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestSnapshotSchema:
    """Tests for snapshot.json schema."""

    def test_valid_snapshot(self):
        """Valid snapshot validates."""
        schema = load_schema("snapshot")
        record = {
            "schema_name": "codebatch.snapshot",
            "schema_version": 1,
            "snapshot_id": "snap-123",
            "created_at": "2025-02-02T00:00:00Z",
            "source": {
                "type": "directory",
                "path": "/some/path"
            }
        }
        jsonschema.validate(record, schema)

    def test_missing_required_fails(self):
        """Missing required field fails validation."""
        schema = load_schema("snapshot")
        record = {
            "schema_name": "codebatch.snapshot",
            "schema_version": 1,
            # missing snapshot_id, created_at, source
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(record, schema)

    def test_unknown_fields_allowed(self):
        """Unknown fields are allowed (forward compatibility)."""
        schema = load_schema("snapshot")
        record = {
            "schema_name": "codebatch.snapshot",
            "schema_version": 1,
            "snapshot_id": "snap-123",
            "created_at": "2025-02-02T00:00:00Z",
            "source": {"type": "directory", "path": "/path"},
            "future_field": "some_value"  # unknown field
        }
        jsonschema.validate(record, schema)


class TestFilesIndexSchema:
    """Tests for files.index.jsonl record schema."""

    def test_valid_record(self):
        """Valid file record validates."""
        schema = load_schema("files-index-record")
        record = {
            "schema_version": 1,
            "path": "src/main.py",
            "path_key": "src/main.py",
            "object": "sha256:" + "a" * 64,
            "size": 100
        }
        jsonschema.validate(record, schema)

    def test_golden_records_validate(self):
        """Golden fixture records validate."""
        schema = load_schema("files-index-record")
        golden_path = FIXTURES_DIR / "golden" / "snapshot" / "files.index.jsonl"

        with open(golden_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    jsonschema.validate(record, schema)


class TestBatchSchema:
    """Tests for batch.json schema."""

    def test_valid_batch(self):
        """Valid batch validates."""
        schema = load_schema("batch")
        record = {
            "schema_name": "codebatch.batch",
            "schema_version": 1,
            "batch_id": "batch-123",
            "snapshot_id": "snap-123",
            "created_at": "2025-02-02T00:00:00Z",
            "pipeline": "parse"
        }
        jsonschema.validate(record, schema)


class TestTaskSchema:
    """Tests for task.json schema."""

    def test_valid_task(self):
        """Valid task validates."""
        schema = load_schema("task")
        record = {
            "schema_name": "codebatch.task",
            "schema_version": 1,
            "task_id": "01_parse",
            "batch_id": "batch-123",
            "type": "parse",
            "sharding": {
                "strategy": "hash_prefix",
                "shard_count": 256
            }
        }
        jsonschema.validate(record, schema)


class TestShardStateSchema:
    """Tests for state.json schema."""

    def test_valid_state(self):
        """Valid shard state validates."""
        schema = load_schema("state")
        record = {
            "schema_name": "codebatch.shard_state",
            "schema_version": 1,
            "shard_id": "ab",
            "task_id": "01_parse",
            "batch_id": "batch-123",
            "status": "ready"
        }
        jsonschema.validate(record, schema)

    def test_valid_status_values(self):
        """All valid status values validate."""
        schema = load_schema("state")
        base = {
            "schema_name": "codebatch.shard_state",
            "schema_version": 1,
            "shard_id": "ab",
            "task_id": "01_parse",
            "batch_id": "batch-123",
        }
        for status in ["ready", "running", "done", "failed"]:
            record = {**base, "status": status}
            jsonschema.validate(record, schema)


class TestOutputRecordSchema:
    """Tests for output record schema."""

    def test_valid_ast_output(self):
        """Valid AST output validates."""
        schema = load_schema("output-record")
        record = {
            "schema_version": 1,
            "snapshot_id": "snap-123",
            "batch_id": "batch-123",
            "task_id": "01_parse",
            "shard_id": "ab",
            "path": "src/main.py",
            "kind": "ast",
            "ts": "2025-02-02T00:00:00Z"
        }
        jsonschema.validate(record, schema)

    def test_valid_diagnostic_output(self):
        """Valid diagnostic output validates."""
        schema = load_schema("output-record")
        record = {
            "schema_version": 1,
            "snapshot_id": "snap-123",
            "batch_id": "batch-123",
            "task_id": "01_parse",
            "shard_id": "ab",
            "path": "src/main.py",
            "kind": "diagnostic",
            "ts": "2025-02-02T00:00:00Z",
            "severity": "error",
            "code": "E0001",
            "message": "Syntax error"
        }
        jsonschema.validate(record, schema)


class TestEventRecordSchema:
    """Tests for event record schema."""

    def test_valid_event(self):
        """Valid event validates."""
        schema = load_schema("event-record")
        record = {
            "schema_version": 1,
            "ts": "2025-02-02T00:00:00Z",
            "event": "shard_started",
            "batch_id": "batch-123",
            "task_id": "01_parse",
            "shard_id": "ab"
        }
        jsonschema.validate(record, schema)


class TestChunkManifestSchema:
    """Tests for chunk manifest schema."""

    def test_valid_manifest(self):
        """Valid chunk manifest validates."""
        schema = load_schema("chunk-manifest")
        record = {
            "schema_name": "codebatch.chunk_manifest",
            "schema_version": 1,
            "kind": "ast",
            "format": "json",
            "chunks": [
                {"object": "sha256:" + "a" * 64, "size": 1000, "index": 0},
                {"object": "sha256:" + "b" * 64, "size": 500, "index": 1}
            ],
            "total_bytes": 1500
        }
        jsonschema.validate(record, schema)
