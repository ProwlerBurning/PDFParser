from __future__ import annotations

import re

from src.normalize import normalize_spaces, parse_money
from src.parsers.base import ParseResult, add_exception, transaction_row
from src.privacy import mask_card_number


CARD_TYPES = (
    "VISA REWARDS PLATINUM",
    "SIMPLY CASH CREDIT CARD",
    "VISA PLATINUM",
    "MPS FLEXPAY",
)
DATE_START_RE = re.compile(r"^(?P<posting>\d{1,2}\s+[A-Z]{3})\s+(?P<transaction>\d{1,2}\s+[A-Z]{3})\s+", re.I)
AMOUNT_END_RE = re.compile(
    r"(?:(?P<foreign>\d[\d,]*\.\d{2})\s+)?(?P<rm>\d[\d,]*\.\d{2})(?:\s+(?P<cr>CR))?",
    re.I,
)
CARD_NUMBER_RE = re.compile(r"(?:[0-9X*][ -]?){12,19}", re.I)
IGNORE_MARKERS = (
    "CREDIT CARD IMPORTANT INFORMATION",
    "MAKLUMAT PENTING KAD KREDIT",
    "HOW TO PAY",
    "CASHBACK BALANCE",
    "REWARDS POINTS SUMMARY",
)


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
            amount = parsed["amount"]
            is_credit = parsed["is_credit"]
            result.transactions.append(
                transaction_row(
                    source_file=source_file,
                    provider=self.provider,
                    statement_type=self.statement_type,
                    statement_date=statement_date,
                    card_type=current_card_type,
                    card_no_masked=mask_card_number(current_card_number),
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
        amount_match = AMOUNT_END_RE.search(line)
        if not date_match or not amount_match:
            return None
        middle = normalize_spaces(line[date_match.end():amount_match.start()])
        trailing = normalize_spaces(line[amount_match.end():])
        tokens = middle.split()
        reference = ""
        description = middle
        if tokens and re.fullmatch(r"[A-Z0-9/-]{5,}", tokens[-1], re.I):
            reference = tokens[-1]
            description = " ".join(tokens[:-1])
        if description.endswith(" MYR"):
            description = description[:-4].strip()
        if trailing:
            description = normalize_spaces(f"{description} {trailing}")
        amount = parse_money(amount_match.group("rm"))
        if amount is None:
            return None
        return {
            "posting_date": date_match.group("posting").title(),
            "transaction_date": date_match.group("transaction").title(),
            "description": description,
            "reference": reference,
            "amount_raw": amount_match.group(0),
            "amount": abs(amount),
            "is_credit": bool(amount_match.group("cr")),
        }

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
