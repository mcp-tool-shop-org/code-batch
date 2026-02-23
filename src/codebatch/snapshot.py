"""Snapshot builder for creating immutable snapshots of directory sources.

A snapshot represents a frozen view of an input source at a specific point in time.
Snapshots are immutable once written.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .cas import ObjectStore
from .common import SCHEMA_VERSION, PRODUCER, utc_now_z, SnapshotExistsError
from .paths import (
    canonicalize_path,
    compute_path_key,
    PathEscapeError,
    InvalidPathError,
    detect_case_collision,
)


# Language detection by extension
LANG_HINTS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
}


def detect_lang_hint(path: str) -> Optional[str]:
    """Detect language hint from file extension.

    Args:
        path: File path.

    Returns:
        Language hint string, or None if unknown.
    """
    ext = os.path.splitext(path)[1].lower()
    return LANG_HINTS.get(ext)


def generate_snapshot_id() -> str:
    """Generate a unique snapshot ID.

    Returns:
        Snapshot ID in format: snap-YYYYMMDD-HHMMSS-XXXX
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"snap-{timestamp}-{suffix}"


class SnapshotBuilder:
    """Builds immutable snapshots from directory sources."""

    def __init__(self, store_root: Path):
        """Initialize the snapshot builder.

        Args:
            store_root: Root directory of the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.object_store = ObjectStore(store_root)
        self.snapshots_dir = self.store_root / "snapshots"

    def _walk_directory(
        self,
        source_dir: Path,
        include_hidden: bool = False,
    ) -> Iterator[tuple[Path, str]]:
        """Walk a directory and yield (file_path, relative_path) pairs.

        Args:
            source_dir: Directory to walk.
            include_hidden: If True, include hidden files/dirs.

        Yields:
            Tuples of (absolute_path, relative_path).
        """
        source_dir = source_dir.resolve()

        for root, dirs, files in os.walk(source_dir):
            if not include_hidden:
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]

            root_path = Path(root)
            for file in files:
                # Skip hidden files unless configured
                if not include_hidden and file.startswith("."):
                    continue

                file_path = root_path / file
                try:
                    rel_path = file_path.relative_to(source_dir)
                    yield file_path, str(rel_path)
                except ValueError:
                    # File not under source_dir (shouldn't happen)
                    continue

    def build(
        self,
        source_dir: Path,
        snapshot_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        include_hidden: bool = False,
        allow_overwrite: bool = False,
    ) -> str:
        """Build a snapshot from a directory.

        Args:
            source_dir: Directory to snapshot.
            snapshot_id: Optional snapshot ID (auto-generated if not provided).
            metadata: Optional user metadata to include.
            include_hidden: If True, include hidden files/dirs.
            allow_overwrite: If True, allow overwriting existing snapshot (default False).

        Returns:
            The snapshot ID.

        Raises:
            SnapshotExistsError: If snapshot already exists and allow_overwrite=False.
            ValueError: If source is not a directory.
        """
        source_dir = Path(source_dir).resolve()

        if not source_dir.is_dir():
            raise ValueError(f"Source is not a directory: {source_dir}")

        if snapshot_id is None:
            snapshot_id = generate_snapshot_id()

        # Check for existing snapshot (immutability enforcement)
        # Fail if directory exists at all - even empty dirs indicate a prior attempt
        snapshot_dir = self.snapshots_dir / snapshot_id
        if snapshot_dir.exists() and not allow_overwrite:
            raise SnapshotExistsError(snapshot_id)

        # Create snapshot directory
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Collect file records and track diagnostics
        file_records = []
        skipped_files = []
        total_bytes = 0

        for file_path, rel_path in self._walk_directory(source_dir, include_hidden):
            try:
                # Canonicalize path
                canonical_path = canonicalize_path(rel_path)
                path_key = compute_path_key(canonical_path)

                # Read file and store in CAS
                data = file_path.read_bytes()
                object_ref = self.object_store.put_bytes(data)
                size = len(data)
                total_bytes += size

                # Build record
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "path": canonical_path,
                    "path_key": path_key,
                    "object": object_ref,
                    "size": size,
                }

                # Add optional fields
                lang_hint = detect_lang_hint(canonical_path)
                if lang_hint:
                    record["lang_hint"] = lang_hint

                file_records.append(record)

            except (PathEscapeError, InvalidPathError) as e:
                skipped_files.append(
                    {
                        "path": rel_path,
                        "reason": "invalid_path",
                        "message": str(e),
                    }
                )
            except OSError as e:
                skipped_files.append(
                    {
                        "path": rel_path,
                        "reason": "unreadable",
                        "message": str(e),
                    }
                )

        # Detect case collisions
        all_paths = [r["path"] for r in file_records]
        case_collisions = detect_case_collision(all_paths)
        collision_warnings = []
        for p1, p2 in case_collisions:
            collision_warnings.append(
                {
                    "paths": [p1, p2],
                    "reason": "case_collision",
                    "message": f"Paths differ only by case: {p1} vs {p2}",
                }
            )

        # Sort records by path_key for deterministic output
        file_records.sort(key=lambda r: r["path_key"])

        # Write files.index.jsonl
        index_path = snapshot_dir / "files.index.jsonl"
        with open(index_path, "w", encoding="utf-8") as f:
            for record in file_records:
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")

        # Write snapshot.json
        snapshot_meta = {
            "schema_name": "codebatch.snapshot",
            "schema_version": SCHEMA_VERSION,
            "producer": PRODUCER,
            "snapshot_id": snapshot_id,
            "created_at": utc_now_z(),
            "source": {
                "type": "directory",
                "path": str(source_dir),
            },
            "file_count": len(file_records),
            "total_bytes": total_bytes,
            "config": {
                "include_hidden": include_hidden,
            },
        }

        if metadata:
            snapshot_meta["metadata"] = metadata

        # Add warnings if any
        if skipped_files or collision_warnings:
            snapshot_meta["warnings"] = []
            snapshot_meta["warnings"].extend(skipped_files)
            snapshot_meta["warnings"].extend(collision_warnings)

        snapshot_json_path = snapshot_dir / "snapshot.json"
        with open(snapshot_json_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_meta, f, indent=2)

        return snapshot_id

    def load_snapshot(self, snapshot_id: str) -> dict:
        """Load snapshot metadata.

        Args:
            snapshot_id: Snapshot ID to load.

        Returns:
            Snapshot metadata dict.

        Raises:
            FileNotFoundError: If snapshot doesn't exist.
        """
        snapshot_path = self.snapshots_dir / snapshot_id / "snapshot.json"
        with open(snapshot_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_file_index(self, snapshot_id: str) -> list[dict]:
        """Load file index records.

        Args:
            snapshot_id: Snapshot ID to load.

        Returns:
            List of file index records.

        Raises:
            FileNotFoundError: If snapshot doesn't exist.
        """
        index_path = self.snapshots_dir / snapshot_id / "files.index.jsonl"
        records = []
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def iter_file_index(self, snapshot_id: str) -> Iterator[dict]:
        """Stream file index records without loading all into memory.

        Args:
            snapshot_id: Snapshot ID.

        Yields:
            File index record dicts.
        """
        index_path = self.snapshots_dir / snapshot_id / "files.index.jsonl"
        with open(index_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def list_snapshots(self) -> list[str]:
        """List all snapshot IDs.

        Returns:
            List of snapshot IDs.
        """
        if not self.snapshots_dir.exists():
            return []

        return [
            d.name
            for d in self.snapshots_dir.iterdir()
            if d.is_dir() and (d / "snapshot.json").exists()
        ]
