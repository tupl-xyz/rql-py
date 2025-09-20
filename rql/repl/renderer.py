"""Utilities for rendering REPL output with rich."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

from ..engine.executors.base import ExecResult
from .session import ContractRecord


class Renderer:
    """Render execution results, diagnostics, and contracts."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    # General messages -----------------------------------------------------------------
    def banner(self) -> None:
        self.console.print(Panel("RQL REPL – type :help for commands", title="RQL"))

    def info(self, message: str) -> None:
        self.console.print(f"[cyan]{message}[/cyan]")

    def warn(self, message: str) -> None:
        self.console.print(f"[yellow]{message}[/yellow]")

    def error(self, message: str) -> None:
        self.console.print(Panel(message, title="Error", border_style="red"))

    # Statement rendering --------------------------------------------------------------
    def render_exec_results(self, results: Iterable[ExecResult]) -> None:
        for idx, result in enumerate(results, start=1):
            header = f"Result {idx}" if idx > 1 else "Result"
            if result.success:
                self._render_success(result, header)
            else:
                self._render_failure(result, header)

    def _render_success(self, result: ExecResult, header: str) -> None:
        body: Optional[object] = None

        if isinstance(result.output, (dict, list)):
            body = Pretty(result.output, expand_all=True)
        elif isinstance(result.output, str):
            try:
                parsed = json.loads(result.output)
                body = Pretty(parsed, expand_all=False)
            except (json.JSONDecodeError, TypeError):
                body = Text(result.output)
        elif result.output is not None:
            body = Pretty(result.output)

        panel = Panel.fit(body or Text("(no output)"), title=header, border_style="green")
        self.console.print(panel)

        if result.reasoning_contract:
            summary = self._contract_summary_text(result.reasoning_contract)
            self.console.print(summary)

    def _render_failure(self, result: ExecResult, header: str) -> None:
        message = result.error or "Unknown error"
        detail = Pretty(result.metadata) if result.metadata else None
        panel = Panel(Text(message), title=f"{header} – failed", border_style="red")
        self.console.print(panel)
        if detail:
            self.console.print(detail)

    def render_parse_error(self, message: str) -> None:
        self.error(message)

    def render_lints(self, lints: Iterable[str]) -> None:
        for lint in lints:
            self.warn(lint)

    # Contracts -----------------------------------------------------------------------
    def render_contract_saved(self, record: ContractRecord) -> None:
        table = Table(title="Reasoning Contract Saved", show_lines=False)
        table.add_column("Field", style="bold cyan")
        table.add_column("Value", style="white")
        table.add_row("File", str(record.path))
        if record.task:
            table.add_row("Task", record.task)
        if record.determinism_level:
            table.add_row("Determinism", record.determinism_level)
        if record.evidence_hash:
            table.add_row("Evidence Hash", record.evidence_hash)
        if record.output_hash:
            table.add_row("Output Hash", record.output_hash)
        table.add_row("Saved", record.created_at.isoformat(timespec="seconds"))
        self.console.print(table)

    def render_contract_content(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.console.print(Pretty(payload, expand_all=False))
        except FileNotFoundError:
            self.error(f"Contract file not found: {path}")
        except json.JSONDecodeError as exc:
            self.error(f"Failed to read contract JSON: {exc}")

    def render_contract_list(self, records: Iterable[ContractRecord]) -> None:
        table = Table(title="Saved Contracts", show_lines=False)
        table.add_column("#", style="bold")
        table.add_column("File")
        table.add_column("Determinism")
        table.add_column("Evidence Hash")
        table.add_column("Timestamp")
        for idx, record in enumerate(records, start=1):
            table.add_row(
                str(idx),
                record.path.name,
                record.determinism_level or "-",
                record.evidence_hash or "-",
                record.created_at.isoformat(timespec="seconds"),
            )
        self.console.print(table)

    def _contract_summary_text(self, contract_payload: dict) -> Text:
        pieces = []
        if contract_payload.get("determinism_level"):
            pieces.append(f"determinism={contract_payload['determinism_level']}")
        if contract_payload.get("evidence_hash"):
            pieces.append(f"evidence_hash={contract_payload['evidence_hash']}")
        if contract_payload.get("output_hash"):
            pieces.append(f"output_hash={contract_payload['output_hash']}")
        summary = ", ".join(pieces) or "contract metadata"
        text = Text(f"contract: {summary}", style="magenta")
        return text
