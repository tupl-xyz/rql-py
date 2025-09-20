"""Custom key bindings for the RQL REPL."""

from __future__ import annotations

from typing import Callable, Optional

from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings

from .commands import CommandOutcome
from .session import ReplSession


ShouldSubmitFn = Callable[[str, bool], bool]
CommandRunner = Callable[[str, str], Optional[CommandOutcome]]


def create_key_bindings(
    repl_session: ReplSession,
    should_submit: ShouldSubmitFn,
    run_command: CommandRunner,
) -> KeyBindings:
    """Wire key bindings for multiline editing and meta shortcuts."""

    kb = KeyBindings()

    def apply_outcome(event, outcome: Optional[CommandOutcome]) -> None:
        if not outcome:
            return
        buffer = event.current_buffer
        if outcome.new_buffer is not None:
            new_text = outcome.new_buffer
            buffer.document = Document(text=new_text, cursor_position=len(new_text))
        if outcome.exit_repl:
            event.app.exit(result="")

    @kb.add("enter")
    def _(event) -> None:
        buffer = event.current_buffer
        text = buffer.text
        forced = repl_session.force_execute
        last_key = ""
        if event.key_sequence:
            last_key = event.key_sequence[-1].key.lower()
        if last_key in {"s-enter", "shift-enter"}:
            buffer.insert_text("\n")
            return
        if should_submit(text, forced):
            repl_session.force_execute = False
            event.app.exit(result=text)
        else:
            buffer.insert_text("\n")

    @kb.add("c-r")
    def _(event) -> None:
        repl_session.force_execute = True
        event.app.exit(result=event.current_buffer.text)

    @kb.add("c-s")
    def _(event) -> None:
        buffer_text = event.current_buffer.text
        holder: dict[str, Optional[CommandOutcome]] = {"value": None}

        def handler() -> None:
            holder["value"] = run_command(":save", buffer_text)

        event.app.run_in_terminal(handler)
        apply_outcome(event, holder.get("value"))

    @kb.add("c-o")
    def _(event) -> None:
        buffer_text = event.current_buffer.text
        holder: dict[str, Optional[CommandOutcome]] = {"value": None}

        def handler() -> None:
            path = input("Open file path: ").strip()
            if path:
                holder["value"] = run_command(f":open {path}", buffer_text)

        event.app.run_in_terminal(handler)
        apply_outcome(event, holder.get("value"))

    @kb.add("escape", "c")
    def _(event) -> None:
        repl_session.toggle_contract_pane()
        repl_session.set_status("Contract pane toggled")

    return kb
