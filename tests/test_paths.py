"""Tests for path canonicalization and safety."""

import pytest
from pathlib import Path

from codebatch.paths import (
    canonicalize_path,
    compute_path_key,
    canonicalize_with_key,
    is_safe_path,
    detect_case_collision,
    PathEscapeError,
    InvalidPathError,
)


class TestCanonicalizePath:
    """Tests for canonicalize_path."""

    def test_forward_slashes_preserved(self):
        """Forward slashes are preserved."""
        assert canonicalize_path("src/main.py") == "src/main.py"

    def test_backslashes_converted(self):
        """Windows backslashes are converted to forward slashes."""
        assert canonicalize_path("src\\main.py") == "src/main.py"
        assert canonicalize_path("src\\sub\\file.txt") == "src/sub/file.txt"

    def test_mixed_slashes_normalized(self):
        """Mixed slashes are normalized."""
        assert canonicalize_path("src/sub\\file.txt") == "src/sub/file.txt"

    def test_trailing_slash_removed(self):
        """Trailing slashes are removed."""
        assert canonicalize_path("src/") == "src"
        assert canonicalize_path("src/sub/") == "src/sub"

    def test_dot_segments_removed(self):
        """Current directory (.) segments are removed."""
        assert canonicalize_path("./src/main.py") == "src/main.py"
        assert canonicalize_path("src/./sub/./file.txt") == "src/sub/file.txt"

    def test_double_dot_resolved(self):
        """Parent directory (..) segments are resolved."""
        assert canonicalize_path("src/sub/../main.py") == "src/main.py"
        assert canonicalize_path("a/b/c/../../d.txt") == "a/d.txt"

    def test_double_dot_escape_raises(self):
        """Attempting to go above root raises PathEscapeError."""
        with pytest.raises(PathEscapeError):
            canonicalize_path("../escape.txt")

        with pytest.raises(PathEscapeError):
            canonicalize_path("src/../../escape.txt")

    def test_empty_path_raises(self):
        """Empty path raises InvalidPathError."""
        with pytest.raises(InvalidPathError):
            canonicalize_path("")

        with pytest.raises(InvalidPathError):
            canonicalize_path("   ")

    def test_only_dots_raises(self):
        """Path that resolves to root raises InvalidPathError."""
        with pytest.raises(InvalidPathError):
            canonicalize_path(".")

        with pytest.raises(InvalidPathError):
            canonicalize_path("./")

    def test_invalid_characters_raise(self):
        """Invalid characters raise InvalidPathError."""
        with pytest.raises(InvalidPathError):
            canonicalize_path("file<name>.txt")

        with pytest.raises(InvalidPathError):
            canonicalize_path("file:name.txt")

        with pytest.raises(InvalidPathError):
            canonicalize_path("file\x00name.txt")

    def test_reserved_names_raise(self):
        """Windows reserved names raise InvalidPathError."""
        with pytest.raises(InvalidPathError):
            canonicalize_path("CON")

        with pytest.raises(InvalidPathError):
            canonicalize_path("src/NUL.txt")

        with pytest.raises(InvalidPathError):
            canonicalize_path("COM1")

    def test_unicode_paths_preserved(self):
        """Unicode paths are preserved."""
        assert canonicalize_path("路径/文件.txt") == "路径/文件.txt"
        assert canonicalize_path("emoji_🎉/test.md") == "emoji_🎉/test.md"

    def test_casing_preserved(self):
        """Original casing is preserved."""
        assert canonicalize_path("SRC/Main.PY") == "SRC/Main.PY"

    def test_multiple_consecutive_slashes_collapsed(self):
        """Multiple slashes are collapsed to one."""
        assert canonicalize_path("src//sub///file.txt") == "src/sub/file.txt"


class TestComputePathKey:
    """Tests for compute_path_key."""

    def test_lowercase_conversion(self):
        """Path key is lowercase."""
        assert compute_path_key("SRC/Main.PY") == "src/main.py"

    def test_unicode_lowercase(self):
        """Unicode characters are lowercased."""
        assert compute_path_key("ÑOÑO.txt") == "ñoño.txt"


class TestCanonicalizeWithKey:
    """Tests for canonicalize_with_key."""

    def test_returns_both(self):
        """Returns both canonical path and key."""
        path, key = canonicalize_with_key("SRC\\Main.PY")
        assert path == "SRC/Main.PY"
        assert key == "src/main.py"


class TestIsSafePath:
    """Tests for is_safe_path."""

    def test_safe_paths(self):
        """Safe paths return True."""
        assert is_safe_path("src/main.py") is True
        assert is_safe_path("a/b/c.txt") is True

    def test_unsafe_paths(self):
        """Unsafe paths return False."""
        assert is_safe_path("../escape.txt") is False
        assert is_safe_path("file<name>.txt") is False
        assert is_safe_path("") is False


class TestDetectCaseCollision:
    """Tests for detect_case_collision."""

    def test_no_collisions(self):
        """No collisions returns empty list."""
        paths = ["src/main.py", "src/other.py", "lib/util.py"]
        assert detect_case_collision(paths) == []

    def test_detects_collision(self):
        """Detects case collisions."""
        paths = ["src/Main.py", "src/main.py"]
        collisions = detect_case_collision(paths)
        assert len(collisions) == 1
        assert ("src/Main.py", "src/main.py") in collisions

    def test_detects_multiple_collisions(self):
        """Detects multiple collisions."""
        paths = ["A.cs", "a.cs", "B.cs", "b.cs"]
        collisions = detect_case_collision(paths)
        assert len(collisions) == 2

    def test_three_way_collision(self):
        """Handles three-way collision."""
        paths = ["File.txt", "file.txt", "FILE.txt"]
        collisions = detect_case_collision(paths)
        # 3 choose 2 = 3 pairs
        assert len(collisions) == 3
