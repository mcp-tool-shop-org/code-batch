"""Gate system for CodeBatch enforcement.

The gate system provides a unified way to define, run, and report
on invariants across phases.
"""

from .result import GateResult, GateStatus, GateContext, GateFailure
from .registry import GateRegistry, register_gate, get_gate, list_gates

__all__ = [
    "GateResult",
    "GateStatus",
    "GateContext",
    "GateFailure",
    "GateRegistry",
    "register_gate",
    "get_gate",
    "list_gates",
]
