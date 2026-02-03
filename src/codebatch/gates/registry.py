"""Gate registry for defining and looking up gates.

The registry is the single source of truth for all gate definitions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import difflib

from .result import GateContext, GateResult, GateStatus


@dataclass
class GateDefinition:
    """Definition of a gate in the registry."""

    gate_id: str
    title: str
    description: str
    status: GateStatus
    required_inputs: list[str]  # e.g., ["store", "batch", "cache"]
    tags: list[str]  # e.g., ["phase3", "cache", "equivalence"]
    entrypoint: Callable[[GateContext], GateResult]
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for listing."""
        return {
            "gate_id": self.gate_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "required_inputs": self.required_inputs,
            "tags": self.tags,
            "aliases": self.aliases,
        }


class GateRegistry:
    """Central registry for all gates."""

    def __init__(self):
        self._gates: dict[str, GateDefinition] = {}
        self._aliases: dict[str, str] = {}  # alias -> canonical_id

    def register(
        self,
        gate_id: str,
        title: str,
        description: str,
        status: GateStatus,
        required_inputs: list[str],
        tags: list[str],
        entrypoint: Callable[[GateContext], GateResult],
        aliases: Optional[list[str]] = None,
    ) -> None:
        """Register a gate.

        Args:
            gate_id: Canonical gate identifier (e.g., P3-A1).
            title: One-line summary.
            description: Full description with pass criteria.
            status: ENFORCED, HARNESS, or PLACEHOLDER.
            required_inputs: What context the gate needs.
            tags: Categorization tags.
            entrypoint: Callable that executes the gate.
            aliases: Optional short aliases (e.g., A1 for P3-A1).
        """
        if gate_id in self._gates:
            raise ValueError(f"Gate already registered: {gate_id}")

        gate = GateDefinition(
            gate_id=gate_id,
            title=title,
            description=description,
            status=status,
            required_inputs=required_inputs,
            tags=tags,
            entrypoint=entrypoint,
            aliases=aliases or [],
        )
        self._gates[gate_id] = gate

        # Register aliases
        for alias in gate.aliases:
            if alias in self._aliases:
                raise ValueError(f"Alias already registered: {alias}")
            self._aliases[alias] = gate_id

    def get(self, gate_id_or_alias: str) -> Optional[GateDefinition]:
        """Get a gate by ID or alias.

        Args:
            gate_id_or_alias: Gate ID or alias.

        Returns:
            GateDefinition or None if not found.
        """
        # Try direct lookup
        if gate_id_or_alias in self._gates:
            return self._gates[gate_id_or_alias]

        # Try alias
        canonical_id = self._aliases.get(gate_id_or_alias)
        if canonical_id:
            return self._gates.get(canonical_id)

        return None

    def list_all(self) -> list[GateDefinition]:
        """List all registered gates."""
        return list(self._gates.values())

    def list_by_status(self, status: GateStatus) -> list[GateDefinition]:
        """List gates with a specific status."""
        return [g for g in self._gates.values() if g.status == status]

    def list_by_tag(self, tag: str) -> list[GateDefinition]:
        """List gates with a specific tag."""
        return [g for g in self._gates.values() if tag in g.tags]

    def list_by_phase(self, phase: str) -> list[GateDefinition]:
        """List gates for a specific phase (e.g., 'phase1', 'phase2')."""
        return [g for g in self._gates.values() if phase in g.tags]

    def suggest_similar(self, unknown_id: str, limit: int = 3) -> list[str]:
        """Suggest similar gate IDs for typos.

        Args:
            unknown_id: The unknown gate ID.
            limit: Maximum suggestions.

        Returns:
            List of similar gate IDs.
        """
        all_ids = list(self._gates.keys()) + list(self._aliases.keys())
        matches = difflib.get_close_matches(unknown_id, all_ids, n=limit, cutoff=0.4)
        return matches

    def validate_inputs(
        self, gate: GateDefinition, ctx: GateContext
    ) -> list[str]:
        """Validate that required inputs are present.

        Args:
            gate: Gate definition.
            ctx: Context to validate.

        Returns:
            List of missing input names.
        """
        missing = []
        for inp in gate.required_inputs:
            if inp == "store" and not ctx.store_root:
                missing.append("store")
            elif inp == "batch" and not ctx.batch_id:
                missing.append("batch")
            elif inp == "snapshot" and not ctx.snapshot_id:
                missing.append("snapshot")
            elif inp == "cache" and ctx.cache_required is False:
                missing.append("cache")
            elif inp == "tasks" and not ctx.task_ids:
                missing.append("tasks")
        return missing


# Global registry instance
_registry = GateRegistry()


def register_gate(
    gate_id: str,
    title: str,
    description: str,
    status: GateStatus,
    required_inputs: list[str],
    tags: list[str],
    aliases: Optional[list[str]] = None,
) -> Callable:
    """Decorator to register a gate function.

    Usage:
        @register_gate(
            gate_id="P3-A1",
            title="Cache equivalence",
            description="Cached queries return identical results to JSONL scan.",
            status=GateStatus.ENFORCED,
            required_inputs=["store", "batch"],
            tags=["phase3", "cache"],
            aliases=["A1"],
        )
        def gate_p3_a1(ctx: GateContext) -> GateResult:
            ...
    """

    def decorator(func: Callable[[GateContext], GateResult]) -> Callable:
        _registry.register(
            gate_id=gate_id,
            title=title,
            description=description,
            status=status,
            required_inputs=required_inputs,
            tags=tags,
            entrypoint=func,
            aliases=aliases,
        )
        return func

    return decorator


def get_gate(gate_id_or_alias: str) -> Optional[GateDefinition]:
    """Get a gate from the global registry."""
    return _registry.get(gate_id_or_alias)


def list_gates() -> list[GateDefinition]:
    """List all gates from the global registry."""
    return _registry.list_all()


def get_registry() -> GateRegistry:
    """Get the global registry instance."""
    return _registry
