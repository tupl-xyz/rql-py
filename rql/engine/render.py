"""Output rendering and formatting for RQL."""

import json
from typing import Any, Dict

from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.text import Text


class OutputRenderer:
    """Handles output formatting and rendering."""

    def __init__(self, console: Console):
        self.console = console

    def render_result(self, result: Any, format_type: str = "json") -> str:
        """Render execution result in the specified format."""
        if format_type.upper() == "JSON":
            return self._render_json(result)
        elif format_type.upper() == "TEXT":
            return self._render_text(result)
        elif format_type.upper() == "MARKDOWN":
            return self._render_markdown(result)
        else:
            # Default to JSON
            return self._render_json(result)

    def _render_json(self, result: Any) -> str:
        """Render result as formatted JSON."""
        if result is None:
            return "null"

        try:
            return json.dumps(result, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            # Fallback for non-serializable objects
            return str(result)

    def _render_text(self, result: Any) -> str:
        """Render result as plain text."""
        if result is None:
            return ""

        if isinstance(result, dict):
            # Format dictionary as key-value pairs
            lines = []
            for key, value in result.items():
                lines.append(f"{key}: {value}")
            return "\n".join(lines)

        elif isinstance(result, list):
            # Format list as numbered items
            lines = []
            for i, item in enumerate(result, 1):
                lines.append(f"{i}. {item}")
            return "\n".join(lines)

        else:
            return str(result)

    def _render_markdown(self, result: Any) -> str:
        """Render result as Markdown."""
        if result is None:
            return ""

        if isinstance(result, dict):
            # Format dictionary as Markdown table
            if not result:
                return ""

            lines = ["| Key | Value |", "|-----|-------|"]
            for key, value in result.items():
                # Escape pipe characters in values
                value_str = str(value).replace("|", "\\|")
                lines.append(f"| {key} | {value_str} |")
            return "\n".join(lines)

        elif isinstance(result, list):
            # Format list as Markdown list
            lines = []
            for item in result:
                lines.append(f"- {item}")
            return "\n".join(lines)

        else:
            return str(result)

    def render_error(self, error: str) -> Text:
        """Render error message with rich formatting."""
        return Text(f"Error: {error}", style="red")

    def render_success(self, message: str) -> Text:
        """Render success message with rich formatting."""
        return Text(message, style="green")

    def render_info(self, message: str) -> Text:
        """Render info message with rich formatting."""
        return Text(message, style="blue")

    def render_warning(self, message: str) -> Text:
        """Render warning message with rich formatting."""
        return Text(f"Warning: {message}", style="yellow")

    def render_sources_table(self, sources: list) -> Table:
        """Render sources as a rich table."""
        table = Table(title="Registered Sources")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Alias", style="green")

        for source in sources:
            alias = source.alias if source.alias else ""
            table.add_row(source.name, source.source_type, alias)

        return table

    def render_policies_table(self, policies: list) -> Table:
        """Render policies as a rich table."""
        table = Table(title="Registered Policies")
        table.add_column("Name", style="cyan")
        table.add_column("Config", style="yellow")

        for policy in policies:
            config_str = json.dumps(policy.config, indent=2) if policy.config else ""
            table.add_row(policy.name, config_str)

        return table

    def render_trace_summary(self, summary: Dict[str, Any]) -> Table:
        """Render execution trace summary as a table."""
        table = Table(title="Execution Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in summary.items():
            # Format key for display
            display_key = key.replace("_", " ").title()
            table.add_row(display_key, str(value))

        return table