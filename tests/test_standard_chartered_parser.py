from pathlib import Path

from src.parsers.standard_chartered import StandardCharteredParser


FIXTURE = Path(__file__).parent / "fixtures" / "sc_sample_ocr_text.txt"


def test_sc_cr_amount_handling():
    result = StandardCharteredParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    payment = next(row for row in result.transactions if "PAYMENT RECEIVED" in row["description"])
    assert payment["amount"] == 100.0
    assert payment["direction"] == "credit"


def test_sc_multi_card_section_reset():
    result = StandardCharteredParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    assert len(result.transactions) == 3
    assert result.transactions[0]["card_type"] == "VISA PLATINUM"
    assert result.transactions[-1]["card_type"] == "VISA REWARDS PLATINUM"
    assert result.transactions[0]["card_no_masked"] != result.transactions[-1]["card_no_masked"]


def test_sc_accepts_wrapped_text_after_ocr_amount_column():
    text = (
        "Standard Chartered Credit Card Statement\n"
        "VISA PLATINUM\n"
        "30 Dec 29 Dec SAMPLE MERCHANT REF001 10.00\n"
        "wrapped description"
    )
    result = StandardCharteredParser().parse_text(text, "sample.pdf")
    assert len(result.transactions) == 1
    assert "wrapped description" in result.transactions[0]["description"]
