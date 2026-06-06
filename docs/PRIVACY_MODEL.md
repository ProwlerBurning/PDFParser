# Privacy Model

This project is designed to keep financial data on your own machine.

## Local-first design
- All normal extraction runs locally using pdfplumber, PyMuPDF, and local
  Tesseract OCR.
- **No cloud parsing by default.**
- **No online API calls** in the normal parser flow.
- **No LLM fallback** in the normal parser flow.
- Normal extraction is deterministic.

## Masked output
- **Masked output is the default.** Names, wallet IDs, and card numbers are
  masked; card numbers retain only the first and last four digits, wallet IDs the
  first and last three.
- **`--unmask` is a local debug mode only**, intended for private use on your own
  machine when full source-available values are required.
- **Raw lines are suppressed in masked workbooks** because they may contain names
  or addresses.
- Values already masked or absent in the source cannot be reconstructed.

## Cache behavior
- Extraction caches native text and OCR results under `cache/`, keyed by the PDF
  SHA-256 (OCR cache files are also keyed by DPI so different resolutions do not
  clobber each other).
- Cache files are **not** committed to the repository.

## Private verifier
- `scripts/verify_private_samples.py` accepts explicit PDF paths and writes its
  OCR cache and workbook **inside a temporary directory only** — nothing
  permanent is written and nothing is uploaded.

## Parser Builder Mode
- Optional and **review-only**. It produces sanitized prompts and metadata as
  review artifacts; it is only contacted when explicitly requested via
  `--parser-build openrouter`, does not run during normal extraction, and does
  not auto-install generated parser code.

## Your responsibility
- **No real financial statements should be committed, attached to issues or pull
  requests, or shared publicly.** Use synthetic or fully redacted data only.
