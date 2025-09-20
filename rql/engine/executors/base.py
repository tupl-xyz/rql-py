"""Base result models for executors."""

from typing import Any, Optional

from pydantic import BaseModel


class ExecResult(BaseModel):
    """Standardized execution result."""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None
    confidence: Optional[float] = None
    evidence: Optional[list] = None
    reasoning_contract: Optional[dict] = None