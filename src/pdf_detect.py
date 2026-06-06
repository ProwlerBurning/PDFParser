from __future__ import annotations

import re


def detect_statement_type(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text or "").upper()
    if (
        "TRANSACTION DATE TIME TRANSACTION TYPE TRANSACTION AMOUNT "
        "TRANSACTION DIRECTION TRANSACTION STATUS TRANSACTION REFERENCE ID"
    ) in normalized or "TNG WALLET TRANSACTION HISTORY" in normalized or (
        "TOUCH" in normalized and "GO EWALLET" in normalized
    ):
        return "tng"
    if "STANDARD CHARTERED" in normalized or (
        "CREDIT CARD STATEMENT" in normalized and "PENYATA KAD ANDA" in normalized
    ):
        return "sc"
    if any(
        marker in normalized
        for marker in (
            "HONG LEONG BANK",
            "YOUR TRANSACTION DETAILS",
            "ESSENTIAL VISA CLASSIC",
        )
    ):
        return "hlb"
    return None


def processing_mode_for(statement_type: str, has_useful_text: bool) -> str:
    if statement_type == "hlb" and has_useful_text:
        return "text"
    if statement_type == "tng":
        return "text" if has_useful_text else "ocr"
    if statement_type == "sc":
        return "ocr"
    return "text" if has_useful_text else "ocr"
