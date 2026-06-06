from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
MASKED_CARD_RE = re.compile(
    r"(?<!\d)\d{4}(?:[ -]*(?:X{3,4}|\*{3,4})){2}[ -]*\d{4}(?!\d)",
    re.I,
)
FULL_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?60|0)\s*\d{1,2}(?:[ -]?\d){7,9}(?!\d)"
)
LONG_IDENTIFIER_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")
LABELLED_PRIVATE_RE = re.compile(
    r"^(?P<label>\s*(?:"
    r"registered\s+name|cardholder\s+name|customer\s+name|name|"
    r"address|mailing\s+address|email|e-mail|phone|mobile|telephone|"
    r"wallet\s*id|account\s*(?:number|no\.?)|card\s*(?:number|no\.?)"
    r")\s*:?\s*).+$",
    re.I | re.M,
)
LABELLED_PRIVATE_SCAN_RE = re.compile(
    r"^\s*(?:"
    r"registered\s+name|cardholder\s+name|customer\s+name|name|"
    r"address|mailing\s+address|email|e-mail|phone|mobile|telephone|"
    r"wallet\s*id|account\s*(?:number|no\.?)|card\s*(?:number|no\.?)"
    r")\s*:[ \t]*(?P<value>.+)$",
    re.I | re.M,
)
REDACTED_PLACEHOLDERS = {
    "[REDACTED]",
    "[EMAIL_REDACTED]",
    "[PHONE_REDACTED]",
    "[CARD_REDACTED]",
    "[LONG_ID_REDACTED]",
}


@dataclass(frozen=True)
class RedactionScan:
    passed: bool
    categories: tuple[str, ...]


def sanitize_statement_text(text: str) -> str:
    sanitized = text or ""
    sanitized = LABELLED_PRIVATE_RE.sub(
        lambda match: f"{match.group('label')}[REDACTED]",
        sanitized,
    )
    sanitized = EMAIL_RE.sub("[EMAIL_REDACTED]", sanitized)
    sanitized = MASKED_CARD_RE.sub("[CARD_REDACTED]", sanitized)
    sanitized = FULL_CARD_RE.sub("[CARD_REDACTED]", sanitized)
    sanitized = PHONE_RE.sub("[PHONE_REDACTED]", sanitized)
    sanitized = LONG_IDENTIFIER_RE.sub("[LONG_ID_REDACTED]", sanitized)
    return sanitized


def redaction_scan(text: str) -> RedactionScan:
    categories = []
    checks = (
        ("email", EMAIL_RE),
        ("masked_card", MASKED_CARD_RE),
        ("full_card", FULL_CARD_RE),
        ("phone", PHONE_RE),
        ("long_identifier", LONG_IDENTIFIER_RE),
    )
    for category, pattern in checks:
        if pattern.search(text or ""):
            categories.append(category)
    if any(
        match.group("value").strip().upper() not in REDACTED_PLACEHOLDERS
        for match in LABELLED_PRIVATE_SCAN_RE.finditer(text or "")
    ):
        categories.append("labelled_private_data")
    return RedactionScan(passed=not categories, categories=tuple(categories))
