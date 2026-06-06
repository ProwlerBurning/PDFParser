from pathlib import Path

from src.parsers.hong_leong import HongLeongParser


FIXTURE = Path(__file__).parent / "fixtures" / "hong_leong_sample_text.txt"


def test_hlb_regex_transaction_parsing():
    result = HongLeongParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    assert len(result.transactions) == 4
    assert result.transactions[0]["description"].startswith("WATSON'S")
    assert result.transactions[-1]["amount"] == -365.61


def test_hlb_cr_amount_handling():
    result = HongLeongParser().parse_text(FIXTURE.read_text(), "sample.pdf")
    credits = [row for row in result.transactions if row["direction"] == "credit"]
    assert [row["amount"] for row in credits] == [100.0, 17.89]
