from src.parsers.base import ParseResult, transaction_row
from src.privacy import apply_privacy, mask_card_number, mask_name, mask_wallet_id


def test_masks_card_wallet_and_name():
    assert mask_card_number("4293 1990 0861 3752") == "4293********3752"
    assert mask_wallet_id("60123456789") == "601*****789"
    assert mask_name("Example Person") == "E***** P*****"


def test_masks_long_identifiers_in_transaction_text():
    result = ParseResult(
        transactions=[
            transaction_row(
                reference="1234567890123456",
                details="Wallet 60123456789 token AB123456789012345 and 1234567890123456789012",
                raw_line="private",
            )
        ]
    )
    apply_privacy(result)
    assert result.transactions[0]["reference"] == "1234********3456"
    assert result.transactions[0]["details"] == (
        "Wallet 601*****789 token AB1234*******2345 and 1234**************9012"
    )
