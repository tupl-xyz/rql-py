import hashlib
import json
from typing import Dict, Any, List
from ..runtime.session import RQLSession
from .ast import RefCall

class EvidenceCanonicalizer:
    """Canonicalizes evidence for deterministic hashing."""

    def __init__(self):
        self.whitelist_fields = {"id", "uri", "title", "text", "score", "meta"}
        self.max_text_tokens = 2000  # Deterministic text truncation

    def canonicalize(self, raw_evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Canonicalize evidence list for deterministic processing."""
        normalized = []

        for i, item in enumerate(raw_evidence):
            if not isinstance(item, dict):
                item = {"text": str(item)}

            # Whitelist and normalize fields
            norm_item = {
                "id": item.get("id", f"evidence_{i}"),
                "uri": item.get("uri", ""),
                "title": item.get("title", ""),
                "text": self._truncate_text(item.get("text", "")),
                "score": item.get("score"),
                "meta": item.get("meta", {})
            }

            # Remove null values for consistency
            norm_item = {k: v for k, v in norm_item.items() if v is not None}
            normalized.append(norm_item)

        # Deterministic sort: score DESC, then id ASC for ties
        def sort_key(item):
            score = item.get("score", 0)
            item_id = item.get("id", "")
            return (-score if score is not None else 0, item_id)

        return sorted(normalized, key=sort_key)

    def _truncate_text(self, text: str) -> str:
        """Truncate text deterministically by character count."""
        if len(text) <= self.max_text_tokens:
            return text
        return text[:self.max_text_tokens] + "..."

    def get_evidence_hash(self, evidence: List[Dict[str, Any]]) -> str:
        """Compute deterministic hash of canonicalized evidence."""
        canonical_json = json.dumps(evidence, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode()).hexdigest()

    def compute_evidence_hash(self, evidence: List[Dict[str, Any]]) -> str:
        """Compute deterministic hash of canonicalized evidence (alias)."""
        return self.get_evidence_hash(evidence)

class RefResolver:
    """Resolves REF() calls to deterministic evidence."""

    def __init__(self):
        self.canonicalizer = EvidenceCanonicalizer()

    async def resolve_ref(self, ref_call: RefCall, session: RQLSession) -> Dict[str, Any]:
        """Resolve REF() call to canonicalized evidence."""
        # 1. Get workflow source from registry
        source = session.registry.get_source(ref_call.source)
        if not source or source.source_type != "WORKFLOW":
            raise ValueError(f"REF source '{ref_call.source}' not found or not a WORKFLOW")

        # 2. Call n8n workflow (reuse existing WorkflowExecutor)
        from .executors.workflow import WorkflowExecutor
        workflow_executor = WorkflowExecutor()

        # Execute workflow and get raw evidence
        result = await workflow_executor.execute_ref(source.config, ref_call.args)
        raw_evidence = result.get("evidence", [])

        # 3. Canonicalize evidence
        canonical_evidence = self.canonicalizer.canonicalize(raw_evidence)
        evidence_hash = self.canonicalizer.compute_evidence_hash(canonical_evidence)

        return {
            "evidence": canonical_evidence,
            "evidence_hash": evidence_hash,
            "source": ref_call.source,
            "args": ref_call.args,
            "count": len(canonical_evidence)
        }