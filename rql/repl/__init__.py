"""Interactive RQL REPL package."""

from typing import Any

__all__ = ["start_repl"]


def start_repl(*args: Any, **kwargs: Any) -> Any:
    """Lazy import entry point to avoid prompt_toolkit dependency at import time."""
    from .app import start_repl as _start_repl

    return _start_repl(*args, **kwargs)
