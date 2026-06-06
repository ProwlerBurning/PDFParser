from pathlib import Path

import pytest

from src.parsers.tng_ewallet import (
    TngEwalletParser,
    infer_direction,
    normalize_tng_ocr_text,
)


FIXTURE = Path(__file__).parent / "fixtures" / "tng_sample_ocr_text.txt"


def test_tng_debit_credit_inference_from_balance_movement():
    assert infer_direction(100.0, 90.0, 10.0, "Payment") == ("debit", -10.0)
    assert infer_direction(90.0, 110.0, 20.0, "Payment") == ("credit", 20.0)


def test_tng_wrapped_row_grouping():
    result = TngEwalletParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    assert len(result.transactions) == 3
    assert "Sample Bank Incoming transfer" in result.transactions[1]["raw_line"]
    assert "REF-003-B" in result.transactions[2]["raw_line"]


def test_tng_accepts_sample_ocr_status_and_rm_prefixes():
    text = (
        "1/6/2025 Success PayDirect Payment REF001 Merchant Details "
        "RM10.00 RM90.00"
    )
    result = TngEwalletParser().parse_text(text, "sample.pdf")
    assert len(result.transactions) == 1
    assert result.transactions[0]["amount"] == -10.0


def test_tng_accepts_wrapped_detail_after_ocr_amount_columns():
    text = (
        "1/6/2025 Success Payment REF001 Merchant RM10.00 RM90.00\n"
        "wrapped detail text"
    )
    result = TngEwalletParser().parse_text(text, "sample.pdf")
    assert len(result.transactions) == 1
    assert "wrapped detail text" in result.transactions[0]["details"]


def test_tng_normalizes_letter_o_inside_rm_amount_only():
    assert normalize_tng_ocr_text("Payment RMO.00 code O123") == (
        "Payment RM0.00 code O123"
    )


@pytest.mark.parametrize(
    ("raw_line", "expected_status", "expected_type", "expected_balance"),
    [
        (
            "15/8/2025 Success Payment REF001 Sample Merchant "
            "RM10.10 RM9g0.04 10000010000 TNGOW3MY1",
            "Success",
            "PAYMENT",
            90.04,
        ),
        (
            "29/8/2025 Reversed Payment REF002 Card Reload "
            "RM100.00 RM77.33 10000010000 TNGOW3MY1",
            "Reversed",
            "PAYMENT",
            77.33,
        ),
        (
            "15/10/2025 Reversed Payment REF003 Card Reload "
            "RM50.00 RM4.87 10000010000 TNGOW3MY 1 "
            "*This is a system generated email. Please do not reply.",
            "Reversed",
            "PAYMENT",
            4.87,
        ),
        (
            "15/11/2025 Success PayDirect Payment REF004 Sample Toll "
            "15/11/2025 06:50 PM RM2.00 RM85.1 1 10000010000 TNGOW3MY1",
            "Success",
            "PAYDIRECT PAYMENT",
            85.11,
        ),
        (
            "2/12/2025 Success PayDirect Payment REF005 Sample Highway "
            "01/12/2025 08:07 PM RM2.10 RM58.1 1 10000010000 TNGOW3MY1",
            "Success",
            "PAYDIRECT PAYMENT",
            58.11,
        ),
    ],
)
def test_tng_normalizes_monthly_ocr_variants(
    raw_line,
    expected_status,
    expected_type,
    expected_balance,
):
    result = TngEwalletParser().parse_text(raw_line, "sample.pdf")

    assert result.exceptions == []
    assert len(result.transactions) == 1
    assert result.transactions[0]["status"] == expected_status
    assert result.transactions[0]["transaction_type"] == expected_type
    assert result.transactions[0]["balance"] == expected_balance


def test_tng_parses_transaction_when_balance_is_unreadable():
    text = "3/12/2025 Success Payment REF006 Sample Shop RM4.50 RM??.??"

    result = TngEwalletParser().parse_text(text, "sample.pdf")

    assert result.exceptions == []
    assert len(result.transactions) == 1
    assert result.transactions[0]["amount"] == -4.5
    assert result.transactions[0]["balance"] is None


def test_tng_parses_alternate_text_table_format():
    text = """
    transaction date time transaction type transaction amount transaction direction transaction status transaction reference id
    2025-05-31 19:35:42 DUITNOW_RECEIVEFROM RM 100.00 CR SUCCESS REF001
    2025-05-31 19:34:49 PREPAID_PURCHASE RM 30.20 DR SUCCESS REF002
    """

    result = TngEwalletParser().parse_text(text, "sample.pdf")

    assert result.exceptions == []
    assert len(result.transactions) == 2
    assert result.transactions[0]["provider"] == "Touch 'n Go eWallet"
    assert result.transactions[0]["statement_type"] == "ewallet"
    assert result.transactions[0]["transaction_date"] == "2025-05-31 19:35:42"
    assert result.transactions[0]["transaction_type"] == "DUITNOW_RECEIVEFROM"
    assert result.transactions[0]["status"] == "Success"
    assert result.transactions[0]["reference"] == "REF001"
    assert result.transactions[0]["direction"] == "credit"
    assert result.transactions[0]["amount"] == 100.0
    assert result.transactions[1]["direction"] == "debit"
    assert result.transactions[1]["amount"] == -30.2
    assert result.transactions[0]["account_name_masked"] is None
    assert result.transactions[0]["account_no_masked"] is None
