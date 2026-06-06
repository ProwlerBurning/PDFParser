from __future__ import annotations

import re

from src.normalize import normalize_spaces, parse_money
from src.parsers.base import ParseResult, add_exception, transaction_row
from src.privacy import mask_card_number


TRANSACTION_RE = re.compile(
    r"^(?P<transaction_date>\d{1,2}\s+[A-Z]{3})\s+"
    r"(?P<posting_date>\d{1,2}\s+[A-Z]{3})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>\d[\d,]*\.\d{2})(?:\s+(?P<cr>CR))?$",
    re.I,
)
CARD_HEADER_RE = re.compile(
    r"(?P<card_type>[A-Z][A-Z ]+?)\s*-\s*(?P<card>(?:\d[ -]?){12,19})",
    re.I,
)
IGNORED_EXACT = {"CARD", "CARD PAYMENT"}


class HongLeongParser:
    provider = "Hong Leong Bank"
    statement_type = "credit_card"

    def parse_text(self, text: str, source_file: str, page_no: int | None = None) -> ParseResult:
        result = ParseResult(processing_mode="text")
        lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
        statement_date = self._metadata(lines, r"STATEMENT DATE\s*:?\s*(.+)")
        due_date = self._metadata(lines, r"PAYMENT DUE DATE\s*:?\s*(.+)")
        credit_limit = self._money_metadata(lines, r"(?:COMBINE|COMBINED) CREDIT LIMIT.*?([\d,]+\.\d{2})")
        current_balance = self._money_metadata(lines, r"CURRENT BALANCE.*?([\d,]+\.\d{2})")
        minimum_payment = self._money_metadata(lines, r"MINIMUM PAYMENT.*?([\d,]+\.\d{2})")
        previous_balance = self._money_metadata(lines, r"PREVIOUS BALANCE.*?([\d,]+\.\d{2})")
        total_balance = self._money_metadata(lines, r"TOTAL BALANCE.*?([\d,]+\.\d{2})")

        card_type = None
        card_number = None
        in_transactions = False
        for index, line in enumerate(lines, start=1):
            upper = line.upper()
            result.raw_extract.append(
                {"source_file": source_file, "provider": self.provider, "page_no": page_no, "line_no": index, "raw_line": line}
            )
            if "YOUR TRANSACTION DETAILS" in upper:
                in_transactions = True
                continue
            if any(
                marker in upper
                for marker in (
                    "CREDIT CARD OVERPAYMENT",
                    "IMPORTANT INFORMATION",
                    "SAY YES TO ONLINE FUND TRANSFERS",
                )
            ):
                if not in_transactions:
                    continue
            header = CARD_HEADER_RE.search(line)
            if header:
                card_type = normalize_spaces(header.group("card_type")).upper()
                card_number = re.sub(r"\D", "", header.group("card"))
                in_transactions = True
                continue
            if not in_transactions:
                continue
            match = TRANSACTION_RE.match(line)
            if not match:
                if self._is_ignorable_continuation(line):
                    continue
                continue
            raw_amount = match.group("amount") + (" CR" if match.group("cr") else "")
            amount = parse_money(match.group("amount")) or 0.0
            is_credit = bool(match.group("cr")) or "PAYMENT RECEIVED - THANK YOU" in match.group("description").upper()
            signed_amount = amount if is_credit else -amount
            result.transactions.append(
                transaction_row(
                    source_file=source_file,
                    provider=self.provider,
                    statement_type=self.statement_type,
                    statement_date=statement_date,
                    card_type=card_type,
                    card_no_masked=mask_card_number(card_number),
                    transaction_date=match.group("transaction_date").upper(),
                    posting_date=match.group("posting_date").upper(),
                    description=normalize_spaces(match.group("description")),
                    amount_raw=raw_amount,
                    amount=signed_amount,
                    direction="credit" if is_credit else "debit",
                    currency="MYR",
                    page_no=page_no,
                    confidence=1.0,
                    raw_line=line,
                )
            )

        summary = {
            "source_file": source_file,
            "provider": self.provider,
            "statement_type": self.statement_type,
            "processing_mode": "text",
            "statement_date": statement_date,
            "payment_due_date": due_date,
            "combined_credit_limit": credit_limit,
            "current_balance": current_balance,
            "minimum_payment": minimum_payment,
            "previous_balance": previous_balance,
            "total_balance": total_balance,
            "card_type": card_type,
            "card_no_masked": mask_card_number(card_number),
            "transaction_count": len(result.transactions),
        }
        result.summaries.append(summary)
        if previous_balance is not None and total_balance is not None:
            debits = -sum(row["amount"] for row in result.transactions if row["amount"] < 0)
            credits = sum(row["amount"] for row in result.transactions if row["amount"] > 0)
            calculated = previous_balance + debits - credits
            if abs(calculated - total_balance) > 0.01:
                add_exception(
                    result,
                    source_file,
                    self.provider,
                    f"Balance validation mismatch: calculated {calculated:.2f}, statement {total_balance:.2f}",
                )
        if not result.transactions:
            add_exception(result, source_file, self.provider, "No Hong Leong transactions parsed")
        return result

    @staticmethod
    def _metadata(lines: list[str], pattern: str) -> str | None:
        regex = re.compile(pattern, re.I)
        for line in lines:
            match = regex.search(line)
            if match:
                return normalize_spaces(match.group(1))
        return None

    @staticmethod
    def _money_metadata(lines: list[str], pattern: str) -> float | None:
        regex = re.compile(pattern, re.I)
        for line in lines:
            match = regex.search(line)
            if match:
                return parse_money(match.group(1))
        return None

    @staticmethod
    def _is_ignorable_continuation(line: str) -> bool:
        upper = line.upper()
        if upper in IGNORED_EXACT:
            return True
        if re.fullmatch(r"\d{12,24}(?:_\d+\s+\d+)?", line):
            return True
        return bool(re.fullmatch(r"\d{12,19}_\d+\s+\d+", line))
