# Supported Providers

The following providers are supported. Details below are documented from current
parser behavior and tests; where exact coverage is uncertain it is stated as
such rather than claimed.

## Touch 'n Go eWallet

- **Processing mode:** local OCR for monthly scanned statements; native text
  extraction for the alternate Jan 2024 – May 2025 text-table export format.
- **Known layout support:** monthly transaction rows including Reversed, Payment,
  and PayDirect Payment entries; malformed RM values, split RM balances, and
  footer-contaminated rows; the alternate text-table export.
- **Privacy notes:** names, wallet IDs, account IDs, and card numbers are masked
  by default; `--unmask` exposes source-available values for local debug only.
- **Limitations:** older alternate-format rows remain blank where the metadata is
  genuinely absent in the source (values are not inferred). Documented from
  current parser behavior and tests.

## Standard Chartered credit card

- **Processing mode:** local OCR (350 DPI primary pass, with a deterministic
  250 DPI fallback union for rows lost at 350 DPI).
- **Known layout support:** wrapped transaction rows; amount-before-reference and
  amount-after-reference layouts; comma-decimal amounts; split reference IDs;
  foreign-currency rows (RM column used as the charged amount); CR credit rows;
  multiple card sections. Targeted amount-cell OCR recovery and a multi-DPI /
  multi-PSM date-cell consensus are used to recover wrapped or invalid-date rows.
- **Privacy notes:** card sections and card numbers are masked by default.
- **Limitations:** depends on OCR quality of the source scan; rows whose amount
  or date cannot be recovered deterministically are kept as exceptions rather
  than guessed. Documented from current parser behavior and tests.

## Hong Leong Bank credit card

- **Processing mode:** native PDF text extraction.
- **Known layout support:** transaction rows including CR credits; first-page
  Statement_Summary metadata extracted via label look-ahead and positional
  data-row parsing, plus a cardholder-name heuristic.
- **Privacy notes:** `cardholder_name` and card numbers are masked by default.
- **Limitations:** metadata extraction depends on the first-page table layout;
  fields not found are left blank rather than inferred. Documented from current
  parser behavior and tests.
