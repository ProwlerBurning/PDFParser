from __future__ import annotations

import re

from src.normalize import normalize_spaces, parse_money
from src.parsers.base import ParseResult, add_exception, transaction_row


DATE_START_RE = re.compile(r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\b")
RM_AMOUNT_RE = re.compile(
    r"\bRM\s*(?P<amount>-?\d[\d,]*\.\d{2})\b",
    re.I,
)
BARE_AMOUNT_RE = re.compile(
    r"(?<![\w.])(?P<amount>-?\d[\d,]*\.\d{2})\b",
    re.I,
)
TNG_TEXT_TABLE_HEADER = (
    "TRANSACTION DATE TIME TRANSACTION TYPE TRANSACTION AMOUNT "
    "TRANSACTION DIRECTION TRANSACTION STATUS TRANSACTION REFERENCE ID"
)
TNG_TEXT_TABLE_ROW_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<type>\S+)\s+RM\s*"
    r"(?P<amount>-?[\d,]+\.\d{2})\s+"
    r"(?P<direction>DR|CR)\s+"
    r"(?P<status>\S+)\s+"
    r"(?P<reference>\S+)\s*$",
    re.I,
)
FOOTER_RE = re.compile(r"\*?\s*This is a system generated email.*$", re.I)
SPLIT_RM_DECIMAL_RE = re.compile(
    r"\bRM\s*([A-Za-z0-9,]+)\.([A-Za-z0-9])\s+([A-Za-z0-9])(?=\s|$)",
    re.I,
)
OCR_RM_AMOUNT_RE = re.compile(
    r"\bRM\s*([A-Za-z0-9,]+)\.([A-Za-z0-9]{2})(?=\s|$)",
    re.I,
)
KNOWN_TYPES = [
    "DUITNOW_RECEIVEFROM",
    "TRANSFER TO WALLET",
    "PAYDIRECT PAYMENT",
    "DUITNOW QR",
    "CARD RELOAD",
    "PAYMENT",
]
CREDIT_TYPES = {"DUITNOW_RECEIVEFROM", "CARD RELOAD"}
DEBIT_TYPES = {"PAYDIRECT PAYMENT", "PAYMENT", "TRANSFER TO WALLET", "DUITNOW QR"}


def _normalize_ocr_amount_part(value: str) -> str:
    return value.replace("O", "0").replace("o", "0").replace("G", "").replace("g", "")


