"""Registry for managing RQL sources and policies.

The registry stores DEFINE SOURCE and DEFINE POLICY statements
and provides lookup functionality for execution.
"""

from typing import Dict, List, Optional

from ..engine.ast import DefinePolicy, DefineSource


class RQLRegistry:
    """Registry for sources and policies defined in RQL."""

    def __init__(self):
        self._sources: Dict[str, DefineSource] = {}
        self._policies: Dict[str, DefinePolicy] = {}

    def register_source(self, source: DefineSource) -> None:
        """Register a data source."""
        self._sources[source.name] = source

    def register_policy(self, policy: DefinePolicy) -> None:
        """Register a governance policy."""
        self._policies[policy.name] = policy

    def get_source(self, name: str) -> Optional[DefineSource]:
        """Get a registered source by name."""
        return self._sources.get(name)

    def get_policy(self, name: str) -> Optional[DefinePolicy]:
        """Get a registered policy by name."""
        return self._policies.get(name)

    def list_sources(self) -> List[DefineSource]:
        """List all registered sources."""
        return list(self._sources.values())

    def list_policies(self) -> List[DefinePolicy]:
        """List all registered policies."""
        return list(self._policies.values())

    def has_source(self, name: str) -> bool:
        """Check if a source is registered."""
        return name in self._sources

    def has_policy(self, name: str) -> bool:
        """Check if a policy is registered."""
        return name in self._policies

    def clear(self) -> None:
        """Clear all registered sources and policies."""
        self._sources.clear()
        self._policies.clear()

    def source_count(self) -> int:
        """Get the number of registered sources."""
        return len(self._sources)

    def policy_count(self) -> int:
        """Get the number of registered policies."""
        return len(self._policies)