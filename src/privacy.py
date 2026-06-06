from __future__ import annotations

import re
from typing import Any


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def mask_card_number(value: str | None) -> str:
    source = value or ""
    edge_match = re.search(r"(?<!\d)(\d{4})[0-9Xx* -]*(\d{4})(?!\d)", source)
    if edge_match and re.search(r"[Xx*]", source):
        return f"{edge_match.group(1)}********{edge_match.group(2)}"
    digits = _digits(source)
    if len(digits) <= 8:
        return "*" * len(digits)
    return f"{digits[:4]}{'*' * (len(digits) - 8)}{digits[-4:]}"


def mask_wallet_id(value: str | None) -> str:
    source = value or ""
    edge_match = re.fullmatch(r"\D*(\d{3})[0-9* -]*(\d{3})\D*", source)
    if edge_match and len(_digits(source)) >= 6:
        return f"{edge_match.group(1)}*****{edge_match.group(2)}"
    digits = _digits(source)
    if len(digits) <= 6:
        return "*" * len(digits)
    return f"{digits[:3]}{'*' * (len(digits) - 6)}{digits[-3:]}"


def mask_name(value: str | None) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", value or "")
    return " ".join(word[0] + "*****" for word in words)


def redact_free_text(value: str | None) -> str:
    text = value or ""
    text = re.sub(
        r"\d{9,}",
        lambda match: (
            mask_wallet_id(match.group(0))
            if len(match.group(0)) <= 12
            else mask_card_number(match.group(0))
        ),
        text,
    )
    return text


def apply_privacy(result: Any, unmask: bool = False) -> Any:
    if unmask:
        return result
    for row in result.transactions:
        if row.get("account_name_masked"):
            row["account_name_masked"] = mask_name(row["account_name_masked"])
        if row.get("account_no_masked"):
            row["account_no_masked"] = mask_wallet_id(row["account_no_masked"])
        if row.get("card_no_masked"):
            row["card_no_masked"] = mask_card_number(row["card_no_masked"])
        for key, value in list(row.items()):
            if isinstance(value, str) and key not in {
                "source_file",
                "provider",
                "account_name_masked",
                "account_no_masked",
                "card_no_masked",
                "raw_line",
            }:
                row[key] = redact_free_text(value)
        if row.get("raw_line"):
            row["raw_line"] = "[MASKED RAW LINE - use --unmask for local review]"
    for row in result.summaries:
        for key in list(row):
            lowered = key.lower()
            if "name" in lowered and row[key]:
                row[key] = mask_name(str(row[key]))
            elif ("card" in lowered or "account" in lowered or "wallet" in lowered) and row[key]:
                row[key] = mask_card_number(str(row[key])) if "card" in lowered else mask_wallet_id(str(row[key]))
    for collection in (result.exceptions, result.raw_extract):
        for row in collection:
            for key, value in list(row.items()):
                if isinstance(value, str):
                    row[key] = (
                        "[MASKED RAW LINE - use --unmask for local review]"
                        if key == "raw_line" and value
                        else redact_free_text(value)
                    )
    return result
