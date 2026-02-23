"""Tests for error handling module (Phase 7).

Tests verify:
- Error envelope structure is correct
- Error codes are valid
- Factory functions produce correct errors
- JSON output is valid
"""

import json
import pytest

try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from codebatch.errors import (
    CodeBatchError,
    STORE_NOT_FOUND,
    STORE_INVALID,
    STORE_EXISTS,
    BATCH_NOT_FOUND,
    SNAPSHOT_NOT_FOUND,
    PIPELINE_NOT_FOUND,
    TASK_NOT_FOUND,
    GATE_NOT_FOUND,
    INVALID_ARGUMENT,
    FILE_NOT_FOUND,
    COMMAND_ERROR,
    INTERNAL_ERROR,
    store_not_found,
    store_invalid,
    store_exists,
    batch_not_found,
    snapshot_not_found,
    pipeline_not_found,
    task_not_found,
    gate_not_found,
    invalid_argument,
    file_not_found,
    command_error,
    internal_error,
    print_error,
)


class TestCodeBatchError:
    """Tests for CodeBatchError dataclass."""

    def test_to_dict_structure(self):
        """Error dict should have correct structure."""
        error = CodeBatchError(
            code="TEST_ERROR",
            message="Test message",
            hints=["Hint 1", "Hint 2"],
            details={"key": "value"},
        )

        result = error.to_dict()

        assert "error" in result
        assert result["error"]["code"] == "TEST_ERROR"
        assert result["error"]["message"] == "Test message"
        assert result["error"]["hints"] == ["Hint 1", "Hint 2"]
        assert result["error"]["details"] == {"key": "value"}

    def test_to_dict_empty_hints_and_details(self):
        """Error dict should handle empty hints and details."""
        error = CodeBatchError(
            code="TEST_ERROR",
            message="Test message",
        )

        result = error.to_dict()

        assert result["error"]["hints"] == []
        assert result["error"]["details"] == {}

    def test_to_json_valid(self):
        """Error JSON should be valid."""
        error = CodeBatchError(
            code="TEST_ERROR",
            message="Test message",
        )

        json_str = error.to_json()
        parsed = json.loads(json_str)

        assert parsed["error"]["code"] == "TEST_ERROR"

    def test_to_json_deterministic(self):
        """Error JSON should be deterministic."""
        error = CodeBatchError(
            code="TEST_ERROR",
            message="Test message",
            hints=["Hint 1"],
            details={"key": "value"},
        )

        json1 = error.to_json()
        json2 = error.to_json()

        assert json1 == json2


class TestErrorCodes:
    """Tests for error code constants."""

    def test_codes_are_uppercase(self):
        """All error codes should be uppercase."""
        codes = [
            STORE_NOT_FOUND,
            STORE_INVALID,
            STORE_EXISTS,
            BATCH_NOT_FOUND,
            SNAPSHOT_NOT_FOUND,
            PIPELINE_NOT_FOUND,
            TASK_NOT_FOUND,
            GATE_NOT_FOUND,
            INVALID_ARGUMENT,
            FILE_NOT_FOUND,
            COMMAND_ERROR,
            INTERNAL_ERROR,
        ]

        for code in codes:
            assert code == code.upper(), f"Code not uppercase: {code}"
            assert "_" in code or code.isalpha(), f"Invalid code format: {code}"