def normalize_tng_ocr_text(text: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        line = FOOTER_RE.sub("", raw_line)
        line = re.sub(r"\bTNGOW3MY\s+1\b", "TNGOW3MY1", line, flags=re.I)
        line = SPLIT_RM_DECIMAL_RE.sub(
            lambda match: (
                f"RM{_normalize_ocr_amount_part(match.group(1))}."
                f"{_normalize_ocr_amount_part(match.group(2) + match.group(3))}"
            ),
            line,
        )
        line = OCR_RM_AMOUNT_RE.sub(
            lambda match: (
                f"RM{_normalize_ocr_amount_part(match.group(1))}."
                f"{_normalize_ocr_amount_part(match.group(2))}"
            ),
            line,
        )
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def infer_direction(
    previous_balance: float | None,
    new_balance: float | None,
    amount: float,
    transaction_type: str,
) -> tuple[str | None, float]:
    if previous_balance is not None and new_balance is not None:
        if abs((previous_balance - amount) - new_balance) <= 0.02:
            return "debit", -abs(amount)
        if abs((previous_balance + amount) - new_balance) <= 0.02:
            return "credit", abs(amount)
    normalized = transaction_type.upper().strip()
    if normalized in CREDIT_TYPES:
        return "credit", abs(amount)
    if normalized in DEBIT_TYPES:
        return "debit", -abs(amount)
    return None, amount


class TngEwalletParser:
    provider = "Touch 'n Go eWallet"
    statement_type = "ewallet"

    def parse_text(self, text: str, source_file: str, page_no: int | None = None) -> ParseResult:
        text = normalize_tng_ocr_text(text)
        if TNG_TEXT_TABLE_HEADER in normalize_spaces(text).upper():
            return self._parse_text_table(text, source_file, page_no)

        result = ParseResult(processing_mode="ocr")
        lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
        registered_name = self._field(lines, r"REGISTERED NAME\s*:?\s*(.+)")
        wallet_id = self._field(lines, r"WALLET ID\s*:?\s*([\d -]+)")
        account_status = self._field(lines, r"ACCOUNT STATUS\s*:?\s*(.+)")
        generated = self._field(lines, r"GENERATED DATE(?: AND TIME)?\s*:?\s*(.+)")
        period = self._field(lines, r"TRANSACTION PERIOD\s*:?\s*(.+)")
        grouped = self._group_rows(lines)
        previous_balance = None
        for index, raw_line in enumerate(grouped, start=1):
            result.raw_extract.append(
                {"source_file": source_file, "provider": self.provider, "page_no": page_no, "line_no": index, "raw_line": raw_line}
            )
            row = self._parse_row(raw_line)
            if row is None:
                add_exception(result, source_file, self.provider, "Unparsed TNG transaction row", raw_line, page_no)
                continue
            direction, signed_amount = infer_direction(
                previous_balance, row["balance"], row["amount"], row["transaction_type"]
            )
            confidence = 0.95 if direction else 0.55
            transaction = transaction_row(
                source_file=source_file,
                provider=self.provider,
                statement_type=self.statement_type,
                statement_period=period,
                account_name_masked=registered_name,
                account_no_masked=wallet_id,
                transaction_date=row["date"],
                status=row["status"],
                transaction_type=row["transaction_type"],
                description=row["description"],
                reference=row["reference"],
                details=row["details"],
                amount_raw=row["amount_raw"],
                amount=signed_amount,
                direction=direction,
                currency="MYR",
                balance=row["balance"],
                page_no=page_no,
                confidence=confidence,
                raw_line=raw_line,
            )
            result.transactions.append(transaction)
            if direction is None:
                add_exception(result, source_file, self.provider, "Unable to infer TNG direction", raw_line, page_no)
            if row["balance"] is not None:
                previous_balance = row["balance"]
        result.summaries.append(
            {
                "source_file": source_file,
                "provider": self.provider,
                "statement_type": self.statement_type,
                "processing_mode": "ocr",
                "statement_period": period,
                "account_name_masked": registered_name,
                "account_no_masked": wallet_id,
                "account_status": account_status,
                "generated_date_time": generated,
                "transaction_count": len(result.transactions),
            }
        )
        if not result.transactions:
            add_exception(result, source_file, self.provider, "No TNG transactions parsed")
        return result

    def _parse_text_table(
        self,
        text: str,
        source_file: str,
        page_no: int | None,
    ) -> ParseResult:
        result = ParseResult(processing_mode="text")
        lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
        line_no = 0
        for line in lines:
            match = TNG_TEXT_TABLE_ROW_RE.match(line)
            if not match:
                continue
            line_no += 1
            amount = parse_money(match.group("amount"))
            if amount is None:
                add_exception(
                    result,
                    source_file,
                    self.provider,
                    "Unparsed TNG text-table amount",
                    line,
                    page_no,
                )
                continue
            direction = "debit" if match.group("direction").upper() == "DR" else "credit"
            signed_amount = -abs(amount) if direction == "debit" else abs(amount)
            result.raw_extract.append(
                {
                    "source_file": source_file,
                    "provider": self.provider,
                    "page_no": page_no,
                    "line_no": line_no,
                    "raw_line": line,
                }
            )
            result.transactions.append(
                transaction_row(
                    source_file=source_file,
                    provider=self.provider,
                    statement_type=self.statement_type,
                    transaction_date=f"{match.group('date')} {match.group('time')}",
                    status=match.group("status").title(),
                    transaction_type=match.group("type"),
                    reference=match.group("reference"),
                    amount_raw=match.group("amount"),
                    amount=signed_amount,
                    direction=direction,
                    currency="MYR",
                    balance=None,
                    page_no=page_no,
                    confidence=1.0,
                    raw_line=line,
                )
            )
        result.summaries.append(
            {
                "source_file": source_file,
                "provider": self.provider,
                "statement_type": self.statement_type,
                "processing_mode": "text",
                "transaction_count": len(result.transactions),
            }
        )
        if not result.transactions:
            add_exception(result, source_file, self.provider, "No TNG transactions parsed")
        return result

    @staticmethod
    def _field(lines: list[str], pattern: str) -> str | None:
        regex = re.compile(pattern, re.I)
        for line in lines:
            match = regex.search(line)
            if match:
                return normalize_spaces(match.group(1))
        return None

    @staticmethod
    def _group_rows(lines: list[str]) -> list[str]:
        rows: list[str] = []
        current: list[str] = []
        for line in lines:
            if line.lower().startswith("this is a system generated email"):
                break
            if DATE_START_RE.match(line):
                if current:
                    rows.append(normalize_spaces(" ".join(current)))
                current = [line]
            elif current:
                current.append(line)
        if current:
            rows.append(normalize_spaces(" ".join(current)))
        return rows

    @staticmethod
    def _parse_row(line: str) -> dict[str, object] | None:
        date_match = DATE_START_RE.match(line)
        amount_matches = list(RM_AMOUNT_RE.finditer(line))
        if not amount_matches:
            amount_matches = list(BARE_AMOUNT_RE.finditer(line))
        if not date_match or not amount_matches:
            return None
        amount_match = amount_matches[0]
        balance_match = amount_matches[1] if len(amount_matches) > 1 else None
        middle = normalize_spaces(line[date_match.end():amount_match.start()])
        status_match = re.match(
            r"(?P<status>SUCCESS(?:FUL)?|FAILED|PENDING|CANCELLED|REVERSED)\s+(?P<body>.+)",
            middle,
            re.I,
        )
        if not status_match:
            return None
        body = status_match.group("body")
        upper_body = body.upper()
        transaction_type = ""
        type_end = 0
        for known in sorted(KNOWN_TYPES, key=len, reverse=True):
            if upper_body.startswith(known):
                transaction_type = known
                type_end = len(known)
                break
        if not transaction_type:
            first, _, rest = body.partition(" ")
            transaction_type, body_after_type = first, rest
        else:
            body_after_type = body[type_end:].strip()
        parts = body_after_type.split()
        reference = parts[0] if parts else ""
        remaining = " ".join(parts[1:])
        description = remaining
        details = ""
        if len(parts) > 3:
            split_at = max(1, len(parts) // 2)
            description = " ".join(parts[:split_at])
            details = " ".join(parts[split_at:])
        trailing_start = balance_match.end() if balance_match else amount_match.end()
        trailing_details = normalize_spaces(line[trailing_start:])
        if trailing_details:
            details = normalize_spaces(f"{details} {trailing_details}")
        amount = parse_money(amount_match.group("amount"))
        balance = parse_money(balance_match.group("amount")) if balance_match else None
        if amount is None:
            return None
        return {
            "date": date_match.group("date"),
            "status": status_match.group("status").title(),
            "transaction_type": transaction_type,
            "reference": reference,
            "description": description,
            "details": details,
            "amount_raw": amount_match.group("amount"),
            "amount": abs(amount),
            "balance": balance,
        }
