#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from extract import process_pdf
from src.export_excel import export_workbook


SAMPLES = [
    Path.home() / "Downloads" / "tng_ewallet_transactions_20250601_20250630.pdf",
    Path.home() / "Downloads" / "SC statement 202501 Jan.pdf",
    Path.home() / "Downloads" / "ESSENTIAL VISA CLASSIC 012025.pdf",
]
REQUIRED_SHEETS = [
    "Transactions",
    "Statement_Summary",
    "Exceptions",
    "Raw_Extract",
]


class SilentLogger:
    def info(self, *args, **kwargs) -> None:
        pass


def main() -> int:
    missing = [path for path in SAMPLES if not path.is_file()]
    if missing:
        return 2

    transactions = []
    summaries = []
    exceptions = []
    raw_extract = []
    cache_root = PROJECT_ROOT / "cache"
    logger = SilentLogger()
    for path in SAMPLES:
        result = process_pdf(path, cache_root, None, False, False, logger)
        transactions.extend(result.transactions)
        summaries.extend(result.summaries)
        exceptions.extend(result.exceptions)
        raw_extract.extend(result.raw_extract)

    with tempfile.TemporaryDirectory(prefix="statement-parser-verify-") as directory:
        workbook_path = Path(directory) / "statements.xlsx"
        export_workbook(
            workbook_path,
            transactions,
            summaries,
            exceptions,
            raw_extract,
        )
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        if workbook.sheetnames != REQUIRED_SHEETS:
            return 3
        privacy_passed = not any(
            isinstance(cell.value, str) and re.search(r"\d{9,}", cell.value)
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
        )

    transaction_counts = Counter(row["provider"] for row in transactions)
    exception_counts = Counter(row["provider"] for row in exceptions)
    modes = {row["provider"]: row["processing_mode"] for row in summaries}
    for provider in sorted(transaction_counts):
        print(
            f"provider={provider} "
            f"transactions={transaction_counts[provider]} "
            f"exceptions={exception_counts[provider]} "
            f"mode={modes[provider]}"
        )
    print(f"privacy_scan={'pass' if privacy_passed else 'fail'}")
    return 0 if privacy_passed else 4


if __name__ == "__main__":
    raise SystemExit(main())
