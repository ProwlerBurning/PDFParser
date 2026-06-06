from pathlib import Path

from openpyxl import load_workbook

from src.export_excel import export_workbook
from src.pdf_detect import detect_statement_type, processing_mode_for


def test_detects_all_supported_statement_types():
    assert detect_statement_type("TNG WALLET TRANSACTION HISTORY") == "tng"
    assert detect_statement_type("Standard Chartered Credit Card Statement") == "sc"
    assert detect_statement_type("YOUR TRANSACTION DETAILS ESSENTIAL VISA CLASSIC") == "hlb"


def test_hlb_uses_text_and_sc_tng_use_ocr():
    assert processing_mode_for("hlb", has_useful_text=True) == "text"
    assert processing_mode_for("tng", has_useful_text=False) == "ocr"
    assert processing_mode_for("sc", has_useful_text=False) == "ocr"


def test_export_has_required_sheets(tmp_path: Path):
    output = tmp_path / "result.xlsx"
    export_workbook(
        output,
        transactions=[],
        summaries=[],
        exceptions=[],
        raw_extract=[],
    )
    workbook = load_workbook(output, read_only=True)
    assert workbook.sheetnames == [
        "Transactions",
        "Statement_Summary",
        "Exceptions",
        "Raw_Extract",
    ]
