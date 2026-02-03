"""Content-Addressed Storage (CAS) object store.

Objects are stored at: objects/sha256/<aa>/<bb>/<full_hash>
Where <aa> and <bb> are the first two byte pairs of the hex hash.
"""

import hashlib
from pathlib import Path
from typing import Optional


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

    def _object_path(self, object_ref: str) -> Path:
        """Get the filesystem path for an object reference.

        Args:
            object_ref: SHA-256 hex hash (64 characters).

        Returns:
            Path to the object file.
        """
        if len(object_ref) != 64:
            raise ValueError(f"Invalid object reference: {object_ref}")
        aa = object_ref[:2]
        bb = object_ref[2:4]
        return self.objects_dir / aa / bb / object_ref

    def put_bytes(self, data: bytes) -> str:
        """Store bytes and return the object reference.

        Args:
            data: Raw bytes to store.

        Returns:
            SHA-256 hex hash of the data (object reference).
        """
        object_ref = hashlib.sha256(data).hexdigest()
        object_path = self._object_path(object_ref)

        # Dedupe: if object already exists, skip write
        if object_path.exists():
            return object_ref

        # Atomic write: write to temp file, then rename
        object_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = object_path.with_suffix(".tmp")
        try:
            temp_path.write_bytes(data)
            temp_path.rename(object_path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise

        return object_ref

    def has(self, object_ref: str) -> bool:
        """Check if an object exists in the store.

        Args:
            object_ref: SHA-256 hex hash.

        Returns:
            True if object exists, False otherwise.
        """
        return self._object_path(object_ref).exists()

    def get_bytes(self, object_ref: str) -> bytes:
        """Retrieve bytes for an object reference.

        Args:
            object_ref: SHA-256 hex hash.

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
            object_ref: SHA-256 hex hash.

        Returns:
            Path to object file, or None if not found.
        """
        object_path = self._object_path(object_ref)
        return object_path if object_path.exists() else None
