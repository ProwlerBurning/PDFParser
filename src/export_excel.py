from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from src.parsers.base import TRANSACTION_COLUMNS


SHEETS = {
    "Transactions": TRANSACTION_COLUMNS,
    "Statement_Summary": [
        "source_file",
        "provider",
        "statement_type",
        "processing_mode",
        "statement_date",
        "statement_period",
        "payment_due_date",
        "transaction_count",
    ],
    "Exceptions": ["source_file", "provider", "reason", "page_no", "raw_line"],
    "Raw_Extract": ["source_file", "provider", "page_no", "line_no", "raw_line"],
}
CURRENCY_HEADERS = {
    "amount",
    "balance",
    "combined_credit_limit",
    "current_balance",
    "minimum_payment",
    "previous_balance",
    "total_balance",
    "new_balance",
    "payments",
    "credits",
    "purchases",
    "charges",
}


def _frame(rows: list[dict[str, Any]], required: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=required)
    frame = pd.DataFrame(rows)
    for column in required:
        if column not in frame.columns:
            frame[column] = None
    ordered = required + [column for column in frame.columns if column not in required]
    return frame[ordered]


def export_workbook(
    output_path: Path,
    transactions: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
    raw_extract: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    datasets = {
        "Transactions": transactions,
        "Statement_Summary": summaries,
        "Exceptions": exceptions,
        "Raw_Extract": raw_extract,
    }
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, rows in datasets.items():
            _frame(rows, SHEETS[sheet_name]).to_excel(writer, sheet_name=sheet_name, index=False)
        workbook = writer.book
        for worksheet in workbook.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = Font(bold=True)
            for column_index, column_cells in enumerate(worksheet.columns, start=1):
                header = str(column_cells[0].value or "")
                width = min(
                    60,
                    max(
                        len(header) + 2,
                        max((len(str(cell.value)) for cell in column_cells[1:] if cell.value is not None), default=0) + 2,
                    ),
                )
                worksheet.column_dimensions[get_column_letter(column_index)].width = width
                if header in CURRENCY_HEADERS:
                    for cell in column_cells[1:]:
                        cell.number_format = '"RM" #,##0.00;[Red]-"RM" #,##0.00'
