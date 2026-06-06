# Contributing

Thanks for your interest in improving this project. It is a privacy-first, local,
deterministic PDF-to-Excel parser for Malaysian bank and e-wallet statements.
Please read this guide before opening an issue or pull request.

## Local setup

- Python **3.11+**.
- Install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract). On macOS:
  `brew install tesseract`. On Debian/Ubuntu: `sudo apt-get install tesseract-ocr`.
  If Tesseract is not on your `PATH`, set the `TESSERACT_CMD` environment variable.
- Create a virtual environment and install dependencies:

  ```bash
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
  ```

## Running checks

Compile everything and run the test suite before opening a PR:

```bash
.venv/bin/python -m compileall extract.py src tests scripts
.venv/bin/python -m pytest
```

To verify your own **private local** samples without committing them, pass the
PDF paths explicitly as positional arguments (the helper never reads hardcoded
locations):

```bash
.venv/bin/python scripts/verify_private_samples.py \
  "/path/to/tng_statement.pdf" \
  "/path/to/sc_statement.pdf" \
  "/path/to/hlb_statement.pdf"
```

It writes its OCR cache and workbook inside a temporary directory only, uploads
nothing, and prints provider counts, exception counts, processing modes, and the
masked-output privacy scan result.

## Privacy and safety rules (non-negotiable)

- **Never commit** real bank statements, e-wallet statements, Excel outputs,
  cache files, `input_pdfs/`, `output/` contents, `review_bundle/`, or any
  personal transaction data.
- **Tests must use synthetic fixtures only** — no real or lightly-edited
  statements.
- **Normal extraction must remain local and deterministic.**
- **No online API calls and no LLM fallback may be added to the normal parser
  flow.**

## Proposing a new provider

1. Do **not** attach real statements. Describe the layout with **redacted notes**
   (field positions, column order, date/amount formats) and provide a
   **synthetic fixture** that mimics the structure with fake data.
2. Add detection phrases and layout constants under `profiles/`.
3. Add a parser implementing the `ParseResult` contract in `src/parsers/`.
4. Add synthetic text fixtures and parser tests.
5. Add provider-specific reconciliation rules in `src/validate.py` if applicable.

## Parser Builder Mode

Parser Builder Mode is **optional and review-only**. It produces sanitized
development packets for designing a new deterministic parser. It does **not** run
during normal extraction, is only contacted when explicitly requested via
`--parser-build openrouter`, and **must not auto-install generated parser code** —
any generated parser must be reviewed and tested locally before use.
