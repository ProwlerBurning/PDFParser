from pathlib import Path

from src.parsers.tng_ewallet import TngEwalletParser, infer_direction


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
