"""prompt_toolkit completer for the RQL REPL."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from .session import ReplSession

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class CompletionItem:
    value: str
    display: str
    description: str


class RqlCompleter(Completer):
    """Context-aware completion for RQL keywords and dynamic names."""

    KEYWORDS: List[CompletionItem] = [
        CompletionItem("SELECT", "SELECT", "Select clause"),
        CompletionItem("FROM", "FROM", "Source clause"),
        CompletionItem("TASK", "TASK", "Task keyword"),
        CompletionItem("ANSWER", "ANSWER", "Answer task"),
        CompletionItem("SUMMARIZE", "SUMMARIZE", "Summarize task"),
        CompletionItem("EXTRACT", "EXTRACT", "Extract task"),
        CompletionItem("WITH", "WITH", "Decoder configuration"),
        CompletionItem("RETURN", "RETURN", "Return format"),
        CompletionItem("JSON", "JSON", "JSON output"),
        CompletionItem("TEXT", "TEXT", "Text output"),
        CompletionItem("MARKDOWN", "MARKDOWN", "Markdown output"),
        CompletionItem("DEFINE", "DEFINE", "Definition"),
        CompletionItem("SOURCE", "SOURCE", "Source definition"),
        CompletionItem("POLICY", "POLICY", "Policy definition"),
        CompletionItem("SET", "SET", "Session setting"),
        CompletionItem("DESCRIBE", "DESCRIBE", "Describe registries"),
        CompletionItem("INTO", "INTO", "Store result"),
        CompletionItem("REF", "REF", "Reference data"),
        CompletionItem("REQUIRE", "REQUIRE", "Determinism requirement"),
        CompletionItem("DETERMINISM", "DETERMINISM", "Determinism clause"),
        CompletionItem("STRONG", "STRONG", "Strict determinism"),
        CompletionItem("PROVIDER", "PROVIDER", "Provider determinism"),
    ]

    META_COMMANDS: List[CompletionItem] = [
        CompletionItem(":help", ":help", "Show help"),
        CompletionItem(":open", ":open", "Open file"),
        CompletionItem(":save", ":save", "Save buffer"),
        CompletionItem(":run", ":run", "Run file"),
        CompletionItem(":describe", ":describe", "Describe registries"),
        CompletionItem(":contracts", ":contracts", "Manage contracts"),
        CompletionItem(":replay", ":replay", "Replay contract"),
        CompletionItem(":reset", ":reset", "Reset session"),
        CompletionItem(":format", ":format", "Format buffer"),
        CompletionItem(":quit", ":quit", "Exit REPL"),
    ]

    def __init__(self, repl_session: ReplSession):
        self._session = repl_session

    def get_completions(self, document: Document, complete_event):  # type: ignore[override]
        text_before_cursor = document.text_before_cursor
        word = document.get_word_before_cursor(pattern=_IDENTIFIER_RE) or ""

        # Meta command completion
        stripped = text_before_cursor.lstrip()
        if stripped.startswith(":"):
            yield from self._iter_matches(word, self.META_COMMANDS)
            return

        suggestions: List[CompletionItem] = list(self.KEYWORDS)

        # Dynamic registry driven items
        suggestions.extend(
            CompletionItem(name, name, "Registered source")
            for name in self._session.source_names()
        )
        suggestions.extend(
            CompletionItem(name, name, "Registered policy")
            for name in self._session.policy_names()
        )
        suggestions.extend(
            CompletionItem(var, var, "Session variable") for var in self._session.variable_names()
        )

        # Task names and dotted WITH keys
        suggestions.extend(
            CompletionItem(task, task, "Task name") for task in self._session.task_names()
        )
        suggestions.extend(
            CompletionItem(key, key, "WITH parameter") for key in self._session.with_param_keys()
        )

        for completion in self._iter_matches(word, suggestions):
            yield completion

    def _iter_matches(self, word: str, items: Iterable[CompletionItem]):
        upper_word = word.upper()
        for item in items:
            if not word or item.value.upper().startswith(upper_word):
                yield Completion(
                    item.value,
                    start_position=-len(word),
                    display=item.display,
                    display_meta=item.description,
                )
