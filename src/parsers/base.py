from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TRANSACTION_COLUMNS = [
    "source_file",
    "provider",
    "statement_type",
    "statement_date",
    "statement_period",
    "account_name_masked",
    "account_no_masked",
    "card_type",
    "card_no_masked",
    "transaction_date",
    "posting_date",
    "status",
    "transaction_type",
    "description",
    "reference",
    "details",
    "amount_raw",
    "amount",
    "direction",
    "currency",
    "balance",
    "page_no",
    "confidence",
    "raw_line",
]


@dataclass
class ParseResult:
    transactions: list[dict[str, Any]] = field(default_factory=list)
    summaries: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    raw_extract: list[dict[str, Any]] = field(default_factory=list)
    processing_mode: str = ""


def transaction_row(**values: Any) -> dict[str, Any]:
    row = {column: None for column in TRANSACTION_COLUMNS}
    row.update(values)
    return row


def add_exception(
    result: ParseResult,
    source_file: str,
    provider: str,
    reason: str,
    raw_line: str = "",
    page_no: int | None = None,
) -> None:
    result.exceptions.append(
        {
            "source_file": source_file,
            "provider": provider,
            "reason": reason,
            "page_no": page_no,
            "raw_line": raw_line,
        }
    )
