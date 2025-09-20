"""Meta command handling for the RQL REPL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from rich.table import Table

from ..engine.ast import DescribeStmt, DescribeTarget
from ..engine.executors.base import ExecResult
from ..engine.planner import execute_statements
from .renderer import Renderer
from .session import ReplSession


@dataclass
class MetaCommand:
    name: str
    args: List[str]


@dataclass
class CommandOutcome:
    exit_repl: bool = False
    new_buffer: Optional[str] = None


class CommandExecutor:
    """Dispatch colon-prefixed meta commands."""

    def __init__(
        self,
        repl_session: ReplSession,
        renderer: Renderer,
        run_rql_text: Callable[[str, Optional[Path]], List[ExecResult]],
    ) -> None:
        self._repl_session = repl_session
        self._renderer = renderer
        self._run_rql_text = run_rql_text

    # Public API ------------------------------------------------------------------
    def execute(self, raw_command: str, buffer_text: str) -> CommandOutcome:
        meta = parse_meta_command(raw_command)
        if not meta:
            self._renderer.error(f"Unknown command: {raw_command}")
            return CommandOutcome()

        name = meta.name
        if name == "help":
            self._cmd_help()
        elif name == "open":
            return self._cmd_open(meta.args)
        elif name == "save":
            return self._cmd_save(meta.args, buffer_text)
        elif name == "run":
            self._cmd_run(meta.args)
        elif name == "describe":
            self._cmd_describe(meta.args)
        elif name == "contracts":
            self._cmd_contracts(meta.args)
        elif name == "replay":
            self._cmd_replay(meta.args)
        elif name == "reset":
            self._cmd_reset()
        elif name == "format":
            return self._cmd_format(buffer_text)
        elif name == "verbose":
            self._cmd_verbose(meta.args)
        elif name == "quit":
            return CommandOutcome(exit_repl=True)
        else:
            self._renderer.error(f"Unsupported command: {raw_command}")
        return CommandOutcome()

    # Command implementations ------------------------------------------------------
    def _cmd_help(self) -> None:
        # REPL Commands table
        table = Table(title=":help - REPL Commands", show_lines=False)
        table.add_column("Command", style="bold cyan")
        table.add_column("Description")
        table.add_row(":help", "Show this help message")
        table.add_row(":open <file>", "Load file contents into the buffer")
        table.add_row(":save [file]", "Save buffer to file (defaults to last opened)")
        table.add_row(":run <file>", "Execute a file in the current session")
        table.add_row(":describe [SOURCES|POLICIES]", "Describe registry state")
        table.add_row(":contracts [last|list|open <n>]", "Inspect reasoning contracts")
        table.add_row(":replay <contract.json>", "Replay a saved contract")
        table.add_row(":reset", "Reset REPL session state")
        table.add_row(":format", "Format current buffer")
        table.add_row(":verbose [on|off]", "Toggle or set verbose mode")
        table.add_row(":quit", "Exit the REPL")
        self._renderer.console.print(table)

        # RQL Tasks table
        tasks_table = Table(title="Available RQL Tasks", show_lines=True)
        tasks_table.add_column("Task", style="bold green")
        tasks_table.add_column("Arguments", style="yellow")
        tasks_table.add_column("Description")

        tasks_table.add_row(
            "ANSWER",
            "question: <text>\ncontext: REF(<source>, <args>)",
            "Answer questions using provided context with citations. Uses general knowledge when no context provided."
        )

        tasks_table.add_row(
            "SUMMARIZE",
            "text: <text>\nfocus: <aspect>\nlength: <constraint>\ntext_ref: REF(<source>, <args>)",
            "Summarize content with optional focus and length controls. Can use REF for dynamic content."
        )

        tasks_table.add_row(
            "EXTRACT",
            "schema: <json_schema>\ninput_text: <text>\ninput_ref: REF(<source>, <args>)",
            "Extract structured information matching JSON schema from text or referenced content."
        )

        self._renderer.console.print(tasks_table)

        # SELECT Statement syntax table
        syntax_table = Table(title="SELECT Statement Syntax", show_lines=True)
        syntax_table.add_column("Component", style="bold magenta")
        syntax_table.add_column("Options")
        syntax_table.add_column("Description")

        syntax_table.add_row(
            "SELECT items",
            "OUTPUT, EVIDENCE, CONFIDENCE, *",
            "What to return from task execution"
        )

        syntax_table.add_row(
            "FROM",
            "TASK <name>(<args>)",
            "Required task invocation"
        )

        syntax_table.add_row(
            "WITH",
            "decode.temperature=0\ndecode.top_p=0.1\n<other_params>=<value>",
            "Optional parameters for task execution"
        )

        syntax_table.add_row(
            "POLICY",
            "<policy_name> or <json_config>",
            "Optional governance policy"
        )

        syntax_table.add_row(
            "REQUIRE DETERMINISM",
            "provider | strong",
            "Determinism level (default: provider)"
        )

        syntax_table.add_row(
            "RETURN",
            "JSON | TEXT | MARKDOWN",
            "Output format (default: TEXT)"
        )

        syntax_table.add_row(
            "INTO",
            "<variable_name>",
            "Store result in variable"
        )

        self._renderer.console.print(syntax_table)

        # Example usage
        example_table = Table(title="Example RQL Statements", show_lines=False)
        example_table.add_column("Example", style="italic")

        example_table.add_row('SELECT * FROM TASK ANSWER(question: "What is RQL?");')
        example_table.add_row('SELECT OUTPUT FROM TASK EXTRACT(schema: {"name": {"type": "string"}}, input_text: "John Doe") RETURN JSON;')
        example_table.add_row('SELECT * FROM TASK SUMMARIZE(text_ref: REF(docs, {"path": "/readme.md"})) WITH decode.temperature=0.1;')
        example_table.add_row('SELECT OUTPUT FROM TASK ANSWER(question: "Explain the data", context: REF(database, {"query": "SELECT * FROM users"})) REQUIRE DETERMINISM strong RETURN JSON;')

        self._renderer.console.print(example_table)

        # RQL Statements table
        statements_table = Table(title="Other RQL Statements", show_lines=True)
        statements_table.add_column("Statement", style="bold blue")
        statements_table.add_column("Syntax")
        statements_table.add_column("Description")

        statements_table.add_row(
            "SET",
            "SET <key> = <value>;",
            "Configure session settings:\n• model (string)\n• temperature (number)\n• max_tokens (number)\n• output_format (string)\n• verbose (boolean)"
        )

        statements_table.add_row(
            "DEFINE SOURCE",
            "DEFINE SOURCE <name> TYPE <type>\nUSING <config> [AS <alias>];",
            "Register data sources:\n• TYPE: LLM, WORKFLOW\n• Config varies by type\n• Optional alias for description"
        )

        statements_table.add_row(
            "DEFINE POLICY",
            "DEFINE POLICY <name> AS <config>;",
            "Set governance rules:\n• input: validation rules\n• output: format requirements\n• logging: audit configuration"
        )

        statements_table.add_row(
            "DESCRIBE",
            "DESCRIBE <target>;",
            "Inspect registry contents:\n• SOURCES: show data sources\n• POLICIES: show governance policies"
        )

        self._renderer.console.print(statements_table)

        # SET examples
        set_example_table = Table(title="SET Statement Examples", show_lines=False)
        set_example_table.add_column("Example", style="italic")

        set_example_table.add_row('SET model = "gemini-2.5-flash";')
        set_example_table.add_row('SET temperature = 0.1;')
        set_example_table.add_row('SET max_tokens = 512;')
        set_example_table.add_row('SET verbose = true;')

        self._renderer.console.print(set_example_table)

    def _cmd_open(self, args: List[str]) -> CommandOutcome:
        if not args:
            self._renderer.error(":open requires a file path")
            return CommandOutcome()
        path = Path(args[0]).expanduser()
        if not path.exists():
            self._renderer.error(f"File not found: {path}")
            return CommandOutcome()
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        self._repl_session.current_file = path
        self._repl_session.set_status(f"Opened {path}")
        return CommandOutcome(new_buffer=content)

    def _cmd_save(self, args: List[str], buffer_text: str) -> CommandOutcome:
        path = Path(args[0]).expanduser() if args else self._repl_session.current_file
        if not path:
            self._renderer.error("No target file. Provide a path or :open first.")
            return CommandOutcome()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(buffer_text)
        self._repl_session.current_file = path
        self._repl_session.set_status(f"Saved buffer to {path}")
        self._renderer.info(f"Buffer saved to {path}")
        return CommandOutcome()

    def _cmd_run(self, args: List[str]) -> None:
        if not args:
            self._renderer.error(":run requires a file path")
            return
        path = Path(args[0]).expanduser()
        if not path.exists():
            self._renderer.error(f"File not found: {path}")
            return
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        self._repl_session.set_status(f"Running {path}")
        self._run_rql_text(content, path)

    def _cmd_describe(self, args: List[str]) -> None:
        target_text = args[0].upper() if args else "SOURCES"
        if target_text not in {"SOURCES", "POLICIES"}:
            self._renderer.error("Target must be SOURCES or POLICIES")
            return
        stmt = DescribeStmt(
            target=DescribeTarget.SOURCES if target_text == "SOURCES" else DescribeTarget.POLICIES
        )
        result = execute_statements([stmt], self._repl_session.rql_session)
        self._renderer.render_exec_results(result)

    def _cmd_contracts(self, args: List[str]) -> None:
        if not self._repl_session.contract_records:
            self._renderer.warn("No contracts saved yet")
            return

        if not args or args[0] == "list":
            self._renderer.render_contract_list(self._repl_session.contract_records)
            return

        if args[0] == "last":
            record = self._repl_session.latest_contract()
            if record:
                self._renderer.render_contract_saved(record)
                self._renderer.render_contract_content(record.path)
            return

        if args[0] == "open" and len(args) > 1:
            try:
                index = int(args[1]) - 1
            except ValueError:
                self._renderer.error("Index must be an integer")
                return
            if index < 0 or index >= len(self._repl_session.contract_records):
                self._renderer.error("Contract index out of range")
                return
            record = self._repl_session.contract_records[index]
            self._renderer.render_contract_saved(record)
            self._renderer.render_contract_content(record.path)
            return

        self._renderer.error("Usage: :contracts [list|last|open <n>]")

    def _cmd_replay(self, args: List[str]) -> None:
        if not args:
            self._renderer.error(":replay requires a contract path")
            return
        path = Path(args[0]).expanduser()
        if not path.exists():
            self._renderer.error(f"Contract not found: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            self._renderer.error(f"Invalid contract JSON: {exc}")
            return

        original = payload.get("original_rql")
        if not original:
            self._renderer.error("Contract missing original RQL. Cannot replay.")
            return

        self._renderer.info(f"Replaying contract from {path}")
        results = self._run_rql_text(original, None)

        # Compare output hash when available
        expected_hash = payload.get("reasoning_contract", {}).get("output_hash") or payload.get("output_hash")
        if expected_hash and results:
            actual_result = results[-1]
            actual_hash = None
            if actual_result.reasoning_contract:
                actual_hash = actual_result.reasoning_contract.get("output_hash")
            if actual_hash and actual_hash == expected_hash:
                self._renderer.info("[replay] hashes match. output stable.")
            elif actual_hash:
                self._renderer.warn(
                    f"[replay] hash mismatch: expected {expected_hash}, got {actual_hash}"
                )
            else:
                self._renderer.warn("[replay] new run did not produce a contract hash")

    def _cmd_reset(self) -> None:
        self._repl_session.reset()
        self._renderer.info("Session reset")

    def _cmd_format(self, buffer_text: str) -> CommandOutcome:
        formatted = _basic_format(buffer_text)
        self._repl_session.set_status("Buffer formatted")
        return CommandOutcome(new_buffer=formatted)

    def _cmd_verbose(self, args: List[str]) -> None:
        """Toggle or set verbose mode: :verbose [on|off]"""
        current = bool(self._repl_session.rql_session.get_setting("verbose", False))
        if not args:
            new_val = not current
        else:
            token = args[0].lower()
            if token in {"on", "true", "1", "yes", "y"}:
                new_val = True
            elif token in {"off", "false", "0", "no", "n"}:
                new_val = False
            else:
                self._renderer.error("Usage: :verbose [on|off]")
                return
        self._repl_session.rql_session.set_setting("verbose", new_val)
        self._renderer.info(f"Verbose {'enabled' if new_val else 'disabled'}")


# Helper functions ----------------------------------------------------------------------

def parse_meta_command(text: str) -> Optional[MetaCommand]:
    text = text.strip()
    if not text.startswith(":"):
        return None
    parts = text[1:].strip().split()
    if not parts:
        return None
    name, *args = parts
    return MetaCommand(name=name.lower(), args=args)


def _basic_format(text: str) -> str:
    """Very small indentation helper for readability."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    indent = 0
    formatted: List[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.endswith(("}", ")", "]")) or stripped.startswith(("}", ")", "]")):
            indent = max(indent - 1, 0)
        formatted.append("    " * indent + stripped)
        if stripped.endswith(("{", "(", "[")):
            indent += 1
        if stripped.upper().endswith(";"):
            indent = 0
    return "\n".join(formatted) + ("\n" if formatted else "")
