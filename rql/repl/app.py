"""Interactive REPL harness built on prompt_toolkit."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from rich.console import Console

from ..engine.ast import DeterminismLevel, SelectStmt, Statement
from ..engine.executors.base import ExecResult
from ..engine.planner import execute_statements
from ..parser import RQLParseError, RQLParser
from .commands import CommandExecutor, CommandOutcome
from .renderer import Renderer
from .session import ReplSession


PROMPT_TOOLKIT_DEPENDENCIES = (
    "prompt-toolkit>=3.0.43",
    "pygments>=2.17.0",
)


DECODE_DEFAULTS = {
    "decode.temperature": 0.0,
    "decode.top_p": 0.0,
    "decode.top_k": 1,
    "decode.candidateCount": 1,
}


def start_repl() -> None:
    """Launch the interactive REPL."""
    console = Console()

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.lexers import PygmentsLexer
        from prompt_toolkit.patch_stdout import patch_stdout
        from prompt_toolkit.styles import Style

        from .completer import RqlCompleter
        from .keybinds import create_key_bindings
        from .lexer import RqlLexer

    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        missing = exc.name or "prompt_toolkit"
        joined = ", ".join(PROMPT_TOOLKIT_DEPENDENCIES)
        console.print(
            f"[red]RQL REPL requires the optional dependency '{missing}'.[/red]"
        )
        console.print(
            f"Install via `[bold]pip install {joined}[/bold]` or reinstall the project with `[bold]pip install -e .[/bold]`."
        )
        raise SystemExit(1) from exc

    repl_session = ReplSession.create()
    renderer = Renderer(console)
    renderer.banner()

    parser = RQLParser()

    # Helper callbacks ----------------------------------------------------------------
    def should_submit(text: str, forced: bool) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if stripped.startswith(":"):
            return True
        if forced:
            return True
        if not stripped.endswith(";"):
            return False
        return _delimiters_balanced(stripped)

    def run_rql_text(text: str, source_path: Optional[Path]) -> List[ExecResult]:
        results: List[ExecResult] = []
        clean_text = text.strip()
        if not clean_text:
            return results

        try:
            statements = parser.parse(clean_text)
        except RQLParseError as exc:
            renderer.render_parse_error(str(exc))
            repl_session.set_status("Parse error")
            return results

        warnings, errors = _lint_statements(statements, repl_session)
        if warnings:
            renderer.render_lints(warnings)
        if errors:
            for err in errors:
                renderer.error(err)
            repl_session.set_status("Lint errors")
            return results

        exec_results = execute_statements(statements, repl_session.rql_session)
        renderer.render_exec_results(exec_results)
        repl_session.set_status("Ran statements")

        for idx, result in enumerate(exec_results):
            if result.reasoning_contract:
                contract_path = _save_contract(
                    input_text=clean_text,
                    source_path=source_path,
                    contract=result.reasoning_contract,
                    output=result.output,
                    metadata=result.metadata,
                    session=repl_session,
                    statement_index=idx,
                )
                record = repl_session.register_contract(contract_path, result.reasoning_contract)
                if repl_session.show_contract_pane:
                    renderer.render_contract_saved(record)
        results = exec_results
        return results

    command_executor = CommandExecutor(repl_session, renderer, run_rql_text)

    def run_command(command_text: str, buffer_text: str) -> Optional[CommandOutcome]:
        return command_executor.execute(command_text, buffer_text)

    style = Style.from_dict(
        {
            "prompt": "ansibrightcyan bold",
            "continuation": "ansibrightblack",
            "toolbar": "ansibrightblack",
        }
    )

    prompt_session = PromptSession(
        message=_prompt_message,
        completer=RqlCompleter(repl_session),
        lexer=PygmentsLexer(RqlLexer),
        history=FileHistory(str(repl_session.history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        enable_history_search=True,
        multiline=True,
        prompt_continuation=_continuation,
        bottom_toolbar=lambda: _toolbar(repl_session),
        key_bindings=create_key_bindings(repl_session, should_submit, run_command),
        style=style,
    )

    buffer_seed: Optional[str] = None

    while True:
        try:
            default_text = buffer_seed or ""
            buffer_seed = None
            with patch_stdout():
                text = prompt_session.prompt(default=default_text)
        except KeyboardInterrupt:
            repl_session.set_status("(cancelled)")
            buffer_seed = ""
            continue
        except EOFError:
            renderer.info("Exiting RQL REPL")
            break

        if text is None:
            continue

        stripped = text.strip()
        if not stripped:
            buffer_seed = ""
            continue

        if stripped.startswith(":"):
            outcome = command_executor.execute(stripped, text)
            if outcome.exit_repl:
                renderer.info("Bye")
                break
            if outcome.new_buffer is not None:
                buffer_seed = outcome.new_buffer
            else:
                buffer_seed = ""
            continue

        run_rql_text(text, None)
        buffer_seed = ""


# Prompt helpers -----------------------------------------------------------------------

def _prompt_message():
    from prompt_toolkit.formatted_text import FormattedText

    return FormattedText([("class:prompt", "rql> ")])


def _continuation(width: int, line_number: int, is_soft_wrap: bool):
    from prompt_toolkit.formatted_text import FormattedText

    return FormattedText([("class:continuation", "... ")])


def _toolbar(session: ReplSession):
    from prompt_toolkit.formatted_text import HTML

    pieces: List[str] = []
    if session.status_message:
        pieces.append(session.status_message)
    if session.show_contract_pane and session.latest_contract():
        record = session.latest_contract()
        pieces.append(
            f"Contract: {record.path.name} | {record.determinism_level or '-'} | "
            f"{record.evidence_hash or '-'}"
        )
    pieces.append(
        "Enter run • Shift+Enter newline • Ctrl-R force • Ctrl-S save • Alt+C contracts"
    )
    return HTML("  •  ".join(pieces))


# Linting ------------------------------------------------------------------------------

def _lint_statements(statements: Sequence[Statement], repl_session: ReplSession) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []

    for stmt in statements:
        if isinstance(stmt, SelectStmt):
            if stmt.determinism_level == DeterminismLevel.STRONG and not stmt.returns_json():
                errors.append("Strong determinism requires RETURN JSON")

            if stmt.determinism_level == DeterminismLevel.STRONG:
                missing = [k for k in DECODE_DEFAULTS if k not in stmt.with_params]
                if missing:
                    for key in missing:
                        stmt.with_params[key] = DECODE_DEFAULTS[key]
                    warnings.append(
                        "Pinned decode.* defaults for strong determinism ("
                        + ", ".join(missing)
                        + ")"
                    )

            model_name = stmt.with_params.get("model") or repl_session.rql_session.get_setting("model")
            if isinstance(model_name, str) and "latest" in model_name.lower():
                errors.append("Model alias containing 'latest' is not allowed in deterministic mode")

    return warnings, errors


# Contracts ---------------------------------------------------------------------------

def _save_contract(
    input_text: str,
    source_path: Optional[Path],
    contract: dict,
    output: Optional[object],
    metadata: Optional[dict],
    session: ReplSession,
    statement_index: int,
) -> Path:
    runs_root = Path.home() / ".rql" / "runs" / datetime.now().strftime("%Y-%m-%d")
    runs_root.mkdir(parents=True, exist_ok=True)

    filename = (
        f"run-{datetime.now().strftime('%H%M%S')}-{statement_index}-{uuid.uuid4().hex[:6]}.json"
    )
    path = runs_root / filename

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "statement_index": statement_index,
        "source_path": str(source_path) if source_path else None,
        "original_rql": input_text,
        "reasoning_contract": contract,
        "output": output,
        "metadata": metadata,
    }

    # Duplicate important fields at top-level for convenience
    if contract.get("output_hash"):
        payload["output_hash"] = contract["output_hash"]
    if contract.get("evidence_hash"):
        payload["evidence_hash"] = contract["evidence_hash"]

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    return path


# Utilities ---------------------------------------------------------------------------

def _delimiters_balanced(text: str) -> bool:
    """Return True when (), [], {} are balanced and we're not mid-string.

    Handles escaped quotes inside strings (\" or \\'). This avoids falsely
    toggling string state for JSON patterns like "^[^\"\n\r]+$".
    """
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack: List[str] = []
    in_single = False
    in_double = False
    escaped = False

    for ch in text:
        if in_single:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == "'":
                in_single = False
            continue

        if in_double:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_double = False
            continue

        # Not inside a string
        if ch == "'":
            in_single = True
            continue
        if ch == '"':
            in_double = True
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in pairs.values():
            if not stack or stack.pop() != ch:
                return False

    return not stack and not in_single and not in_double