class TestFactoryFunctions:
    """Tests for error factory functions."""

    def test_store_not_found(self):
        """store_not_found should create correct error."""
        error = store_not_found("/path/to/store")

        assert error.code == STORE_NOT_FOUND
        assert "/path/to/store" in error.message
        assert error.details["path"] == "/path/to/store"
        assert len(error.hints) > 0

    def test_store_invalid(self):
        """store_invalid should create correct error."""
        error = store_invalid("/path/to/store", "missing store.json")

        assert error.code == STORE_INVALID
        assert "/path/to/store" in error.message
        assert "missing store.json" in error.message
        assert error.details["reason"] == "missing store.json"

    def test_store_exists(self):
        """store_exists should create correct error."""
        error = store_exists("/path/to/store")

        assert error.code == STORE_EXISTS
        assert "/path/to/store" in error.message

    def test_batch_not_found(self):
        """batch_not_found should create correct error."""
        error = batch_not_found("batch-123", "/path/to/store")

        assert error.code == BATCH_NOT_FOUND
        assert "batch-123" in error.message
        assert error.details["batch_id"] == "batch-123"
        assert error.details["store"] == "/path/to/store"

    def test_batch_not_found_without_store(self):
        """batch_not_found should work without store."""
        error = batch_not_found("batch-123")

        assert error.code == BATCH_NOT_FOUND
        assert error.details["batch_id"] == "batch-123"
        assert "store" not in error.details

    def test_snapshot_not_found(self):
        """snapshot_not_found should create correct error."""
        error = snapshot_not_found("snap-123")

        assert error.code == SNAPSHOT_NOT_FOUND
        assert "snap-123" in error.message

    def test_pipeline_not_found(self):
        """pipeline_not_found should create correct error."""
        error = pipeline_not_found("nonexistent")

        assert error.code == PIPELINE_NOT_FOUND
        assert "nonexistent" in error.message

    def test_task_not_found(self):
        """task_not_found should create correct error."""
        error = task_not_found("99_unknown")

        assert error.code == TASK_NOT_FOUND
        assert "99_unknown" in error.message

    def test_gate_not_found(self):
        """gate_not_found should create correct error."""
        error = gate_not_found("P99-G99")

        assert error.code == GATE_NOT_FOUND
        assert "P99-G99" in error.message

    def test_invalid_argument(self):
        """invalid_argument should create correct error."""
        error = invalid_argument("--batch", "invalid!", "must be alphanumeric")

        assert error.code == INVALID_ARGUMENT
        assert "--batch" in error.message
        assert "invalid!" in error.message
        assert error.details["argument"] == "--batch"
        assert error.details["value"] == "invalid!"

    def test_file_not_found(self):
        """file_not_found should create correct error."""
        error = file_not_found("/path/to/file.py")

        assert error.code == FILE_NOT_FOUND
        assert "/path/to/file.py" in error.message

    def test_command_error(self):
        """command_error should create correct error."""
        error = command_error("Something went wrong", {"context": "value"})

        assert error.code == COMMAND_ERROR
        assert "Something went wrong" in error.message
        assert error.details["context"] == "value"

    def test_internal_error(self):
        """internal_error should create correct error."""
        error = internal_error("Unexpected state")

        assert error.code == INTERNAL_ERROR
        assert "Unexpected state" in error.message
        assert "report" in error.hints[0].lower()


class TestPrintError:
    """Tests for print_error function."""

    def test_json_mode(self, capsys):
        """print_error with json_mode should output JSON."""
        error = CodeBatchError(code="TEST", message="Test")

        # Redirect to stdout for easier capture
        import sys

        print_error(error, json_mode=True, file=sys.stdout)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["error"]["code"] == "TEST"

    def test_text_mode(self, capsys):
        """print_error without json_mode should output text."""
        error = CodeBatchError(
            code="TEST",
            message="Test message",
            hints=["Do something"],
        )

        import sys

        print_error(error, json_mode=False, file=sys.stdout)

        captured = capsys.readouterr()
        assert "Error: Test message" in captured.out
        assert "Hint: Do something" in captured.out


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestErrorSchemaValidation:
    """Tests for error schema validation."""

    @pytest.fixture
    def error_schema(self):
        """Load the error schema."""
        from pathlib import Path

        schema_path = Path(__file__).parent.parent / "schemas" / "error.schema.json"
        if not schema_path.exists():
            pytest.skip("Error schema not found")
        with open(schema_path) as f:
            return json.load(f)

    def test_error_validates_against_schema(self, error_schema):
        """Error envelope should validate against schema."""
        error = CodeBatchError(
            code="TEST_ERROR",
            message="Test message",
            hints=["Hint 1"],
            details={"key": "value"},
        )

        jsonschema.validate(error.to_dict(), error_schema)

    def test_minimal_error_validates(self, error_schema):
        """Minimal error (code + message only) should validate."""
        error = CodeBatchError(code="TEST", message="Test")

        jsonschema.validate(error.to_dict(), error_schema)

    @pytest.mark.parametrize(
        "factory",
        [
            lambda: store_not_found("/path"),
            lambda: store_invalid("/path", "reason"),
            lambda: store_exists("/path"),
            lambda: batch_not_found("batch-123"),
            lambda: snapshot_not_found("snap-123"),
            lambda: pipeline_not_found("pipe"),
            lambda: task_not_found("task"),
            lambda: gate_not_found("gate"),
            lambda: invalid_argument("arg", "val"),
            lambda: file_not_found("/file"),
            lambda: command_error("msg"),
            lambda: internal_error("msg"),
        ],
    )
    def test_all_factories_validate(self, error_schema, factory):
        """All factory-created errors should validate against schema."""
        error = factory()
        jsonschema.validate(error.to_dict(), error_schema)
