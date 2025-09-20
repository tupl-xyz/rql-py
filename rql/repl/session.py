"""REPL session state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..runtime import RQLSession, ensure_config_dir, load_config


@dataclass
class ContractRecord:
    """Metadata about a saved reasoning contract."""

    path: Path
    determinism_level: Optional[str]
    evidence_hash: Optional[str]
    output_hash: Optional[str]
    created_at: datetime
    task: Optional[str] = None


@dataclass
class ReplSession:
    """Container for interactive REPL state."""

    rql_session: RQLSession
    history_file: Path
    current_file: Optional[Path] = None
    status_message: str = ""
    contract_records: List[ContractRecord] = field(default_factory=list)
    show_contract_pane: bool = False
    force_execute: bool = False

    @classmethod
    def create(cls) -> "ReplSession":
        """Factory that wires configuration and history paths."""
        ensure_config_dir()
        config = load_config()
        rql_session = RQLSession(config)

        history_file = Path.home() / ".rql" / "history"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        return cls(rql_session=rql_session, history_file=history_file)

    def reset(self) -> None:
        """Reset underlying session and REPL metadata."""
        self.rql_session.reset()
        self.contract_records.clear()
        self.current_file = None
        self.status_message = "Session reset"

    def register_contract(self, path: Path, contract_payload: Dict[str, Any]) -> ContractRecord:
        """Persist metadata about the latest contract for quick lookup."""
        record = ContractRecord(
            path=path,
            determinism_level=contract_payload.get("determinism_level"),
            evidence_hash=contract_payload.get("evidence_hash"),
            output_hash=contract_payload.get("output_hash"),
            created_at=datetime.now(),
            task=contract_payload.get("task"),
        )
        self.contract_records.append(record)
        self.status_message = f"Saved contract: {path.name}"
        return record

    def toggle_contract_pane(self) -> None:
        """Toggle visibility of the contract side pane."""
        self.show_contract_pane = not self.show_contract_pane

    def latest_contract(self) -> Optional[ContractRecord]:
        """Return the most recent contract record if any."""
        return self.contract_records[-1] if self.contract_records else None

    # Dynamic completion helpers -------------------------------------------------
    def source_names(self) -> List[str]:
        return [source.name for source in self.rql_session.registry.list_sources()]

    def policy_names(self) -> List[str]:
        return [policy.name for policy in self.rql_session.registry.list_policies()]

    def variable_names(self) -> List[str]:
        return list(self.rql_session.variables.keys())

    def task_names(self) -> List[str]:
        # In v0.2 we have fixed task names but keep this extensible
        return ["ANSWER", "SUMMARIZE", "EXTRACT"]

    def with_param_keys(self) -> List[str]:
        return ["decode.temperature", "decode.top_p", "decode.top_k", "decode.candidateCount"]

    def set_status(self, message: str) -> None:
        self.status_message = message
