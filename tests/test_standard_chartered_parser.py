from pathlib import Path

import pytest

from src.parsers.standard_chartered import StandardCharteredParser
from src.privacy import apply_privacy


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


@pytest.mark.parametrize(
    ("first_card", "second_card"),
    [
        ("4032-XXX-XXXX-8311", "4032-XXX-XXXX-9295"),
        ("4032-***-****-8311", "4032-***-****-9295"),
        ("4032 **** **** 8311", "4032 **** **** 9295"),
    ],
)
def test_sc_supports_masked_card_numbers_and_keeps_sections_distinct(
    first_card,
    second_card,
):
    text = (
        "Standard Chartered Credit Card Statement\n"
        "VISA PLATINUM\n"
        f"{first_card}\n"
        "30 Dec 29 Dec FIRST MERCHANT REF001 10.00\n"
        "VISA PLATINUM\n"
        f"{second_card}\n"
        "01 Jan 01 Jan SECOND MERCHANT REF002 20.00"
    )

    result = StandardCharteredParser().parse_text(text, "sample.pdf")
    apply_privacy(result)

    assert [row["card_no_masked"] for row in result.transactions] == [
        "4032********8311",
        "4032********9295",
    ]
