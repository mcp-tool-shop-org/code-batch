"""Content-Addressed Storage (CAS) object store.

Objects are stored at: objects/sha256/<aa>/<bb>/<full_hash>
Where <aa> and <bb> are the first two byte pairs of the hex hash.

Object references use canonical format: sha256:<hex>
"""

import hashlib
import os
from pathlib import Path
from typing import Optional

from .common import parse_object_ref, make_object_ref


class ObjectNotFoundError(Exception):
    """Raised when an object is not found in the store."""

    def __init__(self, object_ref: str):
        self.object_ref = object_ref
        super().__init__(f"Object not found: {object_ref}")


class ObjectStore:
    """Content-addressed object store using SHA-256."""

    def __init__(self, store_root: Path):
        """Initialize the object store.

        Args:
            store_root: Root directory of the CodeBatch store.
        """
        self.store_root = Path(store_root)
        self.objects_dir = self.store_root / "objects" / "sha256"

    def _hex_to_path(self, hex_hash: str) -> Path:
        """Get the filesystem path for a hex hash.

        Args:
            hex_hash: SHA-256 hex hash (64 characters).

        Returns:
            Path to the object file.
        """
        aa = hex_hash[:2]
        bb = hex_hash[2:4]
        return self.objects_dir / aa / bb / hex_hash

    def _object_path(self, object_ref: str) -> Path:
        """Get the filesystem path for an object reference.

        Args:
            object_ref: Object reference (sha256:<hex> or legacy bare hex).

        Returns:
            Path to the object file.

        Raises:
            ValueError: If object reference is invalid.
        """
        _, hex_hash = parse_object_ref(object_ref)
        return self._hex_to_path(hex_hash)

    def put_bytes(self, data: bytes) -> str:
        """Store bytes and return the canonical object reference.

        Thread-safe: handles concurrent writes correctly.

        Args:
            data: Raw bytes to store.

        Returns:
            Canonical object reference in format sha256:<hex>.
        """
        hex_hash = hashlib.sha256(data).hexdigest()
        object_path = self._hex_to_path(hex_hash)

        # Dedupe: if object already exists, skip write
        if object_path.exists():
            return make_object_ref(hex_hash)

        # Atomic write: write to temp file, then replace
        object_path.parent.mkdir(parents=True, exist_ok=True)

        # Use PID in temp filename to avoid collisions
        temp_path = object_path.with_suffix(f".tmp.{os.getpid()}")
        try:
            temp_path.write_bytes(data)
            try:
                # Use replace() for atomic overwrite (works on Windows)
                temp_path.replace(object_path)
            except OSError:
                # Race condition: another process wrote the same object
                # This is fine - CAS is content-addressed, so result is identical
                if object_path.exists():
                    # Object was written by another process, clean up our temp
                    if temp_path.exists():
                        temp_path.unlink()
                else:
                    # Actual error, re-raise
                    raise
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

        return make_object_ref(hex_hash)

    def has(self, object_ref: str) -> bool:
        """Check if an object exists in the store.

        Args:
            object_ref: Object reference (sha256:<hex> or bare hex).

        Returns:
            True if object exists, False otherwise.
        """
        try:
            return self._object_path(object_ref).exists()
        except ValueError:
            return False

    def get_bytes(self, object_ref: str) -> bytes:
        """Retrieve bytes for an object reference.

        Args:
            object_ref: Object reference (sha256:<hex> or bare hex).

        Returns:
            Raw bytes of the object.

        Raises:
            ObjectNotFoundError: If object does not exist.
        """
        object_path = self._object_path(object_ref)
        if not object_path.exists():
            raise ObjectNotFoundError(object_ref)
        return object_path.read_bytes()

    def get_path(self, object_ref: str) -> Optional[Path]:
        """Get the filesystem path for an object if it exists.

        Args:
            object_ref: Object reference (sha256:<hex> or bare hex).

        Returns:
            Path to object file, or None if not found.
        """
        try:
            object_path = self._object_path(object_ref)
            return object_path if object_path.exists() else None
        except ValueError:
            return None

    def get_hex(self, object_ref: str) -> str:
        """Extract the hex hash from an object reference.

        Args:
            object_ref: Object reference (sha256:<hex> or bare hex).

        Returns:
            64-character hex hash.
        """
        _, hex_hash = parse_object_ref(object_ref)
        return hex_hash
