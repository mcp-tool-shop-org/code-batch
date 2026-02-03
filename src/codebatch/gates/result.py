"""Gate result types and dataclasses.

Defines the structured output format for gate runs.
"""

import platform
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json

from ..common import SCHEMA_VERSION


class GateStatus(Enum):
    """Gate enforcement status."""

    ENFORCED = "ENFORCED"  # Must pass; failure blocks releases
    HARNESS = "HARNESS"  # Has tests; may be promoted to ENFORCED
    PLACEHOLDER = "PLACEHOLDER"  # Defined but not yet implemented


@dataclass
class GateFailure:
    """A single failure within a gate run."""

    message: str
    location: Optional[str] = None  # File:line or identifier
    expected: Optional[str] = None
    actual: Optional[str] = None
    suggestion: Optional[str] = None  # Actionable fix suggestion

    def to_dict(self) -> dict:
        """Convert to dictionary, omitting None values."""
        result = {"message": self.message}
        if self.location:
            result["location"] = self.location
        if self.expected:
            result["expected"] = self.expected
        if self.actual:
            result["actual"] = self.actual
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


@dataclass
class GateContext:
    """Context provided to gate execution."""

    store_root: Path
    batch_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    task_ids: Optional[list[str]] = None
    cache_required: bool = False
    run_id: Optional[str] = None  # Unique ID for this gate run

    def to_dict(self) -> dict:
        """Convert to dictionary for result context."""
        result = {"store": str(self.store_root)}
        if self.batch_id:
            result["batch_id"] = self.batch_id
        if self.snapshot_id:
            result["snapshot_id"] = self.snapshot_id
        if self.task_ids:
            result["task_ids"] = self.task_ids
        if self.run_id:
            result["run_id"] = self.run_id
        return result

    def get_artifact_dir(self, gate_id: str) -> Path:
        """Get artifact directory for this gate run.

        Creates directory if it doesn't exist.
        Artifacts are stored at: indexes/gate_artifacts/<gate_id>/<run_id>/

        Args:
            gate_id: Gate identifier.

        Returns:
            Path to artifact directory.
        """
        if not self.run_id:
            import uuid
            self.run_id = str(uuid.uuid4())[:8]

        artifact_dir = (
            self.store_root / "indexes" / "gate_artifacts" / gate_id / self.run_id
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def write_artifact(self, gate_id: str, name: str, content: str) -> Path:
        """Write an artifact file.

        Args:
            gate_id: Gate identifier.
            name: Artifact filename (e.g., "diff.txt").
            content: File content.

        Returns:
            Path to written artifact.
        """
        artifact_dir = self.get_artifact_dir(gate_id)
        path = artifact_dir / name
        path.write_text(content)
        return path

    def write_artifact_json(self, gate_id: str, name: str, data: Any) -> Path:
        """Write a JSON artifact file.

        Args:
            gate_id: Gate identifier.
            name: Artifact filename (e.g., "report.json").
            data: JSON-serializable data.

        Returns:
            Path to written artifact.
        """
        artifact_dir = self.get_artifact_dir(gate_id)
        path = artifact_dir / name
        path.write_text(json.dumps(data, indent=2))
        return path


@dataclass
class GateEnvironment:
    """Runtime environment information."""

    os: str = field(default_factory=lambda: sys.platform)
    python: str = field(default_factory=lambda: platform.python_version())
    codebatch_version: str = "0.3.0"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "os": self.os,
            "python": self.python,
            "codebatch_version": self.codebatch_version,
        }


@dataclass
class GateResult:
    """Result of a gate run.

    This is the primary output of executing a gate.
    """

    gate_id: str
    passed: bool
    status: GateStatus = GateStatus.HARNESS
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    failures: list[GateFailure] = field(default_factory=list)
    environment: GateEnvironment = field(default_factory=GateEnvironment)
    context: Optional[GateContext] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "artifacts": self.artifacts,
            "failures": [f.to_dict() for f in self.failures],
            "environment": self.environment.to_dict(),
        }
        if self.context:
            result["context"] = self.context.to_dict()
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "GateResult":
        """Create from dictionary."""
        failures = [
            GateFailure(
                message=f["message"],
                location=f.get("location"),
                expected=f.get("expected"),
                actual=f.get("actual"),
                suggestion=f.get("suggestion"),
            )
            for f in data.get("failures", [])
        ]

        env_data = data.get("environment", {})
        environment = GateEnvironment(
            os=env_data.get("os", sys.platform),
            python=env_data.get("python", platform.python_version()),
            codebatch_version=env_data.get("codebatch_version", "0.3.0"),
        )

        context = None
        if "context" in data:
            ctx = data["context"]
            context = GateContext(
                store_root=Path(ctx["store"]),
                batch_id=ctx.get("batch_id"),
                snapshot_id=ctx.get("snapshot_id"),
                task_ids=ctx.get("task_ids"),
            )

        return cls(
            gate_id=data["gate_id"],
            passed=data["passed"],
            status=GateStatus(data.get("status", "HARNESS")),
            duration_ms=data.get("duration_ms", 0),
            details=data.get("details", {}),
            artifacts=data.get("artifacts", []),
            failures=failures,
            environment=environment,
            context=context,
        )

    def add_failure(
        self,
        message: str,
        location: Optional[str] = None,
        expected: Optional[str] = None,
        actual: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """Add a failure to the result."""
        self.failures.append(
            GateFailure(
                message=message,
                location=location,
                expected=expected,
                actual=actual,
                suggestion=suggestion,
            )
        )
        self.passed = False


@dataclass
class BundleResult:
    """Result of running a gate bundle."""

    bundle_name: str
    passed: bool
    total: int
    passed_count: int
    failed_count: int
    skipped_count: int
    duration_ms: int
    results: list[GateResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "bundle_name": self.bundle_name,
            "passed": self.passed,
            "total": self.total,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "duration_ms": self.duration_ms,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# Gate result JSON schema version
GATE_RESULT_SCHEMA_VERSION = 1
