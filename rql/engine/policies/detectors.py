"""PII and content detection patterns."""

import re
from typing import Dict, List


class PIIDetector:
    """Detects personally identifiable information in text."""

    def __init__(self):
        # Define PII detection patterns
        self.patterns = {
            "email": {
                "pattern": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                "description": "Email address"
            },
            "phone": {
                "pattern": r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',
                "description": "Phone number"
            },
            "ssn": {
                "pattern": r'\b\d{3}-?\d{2}-?\d{4}\b',
                "description": "Social Security Number"
            },
            "credit_card": {
                "pattern": r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3[0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
                "description": "Credit card number"
            },
            "ip_address": {
                "pattern": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
                "description": "IP address"
            },
            "us_passport": {
                "pattern": r'\b[A-Z]{1,2}[0-9]{6,9}\b',
                "description": "US Passport number"
            },
            "driver_license": {
                "pattern": r'\b[A-Z]{1,2}[0-9]{4,8}\b',
                "description": "Driver's license number"
            }
        }

    def detect_pii(self, text: str) -> List[Dict[str, str]]:
        """Detect PII in the given text."""
        findings = []

        for pii_type, pattern_info in self.patterns.items():
            pattern = pattern_info["pattern"]
            matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in matches:
                findings.append({
                    "type": pii_type,
                    "pattern": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "description": pattern_info["description"]
                })

        return findings

    def redact_pii(self, text: str, redaction_char: str = "*") -> str:
        """Redact PII from text by replacing with redaction characters."""
        redacted_text = text

        # Sort findings by position (descending) to avoid offset issues
        all_findings = self.detect_pii(text)
        all_findings.sort(key=lambda x: x["start"], reverse=True)

        for finding in all_findings:
            start = finding["start"]
            end = finding["end"]
            replacement = redaction_char * (end - start)
            redacted_text = redacted_text[:start] + replacement + redacted_text[end:]

        return redacted_text

    def has_pii(self, text: str) -> bool:
        """Check if text contains any PII."""
        return len(self.detect_pii(text)) > 0

    def get_pii_types(self, text: str) -> List[str]:
        """Get list of PII types found in text."""
        findings = self.detect_pii(text)
        return list(set(finding["type"] for finding in findings))

    def add_pattern(self, name: str, pattern: str, description: str) -> None:
        """Add a custom PII detection pattern."""
        self.patterns[name] = {
            "pattern": pattern,
            "description": description
        }

    def remove_pattern(self, name: str) -> None:
        """Remove a PII detection pattern."""
        if name in self.patterns:
            del self.patterns[name]