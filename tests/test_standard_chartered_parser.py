from pathlib import Path

import pytest

from src.parsers.base import transaction_row
from src.parsers.standard_chartered import StandardCharteredParser, select_sc_fallback_rows
from src.privacy import apply_privacy


def _fb_row(source="SC statement 2025012 Dec.pdf", card="4032********8311",
            post="24 Dec", txn="24 Dec", ref="74107625358045204439271",
            amount=42.51, direction="credit", description="SHEIN.COM SINGAPORESG",
            amount_raw="42.51", raw_line="24 Dec 24 Dec SHEIN.COM Txn Ref: 42.51CR"):
    return transaction_row(
        source_file=source, provider="Standard Chartered", statement_type="credit_card",
        card_no_masked=card, posting_date=post, transaction_date=txn, reference=ref,
        amount=amount, direction=direction, description=description,
        amount_raw=amount_raw, currency="MYR", raw_line=raw_line,
    )


def test_fallback_recovers_row_dropped_by_350_and_keeps_cr_direction():
    primary = [
        _fb_row(ref="74107625358044213435487", amount=25.01, raw_line="24 Dec 24 Dec SHEIN.COM Txn Ref: 25.01CR"),
        _fb_row(ref="74107625358045209439359", amount=38.31, raw_line="24 Dec 24 Dec SHEIN.COM Txn Ref: 38.31CR"),
    ]
    added = select_sc_fallback_rows(primary, [_fb_row()])
    assert len(added) == 1
    assert added[0]["amount"] == 42.51 and added[0]["direction"] == "credit"


def test_fallback_does_not_duplicate_existing_350_row():
    assert select_sc_fallback_rows([_fb_row()], [_fb_row()]) == []


def test_fallback_rejects_invalid_dates():
    cand = [_fb_row(txn="41 Dec", amount=99.99, ref="11111111111111111111111")]
    assert select_sc_fallback_rows([], cand) == []


def test_fallback_rejects_non_transaction_rows():
    cand = [_fb_row(description="PREVIOUS BALANCE FROM LAST STATEMENT", amount=900.0,
                    ref="22222222222222222222222")]
    assert select_sc_fallback_rows([], cand) == []


def test_fallback_rejects_benign_churn_amount_already_at_350():
    primary = [_fb_row(ref="99999999999999999999999", amount=42.51)]
    cand = [_fb_row(ref="74107625358045204439271", amount=42.51)]
    assert select_sc_fallback_rows(primary, cand) == []


def test_fallback_rejects_reference_already_present_at_350():
    primary = [_fb_row(ref="24921385349001023418600", amount=-334.40, direction="debit",
                       description="ALLIANZ L 010414800 KUALA LUMPUMY JAYA GROCER")]
    cand = [_fb_row(ref="24921385349001023418600", amount=-333.35, direction="debit",
                    description="ALLIANZ L 010414800", amount_raw="333.35",
                    raw_line="16 Dec 15 Dec ALLIANZ L 010414800 Txn Ref: 333.35")]
    assert select_sc_fallback_rows(primary, cand) == []


def test_fallback_rejects_rate_phantom_where_amount_is_a_percentage():
    cand = [_fb_row(description="FOB+ 9.88% EFF 17.09%", amount=-17.09, direction="debit",
                    amount_raw="17.09", ref="3010078711160",
                    raw_line="28 Oct 28 Oct FOB+ 9.88% EFF 17.09% Txn Ref:30100787111")]
    assert select_sc_fallback_rows([], cand) == []


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


def _single(text: str):
    body = "Standard Chartered Credit Card Statement\nVISA PLATINUM\n" + text
    result = StandardCharteredParser().parse_text(body, "sample.pdf")
    return result


def test_sc_amount_before_reference_recovers_amount():
    # Wrapped OCR row: amount sits before the appended location + reference id.
    result = _single(
        "07 Oct 06 Oct GRAB RIDES-EC Txn Ref: 5.00 PETALING JAMY 24506185279027397641718"
    )
    assert result.exceptions == []
    assert len(result.transactions) == 1
    row = result.transactions[0]
    assert row["amount"] == -5.0
    assert row["direction"] == "debit"
    assert row["reference"] == "24506185279027397641718"
    assert "GRAB RIDES-EC" in row["description"]
    assert "PETALING JAMY" in row["description"]


def test_sc_comma_decimal_amount_is_normalized():
    result = _single(
        "28 Oct 27 Oct LAZADA KUALA LUMPUMY | Txn Ref: 54,52 74413785301000101886156"
    )
    assert result.exceptions == []
    row = result.transactions[0]
    assert row["amount"] == -54.52
    assert row["reference"] == "74413785301000101886156"


def test_sc_amount_after_reference_credit_with_cr_suffix():
    result = _single(
        "06 Oct 06 Oct DUITNOW PAY-TO- Txn Ref:202510060247034 1,000.00CR"
    )
    assert result.exceptions == []
    row = result.transactions[0]
    assert row["amount"] == 1000.0
    assert row["direction"] == "credit"
    assert row["reference"] == "202510060247034"


def test_sc_split_reference_id_is_joined_when_amount_present():
    result = _single(
        "30 Jun 28 Jun Q HOUSE - TAIPAN Txn Ref: SUBANG JAYAMY 24553585 179280603677604 31.50"
    )
    assert result.exceptions == []
    row = result.transactions[0]
    assert row["amount"] == -31.5
    assert row["reference"] == "24553585179280603677604"


def test_sc_foreign_currency_row_uses_rm_amount():
    result = _single(
        "02 Jan 02 Jan FOREIGN SHOP REF003 USD 25.00 100.50"
    )
    assert result.exceptions == []
    row = result.transactions[0]
    assert row["amount"] == -100.50  # RM column, not the 25.00 foreign amount


def test_sc_row_without_recoverable_amount_stays_exception():
    result = _single(
        "07 Oct 06 Oct GRAB RIDES-EC Txn Ref: PETALING JAMY 24506185279027397641718"
    )
    assert len(result.transactions) == 0
    assert any("Unparsed" in exc["reason"] for exc in result.exceptions)


def test_sc_valid_dates_are_accepted():
    result = _single(
        "11 Mar 10 Mar JAYA GROCER-THE MAI Txn Ref: 24506185069027777095224 26.40"
    )
    assert result.exceptions == []
    assert result.transactions[0]["posting_date"] == "11 Mar"
    assert result.transactions[0]["transaction_date"] == "10 Mar"


def test_sc_invalid_transaction_day_is_rejected_with_clear_reason():
    # 41 Mar is shape-valid (DD Mon) but semantically invalid; it must not parse.
    result = _single(
        "11 Mar 41 Mar DUITNOW PAY-TO-ACCOUNT Txn Ref: 2025031101561108311809 500.00CR"
    )
    assert len(result.transactions) == 0
    assert any(
        exc["reason"] == "Unrecoverable SC transaction row: invalid OCR transaction date"
        for exc in result.exceptions
    )


def test_sc_invalid_date_does_not_pass_on_shape_alone():
    # Day 00 and a bogus month both match the DD Mon shape but are invalid.
    for bad in ("11 Mar 00 Mar MERCH Txn Ref: 24506185069027777095224 12.00",
                "11 Mar 10 Zzz MERCH Txn Ref: 24506185069027777095224 12.00"):
        result = _single(bad)
        assert len(result.transactions) == 0
        assert any("invalid OCR transaction date" in exc["reason"] for exc in result.exceptions)
