# Local Statement Extractor Design

## Scope

Build a deterministic local Python 3.11+ command-line tool supporting only:

- Touch 'n Go eWallet transaction history
- Standard Chartered credit card statements
- Hong Leong Bank credit card statements

The tool makes no network or LLM calls during extraction.

## Architecture

The CLI expands a file or folder input into PDFs. Each PDF is hashed, checked
for useful native text, and classified using native text or cached OCR. Hong
Leong uses native text unless it is unavailable; Touch 'n Go and Standard
Chartered use PyMuPDF-rendered page images and Tesseract word coordinates.

Each provider parser consumes page artifacts and returns normalized
transactions, statement summary data, raw extraction rows, and exceptions.
Privacy masking is applied by default before workbook export. Validation
creates exception records instead of terminating the batch.

## Data And Cache

Cache entries live under `cache/<sha256>/` and include native page text,
OCR line text, OCR word coordinates, and extraction metadata. `--force`
invalidates reuse for the current run. Logs contain filenames, provider names,
counts, and processing modes, but no extracted identity or account values.

## Output

One `.xlsx` workbook contains:

- `Transactions`
- `Statement_Summary`
- `Exceptions`
- `Raw_Extract`

Formatting uses openpyxl with frozen headers, filters, sensible widths, and RM
number formats. The command exits nonzero for inaccessible inputs or complete
batch failure, while per-file/parser issues are preserved in Exceptions.

## Testing

Unit tests use synthetic text fixtures for transaction parsing, card-section
state, balance inference, CR handling, and privacy masking. Integration
verification runs the three private local PDFs and reports only masked counts
and processing modes.
