# Statement Extractor

Local, deterministic PDF-to-Excel extraction for three statement formats:

- Touch 'n Go eWallet Transaction History
- Standard Chartered credit card statement
- Hong Leong Bank credit card statement

No LLM, cloud OCR, or online AI service is used. Extraction uses pdfplumber,
PyMuPDF, and local Tesseract OCR.

## Installation

Requires macOS and Python 3.11 or newer.

```bash
cd /Users/benjaminlimoonchye/codex/StatementParser
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Install Tesseract with Homebrew:

```bash
brew install tesseract
```

The extractor uses `TESSERACT_CMD` when set, otherwise
`shutil.which("tesseract")`. It does not hardcode a Homebrew path.

## Run

Extract every PDF in one folder:

```bash
.venv/bin/python extract.py --input "/path/to/input_folder" --output "output/statements.xlsx"
```

Extract one PDF:

```bash
.venv/bin/python extract.py --input "/path/to/file.pdf" --output "output/statement.xlsx"
```

Force a statement type:

```bash
.venv/bin/python extract.py --input "file.pdf" --type tng --output "output.xlsx"
.venv/bin/python extract.py --input "file.pdf" --type sc --output "output.xlsx"
.venv/bin/python extract.py --input "file.pdf" --type hlb --output "output.xlsx"
```

Use `--force` to discard cached extraction artifacts. Cache data is stored by
PDF SHA-256 under `cache/`.

## Review Exceptions

Open the `Exceptions` worksheet after every run. It contains unsupported
documents, uncertain transaction direction, unparsed candidate rows, and
balance-validation mismatches. One bad document does not stop a folder run.

## Privacy

Names, wallet IDs, and card numbers are masked by default. Card numbers retain
the first and last four digits; wallet IDs retain the first and last three.
Raw lines are suppressed in masked workbooks because they may contain names or
addresses. Use `--unmask` only on a private local machine when full audit text
is required. Logs never include extracted identity or account values.

## Add A Future Bank

1. Add detection phrases and layout constants under `profiles/`.
2. Add a parser implementing the `ParseResult` contract in `src/parsers/`.
3. Register its short type in `extract.py`.
4. Add synthetic text fixtures and parser tests.
5. Add provider-specific reconciliation rules in `src/validate.py`.

Profiles are configuration, while row grouping and reconciliation remain
explicit Python so parsing behavior is reviewable and testable.

## Tests

```bash
.venv/bin/pytest
```
