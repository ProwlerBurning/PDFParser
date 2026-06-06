from __future__ import annotations

from src.parsers.base import ParseResult, add_exception


def validate_standard_chartered(result: ParseResult) -> None:
    for summary in result.summaries:
        previous = summary.get("previous_balance")
        new_balance = summary.get("new_balance")
        if previous is None or new_balance is None:
            continue
        debits = -sum(row["amount"] for row in result.transactions if row.get("amount", 0) < 0)
        credits = sum(row["amount"] for row in result.transactions if row.get("amount", 0) > 0)
        calculated = previous + debits - credits
        if abs(calculated - new_balance) > 0.01:
            add_exception(
                result,
                summary["source_file"],
                summary["provider"],
                f"Balance validation mismatch: calculated {calculated:.2f}, statement {new_balance:.2f}",
            )
