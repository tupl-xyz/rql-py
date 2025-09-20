"""Abstract Syntax Tree models for RQL statements."""

from typing import Any, Dict, List, Optional, Union, Literal
from enum import Enum

from pydantic import BaseModel, Field


class SelectItem(str, Enum):
    """Valid items that can be selected in a SELECT statement."""
    OUTPUT = "OUTPUT"
    EVIDENCE = "EVIDENCE"
    CONFIDENCE = "CONFIDENCE"
    STAR = "*"


class ReturnFormat(str, Enum):
    """Valid return formats for SELECT statements."""
    JSON = "JSON"
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"


class DescribeTarget(str, Enum):
    """Valid targets for DESCRIBE statements."""
    SOURCES = "SOURCES"
    POLICIES = "POLICIES"




class DeterminismLevel(str, Enum):
    """Determinism enforcement levels."""
    PROVIDER = "provider"  # Default: provider-level determinism
    STRONG = "strong"      # Explicit: strong determinism with JSON schema


class Statement(BaseModel):
    """Base class for all RQL statements."""
    pass


class SetStmt(Statement):
    """SET key = value statement for configuration."""
    key: str
    value: Union[str, int, float, bool, None, Dict[str, Any], List[Any]]


class DefineSource(Statement):
    """DEFINE SOURCE statement for registering data sources."""
    name: str
    source_type: str
    config: Dict[str, Any]
    alias: Optional[str] = None


class DefinePolicy(Statement):
    """DEFINE POLICY statement for registering governance policies."""
    name: str
    config: Dict[str, Any]


class RefCall(BaseModel):
    """Reference to n8n workflow for deterministic retrieval."""
    source: str  # Name of registered WORKFLOW source
    args: Dict[str, Any]  # Arguments passed to workflow


class TaskInvocation(BaseModel):
    """Invocation of canonical task (no prompts allowed)."""
    name: Literal["ANSWER", "SUMMARIZE", "EXTRACT"]
    args: Dict[str, Any]  # Can include RefCall objects for context




class SelectStmt(Statement):
    """SELECT statement - task-based only."""
    select_items: List[str]
    task_invocation: TaskInvocation  # REQUIRED: only execution method
    with_params: Dict[str, Any] = Field(default_factory=dict)
    policy_name: Optional[str] = None
    determinism_level: DeterminismLevel = DeterminismLevel.PROVIDER
    return_format: str = "TEXT"
    into_var: Optional[str] = None

    def has_output(self) -> bool:
        """Check if OUTPUT is selected."""
        return "OUTPUT" in self.select_items or "*" in self.select_items

    def has_evidence(self) -> bool:
        """Check if EVIDENCE is selected."""
        return "EVIDENCE" in self.select_items or "*" in self.select_items

    def has_confidence(self) -> bool:
        """Check if CONFIDENCE is selected."""
        return "CONFIDENCE" in self.select_items or "*" in self.select_items

    def returns_json(self) -> bool:
        """Check if return format is JSON."""
        return self.return_format.upper() == "JSON"

    def returns_text(self) -> bool:
        """Check if return format is TEXT."""
        return self.return_format.upper() == "TEXT"

    def returns_markdown(self) -> bool:
        """Check if return format is MARKDOWN."""
        return self.return_format.upper() == "MARKDOWN"

    # Task-only helper methods
    def requires_strong_determinism(self) -> bool:
        """Check if strong determinism is required."""
        return self.determinism_level == DeterminismLevel.STRONG

    def requires_json_schema(self) -> bool:
        """Check if JSON schema validation is required."""
        return (self.determinism_level == DeterminismLevel.STRONG or
                self.task_invocation.name == "EXTRACT")

    def has_ref_calls(self) -> bool:
        """Check if task has REF() calls for evidence retrieval."""
        return any(isinstance(v, RefCall) for v in self.task_invocation.args.values())

    def get_ref_calls(self) -> List[RefCall]:
        """Get all REF() calls from task arguments."""
        return [v for v in self.task_invocation.args.values() if isinstance(v, RefCall)]


class DescribeStmt(Statement):
    """DESCRIBE statement for inspecting registry contents."""
    target: str  # SOURCES or POLICIES

    def describes_sources(self) -> bool:
        """Check if this describes sources."""
        return self.target.upper() == "SOURCES"

    def describes_policies(self) -> bool:
        """Check if this describes policies."""
        return self.target.upper() == "POLICIES"


# Type alias for any statement
AnyStatement = Union[SetStmt, DefineSource, DefinePolicy, SelectStmt, DescribeStmt]