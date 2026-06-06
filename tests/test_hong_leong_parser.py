from pathlib import Path

from src.parsers.hong_leong import HongLeongParser
from src.privacy import apply_privacy


FIXTURE = Path(__file__).parent / "fixtures" / "hong_leong_sample_text.txt"
TABLE_FIXTURE = Path(__file__).parent / "fixtures" / "hong_leong_table_sample_text.txt"


def _table_summary(unmask: bool = True):
    result = HongLeongParser().parse_text(TABLE_FIXTURE.read_text(), "sample.pdf")
    apply_privacy(result, unmask=unmask)
    return result.summaries[0]


def test_hlb_regex_transaction_parsing():
    result = HongLeongParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    assert len(result.transactions) == 4
    assert result.transactions[0]["description"].startswith("WATSON'S")
    assert result.transactions[-1]["amount"] == -365.61


def test_hlb_cr_amount_handling():
    result = HongLeongParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    credits = [row for row in result.transactions if row["direction"] == "credit"]
    assert [row["amount"] for row in credits] == [100.0, 17.89]


def test_hlb_table_layout_metadata_extraction():
    summary = _table_summary(unmask=True)
    assert summary["statement_date"] == "14 DEC 2025"
    assert summary["payment_due_date"] == "03 JAN 2026"
    assert summary["combined_credit_limit"] == 30000.00
    assert summary["current_balance"] == 29949.91
    assert summary["minimum_payment"] == 1497.50
    assert summary["cardholder_name"] == "TEST CARDHOLDER NAME"
    assert summary["card_type"] == "ESSENTIAL VISA CLASSIC"
    assert summary["previous_balance"] == 28000.00
    assert summary["total_balance"] == 29949.91


def test_hlb_table_layout_card_number_unmasked_then_masked():
    unmasked = _table_summary(unmask=True)
    assert unmasked["card_no_masked"] == "4000123456789010"
    masked = _table_summary(unmask=False)
    assert masked["card_no_masked"] == "4000********9010"
    assert masked["cardholder_name"] == "T***** C***** N*****"
