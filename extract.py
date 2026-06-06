#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.export_excel import export_workbook
from src.logging_utils import configure_logging
from src.ocr_engine import OcrUnavailableError, ocr_pdf_pages
from src.parsers.base import ParseResult, add_exception
from src.parsers.hong_leong import HongLeongParser
from src.parsers.standard_chartered import StandardCharteredParser
from src.parsers.tng_ewallet import TngEwalletParser
from src.pdf_detect import detect_statement_type, processing_mode_for
from src.privacy import apply_privacy
from src.text_extract import extract_native_pages, has_useful_text
from src.validate import validate_standard_chartered


PARSERS = {
    "tng": TngEwalletParser,
    "sc": StandardCharteredParser,
    "hlb": HongLeongParser,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract supported Malaysian PDF statements to Excel.")
    parser.add_argument("--input", required=True, type=Path, help="A PDF file or folder containing PDFs.")
    parser.add_argument("--output", required=True, type=Path, help="Output .xlsx file.")
    parser.add_argument("--type", choices=sorted(PARSERS), help="Manual statement type override.")
    parser.add_argument("--force", action="store_true", help="Ignore cached text/OCR artifacts.")
    parser.add_argument("--unmask", action="store_true", help="Include private values for local private use.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def collect_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    if input_path.is_dir():
        return sorted(path for path in input_path.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")
    raise FileNotFoundError(f"Input is not a PDF or directory: {input_path}")


def _join_native_pages(pages: list[str]) -> str:
    return "\n".join(pages)


def _join_ocr_pages(pages: list[dict]) -> str:
    return "\n".join(page["text"] for page in pages)


def process_pdf(
    pdf_path: Path,
    cache_root: Path,
    type_override: str | None,
    force: bool,
    unmask: bool,
    logger,
) -> ParseResult:
    native_pages, native_cached = extract_native_pages(pdf_path, cache_root, force)
    useful_text = has_useful_text(native_pages)
    native_text = _join_native_pages(native_pages)
    statement_type = type_override or detect_statement_type(native_text)
    detection_used_ocr = False
    if statement_type is None:
        first_page, _ = ocr_pdf_pages(pdf_path, cache_root, force, first_page_only=True)
        statement_type = detect_statement_type(_join_ocr_pages(first_page))
        detection_used_ocr = True
    if statement_type not in PARSERS:
        result = ParseResult()
        add_exception(result, pdf_path.name, "Unknown", "Unsupported or undetected statement type")
        result.summaries.append(
            {
                "source_file": pdf_path.name,
                "provider": "Unknown",
                "statement_type": "unknown",
                "processing_mode": "undetected",
                "transaction_count": 0,
            }
        )
        return apply_privacy(result, unmask)

    mode = processing_mode_for(statement_type, useful_text)
    parser = PARSERS[statement_type]()
    if mode == "text":
        extraction_text = native_text
        cache_hit = native_cached
    else:
        ocr_pages, cache_hit = ocr_pdf_pages(pdf_path, cache_root, force)
        extraction_text = _join_ocr_pages(ocr_pages)
    result = parser.parse_text(extraction_text, pdf_path.name)
    result.processing_mode = mode
    for summary in result.summaries:
        summary["processing_mode"] = mode
        summary["cache_hit"] = cache_hit
        summary["detection_used_ocr"] = detection_used_ocr
    if statement_type == "sc":
        validate_standard_chartered(result)
    logger.info(
        "Processed %s as %s via %s: %d transactions, %d exceptions%s",
        pdf_path.name,
        statement_type,
        mode,
        len(result.transactions),
        len(result.exceptions),
        " (cache)" if cache_hit else "",
    )
    return apply_privacy(result, unmask)


def main() -> int:
    args = parse_args()
    logger = configure_logging(args.verbose)
    project_root = Path(__file__).resolve().parent
    cache_root = project_root / "cache"
    try:
        pdfs = collect_pdfs(args.input.expanduser().resolve())
    except (FileNotFoundError, PermissionError) as error:
        logger.error("%s", error)
        return 2
    if not pdfs:
        logger.error("No PDF files found in %s", args.input)
        return 2

    transactions = []
    summaries = []
    exceptions = []
    raw_extract = []
    for pdf_path in pdfs:
        try:
            result = process_pdf(
                pdf_path,
                cache_root,
                args.type,
                args.force,
                args.unmask,
                logger,
            )
        except (OcrUnavailableError, RuntimeError, ValueError, OSError) as error:
            logger.error("Failed to process %s: %s", pdf_path.name, type(error).__name__)
            result = ParseResult()
            add_exception(result, pdf_path.name, "Unknown", f"Processing failed: {type(error).__name__}")
            result.summaries.append(
                {
                    "source_file": pdf_path.name,
                    "provider": "Unknown",
                    "statement_type": "unknown",
                    "processing_mode": "failed",
                    "transaction_count": 0,
                }
            )
        transactions.extend(result.transactions)
        summaries.extend(result.summaries)
        exceptions.extend(result.exceptions)
        raw_extract.extend(result.raw_extract)

    export_workbook(args.output.expanduser().resolve(), transactions, summaries, exceptions, raw_extract)
    logger.info("Wrote workbook %s", args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
