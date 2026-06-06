# Statement Extractor

Local, deterministic PDF-to-Excel extraction for three statement formats:

- Touch 'n Go eWallet Transaction History
- Standard Chartered credit card statement
- Hong Leong Bank credit card statement

Normal extraction uses no LLM, cloud OCR, or online AI service. Extraction
uses pdfplumber, PyMuPDF, and local Tesseract OCR.

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
PDF SHA-256 under `cache/`. OCR cache files are keyed by DPI, so different
resolutions never overwrite each other.

## Provider Notes

- **Touch 'n Go**: monthly scans are read via local OCR; the alternate
  Jan 2024–May 2025 export is read via native text.
- **Standard Chartered**: scanned statements are OCR'd at a higher resolution
  so the rightmost RM Amount column is captured on wrapped rows. Amounts may
  appear before or after the reference id, may use a comma decimal
  (`54,52`), and reference ids split across spaces are rejoined. A small number
  of rows whose amount cell is genuinely unreadable in the source scan are kept
  in `Exceptions` rather than guessed.
- **Hong Leong Bank**: first-page summary metadata is laid out as a column
  table, so statement date, payment due date, combined credit limit, card
  number, card type, current balance, and minimum payment are read from their
  labels and the positional data row; previous and total balances come from the
  transaction pages. Missing fields are left blank, never inferred.

## Optional Parser Builder

Parser Builder Mode can create a reviewable development packet for an unknown
statement format. It does not extract transactions, write Excel rows, or
install generated parser code. Native text extraction and OCR happen locally,
and only sanitized text is included in the prompt.

Dry-run creates the sanitized prompt and metadata without calling OpenRouter or
requiring an API key:

```bash
.venv/bin/python extract.py \
  --input "/path/to/unknown.pdf" \
  --parser-build-dry-run
```

Review the prompt under `output/parser_build/`. To request an OpenRouter
development packet:

```bash
export OPENROUTER_API_KEY="your-private-key"
.venv/bin/python extract.py \
  --input "/path/to/unknown.pdf" \
  --parser-build openrouter
```

Options:

- `--parser-build-model MODEL` selects the OpenRouter model. The default can
  also be configured with `OPENROUTER_PARSER_BUILD_MODEL`.
- `--parser-build-max-pages 5` limits the sanitized statement pages included.
- `--parser-build-output output/parser_build` changes the artifact directory.
- `--force` allows existing prompt, metadata, response, and index artifacts to
  be overwritten.
- `--force-parser-build` permits review artifacts for an already-supported
  format. Without it, supported formats fail clearly.

Parser Builder Mode currently calls OpenRouter's chat completions endpoint
using `OPENROUTER_API_KEY`. OpenRouter is contacted only by
`--parser-build openrouter`. The key is never written to artifacts, logs,
workbooks, caches, or exceptions. The original PDF is never uploaded.

For folder input, Parser Builder writes one prompt and metadata file per PDF,
plus `index.json`. Real mode also writes one `.llm_response.md` file per PDF.
All output is review-only; no files are written into `src/parsers/`.

## Review Exceptions

Open the `Exceptions` worksheet after every run. It contains unsupported
documents, uncertain transaction direction, unparsed candidate rows, and
balance-validation mismatches. One bad document does not stop a folder run.

## Privacy

Names, wallet IDs, and card numbers are masked by default. Card numbers retain
the first and last four digits; wallet IDs retain the first and last three.
Raw lines are suppressed in masked workbooks because they may contain names or
addresses. Use `--unmask` only on a private local machine when all
source-available private values and full audit text are required. The existing
`*_masked` column names are retained for workbook compatibility, but contain
source values in unmasked mode. Values already masked or absent in the source
cannot be reconstructed. Logs never include extracted identity or account
values.

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

To verify private local samples without committing them, pass the PDF paths
explicitly as positional arguments:

```bash
.venv/bin/python scripts/verify_private_samples.py \
  "/path/to/tng_statement.pdf" \
  "/path/to/sc_statement.pdf" \
  "/path/to/hlb_statement.pdf"
```

Run with no arguments to print usage. The helper writes both its OCR cache and
its workbook inside a temporary directory only (nothing permanent is written and
nothing is uploaded), and prints provider counts, exception counts, processing
modes, and the masked-output privacy scan result.

## Project governance and safety

This project is privacy-first and local by default. See:

- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, checks, and contribution rules.
- [SECURITY.md](SECURITY.md) — security reporting and what never to attach.
- [SUPPORT.md](SUPPORT.md) — how to get help (synthetic/redacted data only).
- [docs/PRIVACY_MODEL.md](docs/PRIVACY_MODEL.md) — local-first, masked-by-default design.
- [docs/SUPPORTED_PROVIDERS.md](docs/SUPPORTED_PROVIDERS.md) — supported statement formats.
- [docs/ROADMAP.md](docs/ROADMAP.md) — direction and explicit non-goals.
