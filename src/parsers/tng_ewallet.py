from __future__ import annotations

import re

from src.normalize import normalize_spaces, parse_money
from src.parsers.base import ParseResult, add_exception, transaction_row
from src.privacy import mask_name, mask_wallet_id


DATE_START_RE = re.compile(r"^(?P<date>\d{1,2}/\d{1,2}/\d{4})\b")
AMOUNT_PAIR_RE = re.compile(
    r"(?:RM\s*)?(?P<amount>-?[\dO][\dO,]*\.[\dO]{2})\s+"
    r"(?:RM\s*)?(?P<balance>-?[\dO][\dO,]*\.[\dO]{2})",
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
                account_name_masked=mask_name(registered_name),
                account_no_masked=mask_wallet_id(wallet_id),
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
            previous_balance = row["balance"]
        result.summaries.append(
            {
                "source_file": source_file,
                "provider": self.provider,
                "statement_type": self.statement_type,
                "processing_mode": "ocr",
                "statement_period": period,
                "account_name_masked": mask_name(registered_name),
                "account_no_masked": mask_wallet_id(wallet_id),
                "account_status": account_status,
                "generated_date_time": generated,
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
        amount_match = AMOUNT_PAIR_RE.search(line)
        if not date_match or not amount_match:
            return None
        middle = normalize_spaces(line[date_match.end():amount_match.start()])
        status_match = re.match(
            r"(?P<status>SUCCESS(?:FUL)?|FAILED|PENDING|CANCELLED)\s+(?P<body>.+)",
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
        trailing_details = normalize_spaces(line[amount_match.end():])
        if trailing_details:
            details = normalize_spaces(f"{details} {trailing_details}")
        amount = parse_money(amount_match.group("amount").upper().replace("O", "0"))
        balance = parse_money(amount_match.group("balance").upper().replace("O", "0"))
        if amount is None or balance is None:
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
