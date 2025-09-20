"""Core policy enforcement framework."""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..ast import DefinePolicy, SelectStmt
from ...runtime.session import RQLSession
from .detectors import PIIDetector


class PolicyViolation(BaseModel):
    """Represents a policy violation."""
    policy_name: str
    violation_type: str
    message: str
    severity: str = "error"  # error, warning, info


class PolicyEnforcer:
    """Enforces policies on RQL queries and outputs."""

    def __init__(self):
        self.pii_detector = PIIDetector()

    def validate_input(self, stmt: SelectStmt, session: RQLSession) -> List[PolicyViolation]:
        """Validate input against applicable policies."""
        violations = []

        # Get applicable policies
        policies = self._get_applicable_policies(stmt, session)

        for policy in policies:
            input_rules = policy.config.get("input", {})

            # Check PII detection
            if input_rules.get("forbid_pii", False):
                violations.extend(self._check_input_pii(stmt, policy.name))

        return violations

    def validate_output(self, output: Any, stmt: SelectStmt, session: RQLSession) -> List[PolicyViolation]:
        """Validate output against applicable policies."""
        violations = []

        # Get applicable policies
        policies = self._get_applicable_policies(stmt, session)

        for policy in policies:
            output_rules = policy.config.get("output", {})

            # Check citation requirements
            if output_rules.get("require_citations", False):
                violations.extend(self._check_citations(output, policy.name))

            # Check for PII in output
            if output_rules.get("forbid_pii_output", False):
                violations.extend(self._check_output_pii(output, policy.name))

        return violations

    def should_block_output(self, violations: List[PolicyViolation], stmt: SelectStmt, session: RQLSession) -> bool:
        """Determine if output should be blocked based on violations."""
        if not violations:
            return False

        # Get applicable policies to check hallucination_mode
        policies = self._get_applicable_policies(stmt, session)

        for policy in policies:
            output_rules = policy.config.get("output", {})
            hallucination_mode = output_rules.get("hallucination_mode", "block")

            if hallucination_mode == "block_or_ask":
                # For now, always block in CLI mode
                # In an interactive mode, this would prompt the user
                return True
            elif hallucination_mode == "block":
                return True

        return len([v for v in violations if v.severity == "error"]) > 0

    def _get_applicable_policies(self, stmt: SelectStmt, session: RQLSession) -> List[DefinePolicy]:
        """Get policies that apply to this statement."""
        policies = []

        # Check explicit POLICY clause
        if stmt.policy_name:
            policy = session.registry.get_policy(stmt.policy_name)
            if policy:
                policies.append(policy)

        # TODO: Add support for global/default policies
        # For now, only explicit policies are applied

        return policies

    def _check_input_pii(self, stmt: SelectStmt, policy_name: str) -> List[PolicyViolation]:
        """Check for PII in query inputs."""
        violations = []

        # Extract text from the query to check
        text_to_check = []

        # Check the prompt if it's an LLM query
        if stmt.from_item and stmt.from_item.function_args:
            prompt = stmt.from_item.function_args.get("prompt")
            if isinstance(prompt, str):
                text_to_check.append(prompt)

            # Check other string arguments
            for key, value in stmt.from_item.function_args.items():
                if isinstance(value, str) and key != "prompt":
                    text_to_check.append(value)

        # Run PII detection
        for text in text_to_check:
            pii_findings = self.pii_detector.detect_pii(text)
            for finding in pii_findings:
                violations.append(PolicyViolation(
                    policy_name=policy_name,
                    violation_type="input_pii",
                    message=f"PII detected in input: {finding['type']} - {finding['pattern']}",
                    severity="error"
                ))

        return violations

    def _check_citations(self, output: Any, policy_name: str) -> List[PolicyViolation]:
        """Check if output contains required citations."""
        violations = []

        # Convert output to string for citation checking
        output_text = str(output)

        # Simple citation patterns to look for
        citation_patterns = [
            r'\[\d+\]',  # [1], [2], etc.
            r'\(\d+\)',  # (1), (2), etc.
            r'Source:',  # Source: ...
            r'Reference:',  # Reference: ...
            r'According to',  # According to [source]
        ]

        has_citations = any(re.search(pattern, output_text, re.IGNORECASE) for pattern in citation_patterns)

        if not has_citations:
            violations.append(PolicyViolation(
                policy_name=policy_name,
                violation_type="missing_citations",
                message="Output does not contain required citations",
                severity="error"
            ))

        return violations

    def _check_output_pii(self, output: Any, policy_name: str) -> List[PolicyViolation]:
        """Check for PII in output."""
        violations = []

        output_text = str(output)
        pii_findings = self.pii_detector.detect_pii(output_text)

        for finding in pii_findings:
            violations.append(PolicyViolation(
                policy_name=policy_name,
                violation_type="output_pii",
                message=f"PII detected in output: {finding['type']} - {finding['pattern']}",
                severity="error"
            ))

        return violations

    def redact_pii(self, text: str) -> str:
        """Redact PII from text."""
        return self.pii_detector.redact_pii(text)