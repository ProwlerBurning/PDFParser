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
PDF SHA-256 under `cache/`.

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

When the three private samples are present in `~/Downloads`, run the local
integration verifier:

```bash
.venv/bin/python scripts/verify_private_samples.py
```

It creates its workbook in a temporary directory and prints only provider
counts, exception counts, processing modes, and the masked-output privacy scan
result.
