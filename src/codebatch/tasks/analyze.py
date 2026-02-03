"""Analyze task executor - Phase 2 stub.

NOT IMPLEMENTED IN PHASE 1.

This module exists as a placeholder for the analyze pipeline.
The 'analyze' pipeline is registered but will produce no outputs.
Use the 'parse' pipeline for Phase 1 functionality.
"""

from typing import Iterable

from ..runner import ShardRunner


def analyze_executor(config: dict, files: Iterable[dict], runner: ShardRunner) -> list[dict]:
    """Phase 2 stub - not implemented.

    This task depends on 01_parse outputs and will perform
    semantic analysis in Phase 2.

    Currently returns empty outputs.

    Args:
        config: Task configuration (ignored).
        files: Input files (ignored).
        runner: ShardRunner for CAS access (ignored).

    Returns:
        Empty list - no outputs produced.
    """
    # Phase 2: implement semantic analysis here
    return []
