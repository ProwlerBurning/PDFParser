from __future__ import annotations

import re

from collections import defaultdict
from typing import Any

from src.normalize import AMOUNT_TOKEN_RE, normalize_spaces, parse_amount_token, parse_money
from src.parsers.base import ParseResult, add_exception, transaction_row


CARD_TYPES = (
    "VISA REWARDS PLATINUM",
    "SIMPLY CASH CREDIT CARD",
    "VISA PLATINUM",
    "MPS FLEXPAY",
)
DATE_START_RE = re.compile(r"^(?P<posting>\d{1,2}\s+[A-Z]{3})\s+(?P<transaction>\d{1,2}\s+[A-Z]{3})\s+", re.I)
MONTHS = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}
DATE_PART_RE = re.compile(r"^(?P<day>\d{1,2})\s+(?P<month>[A-Z]{3})$", re.I)
INVALID_DATE_REASON = "Unrecoverable SC transaction row: invalid OCR transaction date"
# A bank reference id, possibly split across spaces by OCR (e.g. "24553585 179280603677604").
REFERENCE_RE = re.compile(r"\d[\d ]{6,}\d")
# Stray currency / column-label tokens left behind once amounts are removed.
NOISE_TOKENS = {"RM", "MYR", "CR", "TXN", "REF", "REF:", "|"}
CARD_NUMBER_RE = re.compile(r"(?:[0-9X*][ -]?){12,19}", re.I)
IGNORE_MARKERS = (
    "CREDIT CARD IMPORTANT INFORMATION",
    "MAKLUMAT PENTING KAD KREDIT",
    "HOW TO PAY",
    "CASHBACK BALANCE",
    "REWARDS POINTS SUMMARY",
)
# Summary/notice phrases that must never enter the transaction set via fallback.
NON_TRANSACTION_MARKERS = (
    "PREVIOUS BALANCE",
    "NEW BALANCE",
    "TOTAL BALANCE",
    "SUB TOTAL",
    "SUBTOTAL",
    "MINIMUM PAYMENT",
    "REWARD",
    "CASHBACK",
    "ANNUAL FEE SUMMARY",
    "PAYMENT SUMMARY",
    "NOTICE",
    "SUMMARY",
)


def _fallback_key(row: dict[str, Any]) -> tuple:
    return (
        row.get("source_file"),
        row.get("card_no_masked"),
        row.get("posting_date"),
        row.get("transaction_date"),
        row.get("reference"),
        row.get("amount"),
    )


def _is_non_transaction_row(description: str | None) -> bool:
    upper = (description or "").upper()
    return any(marker in upper for marker in NON_TRANSACTION_MARKERS)


def _amount_is_percentage(row: dict[str, Any]) -> bool:
    # Guards against a 250-dpi row whose amount column was empty, so the parser
    # grabbed a rate like "17.09" out of "EFF 17.09%" instead of a real amount.
    amount_raw = (row.get("amount_raw") or "").strip()
    if not amount_raw:
        return False
    return re.search(re.escape(amount_raw) + r"\s*%", row.get("raw_line") or "") is not None


