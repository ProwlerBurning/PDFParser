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
