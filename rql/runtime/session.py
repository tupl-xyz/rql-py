"""Session management for RQL execution.

The session maintains runtime state including:
- Settings (model, temperature, etc.)
- Variable bindings from INTO statements
- Registry for sources and policies
"""

import uuid
from typing import Any, Dict, Optional

from .config import RQLConfig
from .registry import RQLRegistry


class RQLSession:
    """Runtime session for RQL execution."""

    def __init__(self, config: Optional[RQLConfig] = None):
        self.session_id = str(uuid.uuid4())
        self.config = config or RQLConfig()
        self.registry = RQLRegistry()

        # Runtime settings (can be modified by SET statements)
        self.settings: Dict[str, Any] = {
            "model": self.config.llm.model,
            "temperature": self.config.llm.temperature,
            "max_tokens": self.config.llm.max_tokens,
            "output_format": self.config.output_format,
            "verbose": self.config.verbose,
        }

        # Variable bindings from INTO statements
        self.variables: Dict[str, Any] = {}

    def set_setting(self, key: str, value: Any) -> None:
        """Set a session setting (from SET statements)."""
        self.settings[key] = value

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a session setting."""
        return self.settings.get(key, default)

    def set_variable(self, name: str, value: Any) -> None:
        """Set a variable binding (from INTO statements)."""
        self.variables[name] = value

    def get_variable(self, name: str) -> Any:
        """Get a variable binding."""
        return self.variables.get(name)

    def has_variable(self, name: str) -> bool:
        """Check if a variable is bound."""
        return name in self.variables

    def clear_variables(self) -> None:
        """Clear all variable bindings."""
        self.variables.clear()

    def get_model(self) -> str:
        """Get the current model setting."""
        return self.get_setting("model", self.config.llm.model)

    def get_temperature(self) -> float:
        """Get the current temperature setting."""
        return self.get_setting("temperature", self.config.llm.temperature)

    def get_max_tokens(self) -> Optional[int]:
        """Get the current max_tokens setting."""
        return self.get_setting("max_tokens", self.config.llm.max_tokens)

    def get_output_format(self) -> str:
        """Get the current output format setting."""
        return self.get_setting("output_format", self.config.output_format)

    def is_verbose(self) -> bool:
        """Check if verbose mode is enabled."""
        return self.get_setting("verbose", self.config.verbose)

    def reset(self) -> None:
        """Reset session to initial state."""
        self.variables.clear()
        self.registry.clear()
        self.settings = {
            "model": self.config.llm.model,
            "temperature": self.config.llm.temperature,
            "max_tokens": self.config.llm.max_tokens,
            "output_format": self.config.output_format,
            "verbose": self.config.verbose,
        }