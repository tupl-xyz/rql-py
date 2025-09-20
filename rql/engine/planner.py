"""Execution planner for RQL statements.

The planner orchestrates statement execution by:
1. Validating statements against the registry
2. Planning execution order
3. Delegating to appropriate executors
4. Managing session state
"""

import time
from typing import List

from ..runtime.session import RQLSession
from .ast import (
    DefinePolicy,
    DefineSource,
    DescribeStmt,
    DescribeTarget,
    SelectStmt,
    SetStmt,
    Statement,
)
from .executors.base import ExecResult
from .tracing import ExecutionTracer


def execute_statements(statements: List[Statement], session: RQLSession) -> List[ExecResult]:
    """Execute a list of RQL statements in order."""
    results = []
    tracer = ExecutionTracer(session)

    for i, stmt in enumerate(statements):
        try:
            start_time = time.time()
            result = execute_statement(stmt, session)
            execution_time_ms = (time.time() - start_time) * 1000

            # Record trace
            tracer.trace_statement(
                stmt=stmt,
                stmt_index=i,
                success=result.success,
                execution_time_ms=execution_time_ms,
                output=result.output,
                error=result.error,
                metadata=result.metadata,
            )

            results.append(result)

            # Stop execution on first failure
            if not result.success:
                break

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
            error_msg = str(e)

            # Record failed trace
            tracer.trace_statement(
                stmt=stmt,
                stmt_index=i,
                success=False,
                execution_time_ms=execution_time_ms,
                error=error_msg,
            )

            results.append(ExecResult(success=False, error=error_msg))
            break

    # Write trace file if enabled
    if session.config.tracing.enabled:
        trace_file = tracer.write_trace_file()
        if session.is_verbose() and trace_file:
            print(f"Trace written to: {trace_file}")

    return results


def execute_statement(stmt: Statement, session: RQLSession) -> ExecResult:
    """Execute a single RQL statement."""
    try:
        if isinstance(stmt, SetStmt):
            return execute_set(stmt, session)
        elif isinstance(stmt, DefineSource):
            return execute_define_source(stmt, session)
        elif isinstance(stmt, DefinePolicy):
            return execute_define_policy(stmt, session)
        elif isinstance(stmt, SelectStmt):
            return execute_select(stmt, session)
        elif isinstance(stmt, DescribeStmt):
            return execute_describe(stmt, session)
        else:
            return ExecResult(success=False, error=f"Unknown statement type: {type(stmt)}")

    except Exception as e:
        return ExecResult(success=False, error=str(e))


def execute_set(stmt: SetStmt, session: RQLSession) -> ExecResult:
    """Execute a SET statement."""
    session.set_setting(stmt.key, stmt.value)

    if session.is_verbose():
        return ExecResult(
            success=True,
            output=f"Set {stmt.key} = {stmt.value}",
        )
    else:
        return ExecResult(success=True)


def execute_define_source(stmt: DefineSource, session: RQLSession) -> ExecResult:
    """Execute a DEFINE SOURCE statement."""
    session.registry.register_source(stmt)

    if session.is_verbose():
        alias_text = f" AS \"{stmt.alias}\"" if stmt.alias else ""
        return ExecResult(
            success=True,
            output=f"Defined source '{stmt.name}' (type: {stmt.source_type}){alias_text}",
        )
    else:
        return ExecResult(success=True)


def execute_define_policy(stmt: DefinePolicy, session: RQLSession) -> ExecResult:
    """Execute a DEFINE POLICY statement."""
    session.registry.register_policy(stmt)

    if session.is_verbose():
        return ExecResult(
            success=True,
            output=f"Defined policy '{stmt.name}'",
        )
    else:
        return ExecResult(success=True)


def execute_select(stmt: SelectStmt, session: RQLSession) -> ExecResult:
    """Execute a SELECT statement."""
    # Import here to avoid circular imports
    from .executors.factory import create_executor
    from .policies import PolicyEnforcer

    try:
        # Initialize policy enforcer
        policy_enforcer = PolicyEnforcer()

        # Validate input against policies
        input_violations = policy_enforcer.validate_input(stmt, session)
        if input_violations:
            violation_messages = [v.message for v in input_violations]
            return ExecResult(
                success=False,
                error=f"Policy violations in input: {'; '.join(violation_messages)}"
            )

        # Create the appropriate executor based on the TASK clause
        executor = create_executor(stmt.task_invocation, session)

        # Execute the query
        result = executor.execute(stmt, session)

        # Validate output against policies if execution was successful
        if result.success and result.output is not None:
            output_violations = policy_enforcer.validate_output(result.output, stmt, session)

            if output_violations:
                if policy_enforcer.should_block_output(output_violations, stmt, session):
                    violation_messages = [v.message for v in output_violations]
                    return ExecResult(
                        success=False,
                        error=f"Policy violations in output: {'; '.join(violation_messages)}"
                    )

        # Handle INTO variable binding
        if stmt.into_var and result.success and result.output:
            session.set_variable(stmt.into_var, result.output)
            if session.is_verbose():
                result.output = f"Result stored in variable '{stmt.into_var}': {result.output}"

        return result

    except Exception as e:
        return ExecResult(success=False, error=f"Execution failed: {str(e)}")


def execute_describe(stmt: DescribeStmt, session: RQLSession) -> ExecResult:
    """Execute a DESCRIBE statement."""
    if stmt.target == DescribeTarget.SOURCES:
        sources = session.registry.list_sources()
        if not sources:
            return ExecResult(success=True, output="No sources registered")

        output_lines = ["Registered Sources:"]
        for source in sources:
            alias_text = f" (alias: \"{source.alias}\")" if source.alias else ""
            output_lines.append(f"  - {source.name}: {source.source_type}{alias_text}")

        return ExecResult(success=True, output="\n".join(output_lines))

    elif stmt.target == DescribeTarget.POLICIES:
        policies = session.registry.list_policies()
        if not policies:
            return ExecResult(success=True, output="No policies registered")

        output_lines = ["Registered Policies:"]
        for policy in policies:
            output_lines.append(f"  - {policy.name}")

        return ExecResult(success=True, output="\n".join(output_lines))

    else:
        return ExecResult(success=False, error=f"Unknown describe target: {stmt.target}")