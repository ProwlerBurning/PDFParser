from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_money(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\d().-]", "", value.replace(",", ""))
    if not cleaned:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if negative:
        amount = -amount
    return float(amount)


def money_tokens(value: str) -> list[str]:
    return re.findall(r"(?:RM\s*)?\(?-?\d[\d,]*\.\d{2}\)?(?:\s*CR)?", value, re.I)


# Matches either a dot-decimal amount (optionally with thousands commas, e.g.
# 1,000.00) or a bare comma-decimal amount produced by some OCR passes
# (e.g. 54,52 -> 54.52), followed by an optional CR credit marker.
AMOUNT_TOKEN_RE = re.compile(
    r"(?P<num>\d[\d,]*\.\d{2}|\d{1,3},\d{2})(?:\s*(?P<cr>CR))?",
    re.I,
)


def parse_amount_token(token: str | None) -> float | None:
    """Parse a single amount token, normalising comma-decimal forms.

    ``1,000.00`` keeps comma-as-thousands semantics; ``54,52`` is treated as a
    comma decimal and normalised to ``54.52``. Returns ``None`` when the token
    is not a recoverable amount so callers can keep the row as an exception.
    """
    if token is None:
        return None
    cleaned = token.strip().upper().removesuffix("CR").strip()
    if re.fullmatch(r"\d{1,3},\d{2}", cleaned):
        cleaned = cleaned.replace(",", ".")
    return parse_money(cleaned)
