"""Execution tracing and logging for RQL."""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..runtime.session import RQLSession
from .ast import Statement


class TraceRecord(BaseModel):
    """A single trace record for execution logging."""
    trace_id: str
    run_id: str
    session_id: str
    timestamp: str
    statement_index: int
    statement_type: str
    statement_text: Optional[str] = None
    execution_time_ms: Optional[float] = None
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ExecutionTracer:
    """Manages execution tracing and logging."""

    def __init__(self, session: RQLSession):
        self.session = session
        self.run_id = str(uuid.uuid4())
        self.traces: List[TraceRecord] = []
        self.start_time = time.time()

    def trace_statement(
        self,
        stmt: Statement,
        stmt_index: int,
        success: bool,
        execution_time_ms: float,
        output: Optional[Any] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        statement_text: Optional[str] = None,
    ) -> TraceRecord:
        """Create and record a trace entry for a statement execution."""
        trace = TraceRecord(
            trace_id=str(uuid.uuid4()),
            run_id=self.run_id,
            session_id=self.session.session_id,
            timestamp=datetime.now().isoformat(),
            statement_index=stmt_index,
            statement_type=type(stmt).__name__,
            statement_text=statement_text,
            execution_time_ms=execution_time_ms,
            success=success,
            output=output,
            error=error,
            metadata=metadata or {},
        )

        self.traces.append(trace)
        return trace

    def write_trace_file(self) -> Optional[Path]:
        """Write trace records to a JSONL file."""
        if not self.session.config.tracing.enabled:
            return None

        # Expand the trace directory path
        trace_dir = Path(self.session.config.tracing.trace_dir).expanduser()
        trace_dir.mkdir(parents=True, exist_ok=True)

        # Create trace file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_file = trace_dir / f"rql_trace_{timestamp}_{self.run_id[:8]}.jsonl"

        # Write trace records as JSONL
        with open(trace_file, "w") as f:
            for trace in self.traces:
                f.write(trace.model_dump_json() + "\n")

        return trace_file

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the execution trace."""
        total_time = time.time() - self.start_time
        successful_statements = sum(1 for trace in self.traces if trace.success)
        failed_statements = len(self.traces) - successful_statements

        total_execution_time = sum(
            trace.execution_time_ms or 0 for trace in self.traces
        )

        return {
            "run_id": self.run_id,
            "session_id": self.session.session_id,
            "total_statements": len(self.traces),
            "successful_statements": successful_statements,
            "failed_statements": failed_statements,
            "total_time_seconds": total_time,
            "total_execution_time_ms": total_execution_time,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.now().isoformat(),
        }

    def estimate_costs(self) -> Dict[str, Any]:
        """Estimate API costs from trace metadata."""
        if not self.session.config.tracing.include_costs:
            return {}

        # Simple cost estimation (would need real token counting in production)
        llm_calls = 0
        workflow_calls = 0
        estimated_tokens = 0

        for trace in self.traces:
            if trace.statement_type == "SelectStmt" and trace.metadata:
                if "model" in trace.metadata:
                    llm_calls += 1
                    # Very rough token estimation
                    if trace.metadata.get("prompt"):
                        estimated_tokens += len(str(trace.metadata["prompt"]).split()) * 1.3
                    if trace.output:
                        estimated_tokens += len(str(trace.output).split()) * 1.3

                if "webhook_url" in trace.metadata:
                    workflow_calls += 1

        # Rough cost estimation for Gemini
        estimated_cost_usd = estimated_tokens * 0.00001  # Very rough estimate

        return {
            "llm_calls": llm_calls,
            "workflow_calls": workflow_calls,
            "estimated_tokens": int(estimated_tokens),
            "estimated_cost_usd": round(estimated_cost_usd, 6),
        }