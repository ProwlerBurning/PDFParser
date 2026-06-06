# Statement Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local deterministic extractor that converts the three specified statement formats into one audited Excel workbook.

**Architecture:** Use native PDF text first, provider-specific OCR fallback with cached PyMuPDF/Tesseract artifacts, focused parsers returning a shared result model, privacy masking before export, and validation represented as exception rows. Keep provider recognition and parsing profile-driven where layout constants or phrases are likely to change.

**Tech Stack:** Python 3.11+, pdfplumber, PyMuPDF, pytesseract, Pillow, pandas, openpyxl, PyYAML, pytest

---

### Task 1: Environment And Parser Contracts

**Files:**
- Create: `requirements.txt`
- Create: `tests/fixtures/*.txt`
- Create: `tests/test_*.py`

- [ ] Write parser and privacy tests from synthetic fixtures.
- [ ] Create `.venv` and install dependencies.
- [ ] Run pytest and verify collection fails because implementation modules do not exist.

### Task 2: Core Models And Provider Parsers

**Files:**
- Create: `src/parsers/base.py`
- Create: `src/parsers/tng_ewallet.py`
- Create: `src/parsers/standard_chartered.py`
- Create: `src/parsers/hong_leong.py`
- Create: `src/privacy.py`
- Create: `src/normalize.py`
- Create: `src/validate.py`

- [ ] Implement shared result/transaction contracts.
- [ ] Implement HLB regex parsing and CR semantics.
- [ ] Implement TNG row grouping and balance direction inference.
- [ ] Implement Standard Chartered section state and CR semantics.
- [ ] Run focused tests after each parser, then the full suite.

### Task 3: PDF/OCR Pipeline And Cache

**Files:**
- Create: `src/text_extract.py`
- Create: `src/ocr_engine.py`
- Create: `src/pdf_detect.py`
- Create: `profiles/*.yml`

- [ ] Implement native text extraction and useful-text detection.
- [ ] Implement Tesseract discovery through `TESSERACT_CMD` or `shutil.which`.
- [ ] Render with PyMuPDF and cache OCR text/coordinates by SHA-256.
- [ ] Implement deterministic provider detection and provider mode selection.
- [ ] Add tests for processing mode decisions.

### Task 4: CLI And Excel Export

**Files:**
- Create: `extract.py`
- Create: `src/export_excel.py`
- Create: `src/logging_utils.py`

- [ ] Implement folder/file inputs, override type, `--force`, and `--unmask`.
- [ ] Aggregate parser results without stopping on individual PDF failures.
- [ ] Export all four required sheets with formatting.
- [ ] Test workbook sheet contract and masking boundary.

### Task 5: Documentation And Private Integration Verification

**Files:**
- Create: `README.md`

- [ ] Document installation, Homebrew Tesseract, CLI use, exceptions, masking, and profiles.
- [ ] Run full pytest.
- [ ] Run extraction over the three local PDFs.
- [ ] Verify workbook sheets and report provider/exception counts and OCR modes without private values.
