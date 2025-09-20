"""RQL - Retrieval Query Language.

A weekend prototype implementation of RQL with Google GenAI and n8n integration.
"""

__version__ = "0.1.0"

from . import engine, parser, runtime
from .cli import main

__all__ = ["engine", "parser", "runtime", "main"]