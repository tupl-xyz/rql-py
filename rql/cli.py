"""CLI commands for RQL using Typer."""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .engine.ast import DescribeStmt, DescribeTarget
from .parser import RQLParser
from .repl import start_repl
from .runtime import RQLSession, create_default_config, ensure_config_dir, load_config

app = typer.Typer(help="RQL - Retrieval Query Language CLI")
console = Console()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    help_: bool = typer.Option(
        False,
        "--help",
        "-h",
        help="Show this message and exit.",
        is_eager=True,
    ),
) -> None:
    """Default callback to launch REPL when no subcommand is invoked."""
    if ctx.invoked_subcommand is not None:
        return
    if help_:
        typer.echo(ctx.command.get_help(ctx))
        raise typer.Exit()

    start_repl()
    raise typer.Exit()


@app.command()
def exec(
    statement: str = typer.Argument(..., help="RQL statement to execute"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Execute a single RQL statement."""
    try:
        # Initialize configuration and session
        ensure_config_dir()
        config = load_config()
        session = RQLSession(config)

        if verbose:
            session.set_setting("verbose", True)

        # Parse the statement
        parser = RQLParser()
        statements = parser.parse(statement)

        if not statements:
            console.print("[red]Error:[/red] No valid statements found")
            raise typer.Exit(1)

        # Execute each statement
        from .engine.planner import execute_statements
        results = execute_statements(statements, session)

        # Display results
        for result in results:
            if result.success:
                if result.output:
                    console.print(result.output)
            else:
                console.print(f"[red]Error:[/red] {result.error}")
                raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def run(
    file_path: Path = typer.Argument(..., help="Path to RQL file to execute"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Execute RQL statements from a file."""
    try:
        if not file_path.exists():
            console.print(f"[red]Error:[/red] File {file_path} not found")
            raise typer.Exit(1)

        # Read the file
        with open(file_path, "r") as f:
            content = f.read()

        # Initialize configuration and session
        ensure_config_dir()
        config = load_config()
        session = RQLSession(config)

        if verbose:
            session.set_setting("verbose", True)

        # Parse the statements
        parser = RQLParser()
        statements = parser.parse(content)

        if not statements:
            console.print("[red]Error:[/red] No valid statements found in file")
            raise typer.Exit(1)

        if verbose:
            console.print(f"[blue]Info:[/blue] Executing {len(statements)} statements from {file_path}")

        # Execute all statements
        from .engine.planner import execute_statements
        results = execute_statements(statements, session)

        # Display results
        for i, result in enumerate(results):
            if verbose:
                console.print(f"[blue]Statement {i+1}:[/blue]")

            if result.success:
                if result.output:
                    console.print(result.output)
            else:
                console.print(f"[red]Error in statement {i+1}:[/red] {result.error}")
                raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def describe(
    target: str = typer.Argument(..., help="What to describe: SOURCES or POLICIES"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Describe registered sources or policies."""
    try:
        # Parse the target
        target_upper = target.upper()
        if target_upper not in ["SOURCES", "POLICIES"]:
            console.print(f"[red]Error:[/red] Invalid target '{target}'. Use SOURCES or POLICIES")
            raise typer.Exit(1)

        # Initialize session
        ensure_config_dir()
        config = load_config()
        session = RQLSession(config)

        # Create a DESCRIBE statement
        describe_target = DescribeTarget.SOURCES if target_upper == "SOURCES" else DescribeTarget.POLICIES
        describe_stmt = DescribeStmt(target=describe_target)

        # Execute the describe statement
        from .engine.planner import execute_statements
        results = execute_statements([describe_stmt], session)

        # Display results
        for result in results:
            if result.success:
                if result.output:
                    console.print(result.output)
                else:
                    console.print(f"[yellow]No {target.lower()} registered[/yellow]")
            else:
                console.print(f"[red]Error:[/red] {result.error}")
                raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def init() -> None:
    """Initialize RQL configuration."""
    try:
        ensure_config_dir()
        create_default_config()
        console.print("[green]Success:[/green] RQL configuration initialized at ~/.rql/config.toml")
        console.print("Set your GEMINI_API_KEY environment variable to get started!")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show RQL version information."""
    try:
        from importlib.metadata import version as _v

        ver = _v("rql")
    except Exception:
        ver = "unknown"
    console.print(f"RQL (Retrieval Query Language) v{ver}")
    console.print("A weekend prototype implementation")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
