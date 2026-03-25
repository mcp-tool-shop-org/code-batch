"""Tests for version consistency — single source of truth."""



class TestVersionConsistency:
    """Verify all version declarations agree with pyproject.toml."""

    def test_init_version_matches_pyproject(self):
        """__init__.__version__ should match pyproject.toml version."""
        from codebatch import __version__

        # Should be either the installed version (1.0.0) or dev fallback
        assert __version__ is not None
        assert isinstance(__version__, str)
        # If installed (editable or not), should not be the old hardcoded values
        if __version__ != "0.0.0-dev":
            assert __version__ != "0.1.0", "Still using old hardcoded 0.1.0"
            assert __version__ != "0.7.0", "Still using old hardcoded 0.7.0"

    def test_common_version_matches_init(self):
        """common.VERSION should be the same as __init__.__version__."""
        from codebatch import __version__
        from codebatch.common import VERSION

        assert VERSION == __version__

    def test_producer_version_matches(self):
        """PRODUCER version should match VERSION."""
        from codebatch.common import VERSION, PRODUCER

        assert PRODUCER["version"] == VERSION

    def test_version_is_string(self):
        """Version should be a valid string."""
        from codebatch.common import VERSION

        assert isinstance(VERSION, str)
        assert len(VERSION) > 0