def select_sc_fallback_rows(
    primary: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pick 250-dpi rows safe to add as a fallback for rows the 350 pass lost.

    A candidate is added only if it is a valid SC transaction (semantic dates,
    amount, direction), is not a summary/non-transaction row, is not a rate
    misread, and is not already represented in the primary (350) set by
    deterministic key, by reference, or by an equal signed amount within the
    same statement (which catches OCR re-segmentation churn). Deterministic and
    free of any merchant- or amount-specific special cases.
    """
    primary_keys = {_fallback_key(row) for row in primary}
    amounts_by_file: dict[Any, set] = defaultdict(set)
    refs_by_file: dict[Any, set] = defaultdict(set)
    for row in primary:
        source = row.get("source_file")
        amounts_by_file[source].add(row.get("amount"))
        reference = re.sub(r"\D", "", row.get("reference") or "")
        if reference:
            refs_by_file[source].add(reference)

    added: list[dict[str, Any]] = []
    added_keys: set = set()
    for candidate in candidates:
        if not (
            StandardCharteredParser._valid_date(candidate.get("posting_date"))
            and StandardCharteredParser._valid_date(candidate.get("transaction_date"))
        ):
            continue
        if candidate.get("amount") is None:
            continue
        if candidate.get("direction") not in ("debit", "credit"):
            continue
        if _is_non_transaction_row(candidate.get("description")):
            continue
        if _amount_is_percentage(candidate):
            continue
        key = _fallback_key(candidate)
        if key in primary_keys or key in added_keys:
            continue
        source = candidate.get("source_file")
        reference = re.sub(r"\D", "", candidate.get("reference") or "")
        if reference and reference in refs_by_file[source]:
            continue
        if candidate.get("amount") in amounts_by_file[source]:
            continue
        added.append(candidate)
        added_keys.add(key)
    return added


class StandardCharteredParser:
    provider = "Standard Chartered"
    statement_type = "credit_card"

    def parse_text(self, text: str, source_file: str, page_no: int | None = None) -> ParseResult:
        result = ParseResult(processing_mode="ocr")
        lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
        statement_date = self._metadata(lines, r"STATEMENT DATE\s*:?\s*(.+)")
        grouped = self._group_rows(lines)
        current_card_type = None
        current_card_number = None
        for index, item in enumerate(grouped, start=1):
            kind, value = item
            if kind == "card_type":
                current_card_type = value
                current_card_number = None
                continue
            if kind == "card_number":
                current_card_number = self._normalize_card_identity(value)
                continue
            raw_line = value
            result.raw_extract.append(
                {"source_file": source_file, "provider": self.provider, "page_no": page_no, "line_no": index, "raw_line": raw_line}
            )
            parsed = self._parse_row(raw_line)
            if parsed is None:
                add_exception(result, source_file, self.provider, "Unparsed Standard Chartered transaction row", raw_line, page_no)
                continue
            if not (self._valid_date(parsed["posting_date"]) and self._valid_date(parsed["transaction_date"])):
                add_exception(result, source_file, self.provider, INVALID_DATE_REASON, raw_line, page_no)
                continue
            amount = parsed["amount"]
            is_credit = parsed["is_credit"]
            result.transactions.append(
                transaction_row(
                    source_file=source_file,
                    provider=self.provider,
                    statement_type=self.statement_type,
                    statement_date=statement_date,
                    card_type=current_card_type,
                    card_no_masked=current_card_number,
                    transaction_date=parsed["transaction_date"],
                    posting_date=parsed["posting_date"],
                    description=parsed["description"],
                    reference=parsed["reference"],
                    amount_raw=parsed["amount_raw"],
                    amount=amount if is_credit else -amount,
                    direction="credit" if is_credit else "debit",
                    currency="MYR",
                    page_no=page_no,
                    confidence=0.85 if current_card_type else 0.6,
                    raw_line=raw_line,
                )
            )
            if not current_card_type:
                add_exception(result, source_file, self.provider, "Transaction has no detected card section", raw_line, page_no)
        result.summaries.append(
            {
                "source_file": source_file,
                "provider": self.provider,
                "statement_type": self.statement_type,
                "processing_mode": "ocr",
                "statement_date": statement_date,
                "transaction_count": len(result.transactions),
                **self._summary_values(lines),
            }
        )
        if not result.transactions:
            add_exception(result, source_file, self.provider, "No Standard Chartered transactions parsed")
        return result

    @staticmethod
    def _valid_date(value: str | None) -> bool:
        match = DATE_PART_RE.match(value or "")
        if not match:
            return False
        return 1 <= int(match.group("day")) <= 31 and match.group("month").upper() in MONTHS

    @staticmethod
    def _normalize_card_identity(value: str) -> str:
        return re.sub(r"[^0-9X*]", "", value.upper())

    @staticmethod
    def _metadata(lines: list[str], pattern: str) -> str | None:
        regex = re.compile(pattern, re.I)
        for line in lines:
            match = regex.search(line)
            if match:
                return normalize_spaces(match.group(1))
        return None

    @staticmethod
    def _group_rows(lines: list[str]) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        current: list[str] = []
        ignored_page = False
        for line in lines:
            upper = line.upper()
            if any(marker in upper for marker in IGNORE_MARKERS):
                ignored_page = True
                if current:
                    items.append(("row", normalize_spaces(" ".join(current))))
                    current = []
                continue
            card_type = next((card for card in CARD_TYPES if card in upper), None)
            if card_type:
                ignored_page = False
                if current:
                    items.append(("row", normalize_spaces(" ".join(current))))
                    current = []
                items.append(("card_type", card_type))
                continue
            number_match = CARD_NUMBER_RE.fullmatch(line)
            if number_match and not ignored_page:
                items.append(("card_number", number_match.group(0)))
                continue
            if ignored_page:
                continue
            if DATE_START_RE.match(line):
                if current:
                    items.append(("row", normalize_spaces(" ".join(current))))
                current = [line]
            elif current:
                current.append(line)
        if current:
            items.append(("row", normalize_spaces(" ".join(current))))
        return items

    @staticmethod
    def _parse_row(line: str) -> dict[str, object] | None:
        date_match = DATE_START_RE.match(line)
        if not date_match:
            return None
        rest = normalize_spaces(line[date_match.end():])
        amounts = list(AMOUNT_TOKEN_RE.finditer(rest))
        if not amounts:
            # No recoverable RM amount column on this row; keep it as an exception.
            return None
        # The RM Amount column is the rightmost amount; an immediately preceding
        # amount is the foreign-currency value and is not the charged total.
        rm_match = amounts[-1]
        amount = parse_amount_token(rm_match.group(0))
        if amount is None:
            return None
        is_credit = bool(rm_match.group("cr"))
        # Remove every amount token so the remainder holds merchant, location and
        # the reference id (which may sit before or after the amount column).
        remainder = normalize_spaces(AMOUNT_TOKEN_RE.sub(" ", rest))
        reference, description = StandardCharteredParser._split_reference(remainder)
        return {
            "posting_date": date_match.group("posting").title(),
            "transaction_date": date_match.group("transaction").title(),
            "description": description,
            "reference": reference,
            "amount_raw": rm_match.group(0).strip(),
            "amount": abs(amount),
            "is_credit": is_credit,
        }

    @staticmethod
    def _split_reference(remainder: str) -> tuple[str, str]:
        reference = ""
        ref_match = max(
            REFERENCE_RE.finditer(remainder),
            key=lambda match: len(re.sub(r"\D", "", match.group(0))),
            default=None,
        )
        if ref_match and len(re.sub(r"\D", "", ref_match.group(0))) >= 8:
            reference = re.sub(r"\s", "", ref_match.group(0))
            remainder = remainder[: ref_match.start()] + " " + remainder[ref_match.end():]
        tokens = [
            token
            for token in remainder.split()
            if token.upper() not in NOISE_TOKENS
        ]
        return reference, normalize_spaces(" ".join(tokens))

    @staticmethod
    def _summary_values(lines: list[str]) -> dict[str, float | str | None]:
        fields = {
            "payment_due_date": r"PAYMENT DUE DATE\s*:?\s*(.+)",
            "new_balance": r"NEW BALANCE.*?([\d,]+\.\d{2})",
            "minimum_payment": r"MINIMUM PAYMENT.*?([\d,]+\.\d{2})",
            "previous_balance": r"PREVIOUS BALANCE.*?([\d,]+\.\d{2})",
            "payments": r"PAYMENTS.*?([\d,]+\.\d{2})",
            "credits": r"CREDITS.*?([\d,]+\.\d{2})",
            "purchases": r"PURCHASES.*?([\d,]+\.\d{2})",
            "charges": r"CHARGES.*?([\d,]+\.\d{2})",
        }
        values: dict[str, float | str | None] = {}
        for key, pattern in fields.items():
            regex = re.compile(pattern, re.I)
            values[key] = None
            for line in lines:
                match = regex.search(line)
                if match:
                    values[key] = parse_money(match.group(1)) if key != "payment_due_date" else normalize_spaces(match.group(1))
                    break
        return values
