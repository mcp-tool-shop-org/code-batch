"""CodeBatch - Content-addressed batch execution engine."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("codebatch")
except PackageNotFoundError:
    # Package not installed (e.g., running from source without pip install -e)
    __version__ = "0.0.0-dev"
