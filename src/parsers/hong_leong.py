from __future__ import annotations

import re

from src.normalize import normalize_spaces, parse_money
from src.parsers.base import ParseResult, add_exception, transaction_row


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
# First-page metadata patterns. HLB statements render the summary as a column
# table, so labels and values often live on separate native-text lines.
DATE_VALUE_RE = re.compile(r"\b\d{1,2}\s+[A-Z]{3}\s+\d{4}\b", re.I)
MONEY_VALUE_RE = re.compile(r"[\d,]+\.\d{2}")
# The single positional data row: card number, credit limit, card type,
# current balance, overdue/limit, minimum payment.
DATA_ROW_RE = re.compile(
    r"(?P<card>(?:\d{4}[ -]?){3}\d{4})\s+"
    r"(?P<limit>[\d,]+\.\d{2})\s+"
    r"(?P<card_type>[A-Z][A-Z ]+?)\s+"
    r"(?P<current>[\d,]+\.\d{2})\s+"
    r"(?P<overdue>[\d,]+\.\d{2})\s+"
    r"(?P<minimum>[\d,]+\.\d{2})\b"
)
NAME_LINE_RE = re.compile(r"^[A-Z][A-Z]+(?: [A-Z]{2,})+$")
NAME_BLOCKLIST = (
    "BANK", "STATEMENT", "PAYMENT", "CREDIT", "LIMIT", "BALANCE", "CARD",
    "VISA", "MASTER", "CLASSIC", "PLATINUM", "GOLD", "SIGNATURE", "TARIKH",
    "JUMLAH", "NOMBOR", "TRANSACTION", "DETAILS", "TOTAL", "PREVIOUS", "SUB",
    "HONG", "LEONG", "ESSENTIAL", "DETAIL", "BERHAD",
)


class HongLeongParser:
    provider = "Hong Leong Bank"
    statement_type = "credit_card"

    def parse_text(self, text: str, source_file: str, page_no: int | None = None) -> ParseResult:
        result = ParseResult(processing_mode="text")
        lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
        data_row = self._data_row(lines)
        statement_date = self._date_for_label(lines, "STATEMENT DATE")
        due_date = self._date_for_label(lines, "PAYMENT DUE DATE")
        credit_limit = self._money_for_label(
            lines, r"(?:COMBINE|COMBINED) CREDIT LIMIT"
        )
        if credit_limit is None and data_row is not None:
            credit_limit = data_row["limit"]
        # The positional data row is unambiguous; the label lookups are a
        # fallback for single-line layouts. Bilingual totals lines repeat the
        # "Minimum Payment" / "Current Balance" labels next to each other, so a
        # label search there can grab the wrong column.
        if data_row is not None:
            current_balance = data_row["current"]
            minimum_payment = data_row["minimum"]
        else:
            current_balance = self._money_for_label(lines, "CURRENT BALANCE")
            minimum_payment = self._money_for_label(lines, "MINIMUM PAYMENT")
        previous_balance = self._money_metadata(lines, r"PREVIOUS BALANCE.*?([\d,]+\.\d{2})")
        total_balance = self._money_metadata(lines, r"TOTAL BALANCE.*?([\d,]+\.\d{2})")
        cardholder_name = self._cardholder_name(lines)

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
                    card_no_masked=card_number,
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

        if card_type is None and data_row is not None:
            card_type = data_row["card_type"]
        if card_number is None and data_row is not None:
            card_number = data_row["card"]
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
            "cardholder_name": cardholder_name,
            "card_type": card_type,
            "card_no_masked": card_number,
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
    def _label_index(lines: list[str], label: str) -> int | None:
        upper = label.upper()
        for index, line in enumerate(lines):
            if upper in line.upper():
                return index
        return None

    @classmethod
    def _date_for_label(cls, lines: list[str], label: str, lookahead: int = 2) -> str | None:
        index = cls._label_index(lines, label)
        if index is None:
            return None
        for line in lines[index:index + 1 + lookahead]:
            match = DATE_VALUE_RE.search(line)
            if match:
                return normalize_spaces(match.group(0)).upper()
        return None

    @classmethod
    def _money_for_label(cls, lines: list[str], label_pattern: str, lookahead: int = 2) -> float | None:
        regex = re.compile(label_pattern, re.I)
        for index, line in enumerate(lines):
            if regex.search(line):
                for candidate in lines[index:index + 1 + lookahead]:
                    money = MONEY_VALUE_RE.search(candidate)
                    if money:
                        return parse_money(money.group(0))
        return None

    @staticmethod
    def _data_row(lines: list[str]) -> dict[str, object] | None:
        for line in lines:
            match = DATA_ROW_RE.search(line)
            if match:
                return {
                    "card": re.sub(r"\D", "", match.group("card")),
                    "limit": parse_money(match.group("limit")),
                    "card_type": normalize_spaces(match.group("card_type")).upper(),
                    "current": parse_money(match.group("current")),
                    "minimum": parse_money(match.group("minimum")),
                }
        return None

    @staticmethod
    def _cardholder_name(lines: list[str]) -> str | None:
        for line in lines[:15]:
            candidate = normalize_spaces(line)
            if not NAME_LINE_RE.fullmatch(candidate):
                continue
            if set(candidate.split()) & set(NAME_BLOCKLIST):
                continue
            return candidate
        return None

    @staticmethod
    def _is_ignorable_continuation(line: str) -> bool:
        upper = line.upper()
        if upper in IGNORED_EXACT:
            return True
        if re.fullmatch(r"\d{12,24}(?:_\d+\s+\d+)?", line):
            return True
        return bool(re.fullmatch(r"\d{12,19}_\d+\s+\d+", line))
