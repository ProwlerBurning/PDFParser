from src.redaction import redaction_scan, sanitize_statement_text


PRIVATE_TEXT = """
Registered Name: Example Person
Address: 12 Example Road, Kuala Lumpur
Email: person@example.com
Phone: +60 12-345 6789
Card: 4293 1990 0861 3752
Masked Card: 4032-XXX-XXXX-8311
Wallet ID: 60123456789
Account No: 123456789012
Reference: 987654321012345
"""


def test_sanitize_statement_text_redacts_supported_sensitive_values():
    sanitized = sanitize_statement_text(PRIVATE_TEXT)

    assert "Example Person" not in sanitized
    assert "Example Road" not in sanitized
    assert "person@example.com" not in sanitized
    assert "345 6789" not in sanitized
    assert "4293 1990 0861 3752" not in sanitized
    assert "4032-XXX-XXXX-8311" not in sanitized
    assert "60123456789" not in sanitized
    assert "123456789012" not in sanitized
    assert "987654321012345" not in sanitized
    assert redaction_scan(sanitized).passed


def test_redaction_scan_reports_categories_without_exposing_values():
    scan = redaction_scan("Email person@example.com account 123456789012")

    assert not scan.passed
    assert set(scan.categories) == {"email", "long_identifier"}
    assert "person@example.com" not in repr(scan)
    assert "123456789012" not in repr(scan)
