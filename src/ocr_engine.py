from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import fitz
import pytesseract
from PIL import Image
from pytesseract import Output

from src.text_extract import cache_directory


DEFAULT_OCR_DPI = 250

# Amount-column recovery (Standard Chartered). A transaction date row whose RM
# amount was dropped by the full-page OCR pass is re-OCR'd from just the amount
# cell. Matching uses the same case-insensitive date prefix the parser uses.
_SC_DATE_PREFIX_RE = re.compile(r"^\d{1,2}\s+[A-Z]{3}\s+\d{1,2}\s+[A-Z]{3}\b", re.I)
_SC_DATE_PREFIX_SUB_RE = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{1,2}\s+[A-Za-z]{3}\s+")
# Tolerates the missing space tesseract often emits on a tight crop ("11Mar").
_DATE_TOKEN_RE = re.compile(r"(\d{1,2})\s*([A-Za-z]{3})")
_MONTHS = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}
_AMOUNT_WORD_RE = re.compile(r"^\(?\d[\d,]*\.\d{2}\)?$")
_AMOUNT_IN_TEXT_RE = re.compile(r"\d[\d,]*\.\d{2}")
_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*\.\d{2}(?:\s*CR)?", re.I)


def _valid_sc_date(day: str, month: str) -> bool:
    return 1 <= int(day) <= 31 and month.upper() in _MONTHS


# Acceptance thresholds for the invalid-date recovery consensus.
_DATE_MIN_ANCHORED_READS = 8
_DATE_MIN_DPI_SUPPORT = 3
_DATE_MIN_PSM_SUPPORT = 2
_DATE_MIN_WINNER_RATIO = 0.75


def _consensus_transaction_date(
    reads: list[tuple[int, int, str]],
    posting: tuple[str, str],
) -> tuple[int, str] | None:
    """Pick a transaction date from a DPI x PSM matrix of date-cell reads.

    Each read is ``(dpi, psm, text)``. A read counts only if it yields exactly
    two valid dates and its posting date matches the row's existing valid
    posting date (anchor). The winning transaction date must clear every gate:
    enough anchored reads, a strong majority share, and support across multiple
    DPIs and PSMs, with the runner-up not close. Returns ``(day, MONTH)`` or
    ``None`` when the evidence is not deterministic.
    """
    anchored: list[tuple[int, int, tuple[int, str]]] = []
    for dpi, psm, text in reads:
        dates = [
            (day, month)
            for day, month in _DATE_TOKEN_RE.findall(text or "")
            if _valid_sc_date(day, month)
        ]
        if len(dates) != 2:
            continue
        if int(dates[0][0]) != int(posting[0]) or dates[0][1].upper() != posting[1].upper():
            continue
        anchored.append((dpi, psm, (int(dates[1][0]), dates[1][1].upper())))

    if len(anchored) < _DATE_MIN_ANCHORED_READS:
        return None
    tally = Counter(item[2] for item in anchored)
    ranked = tally.most_common()
    winner, winner_count = ranked[0]
    runner_up_count = ranked[1][1] if len(ranked) > 1 else 0
    if winner_count / len(anchored) < _DATE_MIN_WINNER_RATIO:
        return None
    if runner_up_count * 2 > winner_count:  # top two too close
        return None
    dpis = {item[0] for item in anchored if item[2] == winner}
    psms = {item[1] for item in anchored if item[2] == winner}
    if len(dpis) < _DATE_MIN_DPI_SUPPORT or len(psms) < _DATE_MIN_PSM_SUPPORT:
        return None
    return winner


def recover_transaction_dates(
    pages: list[dict[str, Any]],
    date_region_ocr: Callable[[int, tuple[int, int, int, int]], list[tuple[int, int, str]]],
    pad: int = 8,
) -> int:
    """Re-OCR the left date cells for rows whose date is shape-valid but invalid.

    A row like ``11 Mar 41 Mar ...`` matches the DD-Mon shape but "41" is not a
    real day. The two date cells (the first four words) are re-OCR'd across a
    DPI x PSM matrix via ``date_region_ocr``; the transaction date is rewritten
    only on a clear, anchored, multi-setting consensus (see
    :func:`_consensus_transaction_date`). Otherwise the row is left unchanged and
    the parser flags it as an invalid-date exception. Returns rows recovered.
    """
    recovered = 0
    for page in pages:
        changed = False
        for line in page["lines"]:
            text = line.get("text", "")
            if not _SC_DATE_PREFIX_RE.match(text):
                continue
            tokens = _DATE_TOKEN_RE.findall(text)
            if len(tokens) < 2:
                continue
            posting, transaction = tokens[0], tokens[1]
            if _valid_sc_date(*posting) and _valid_sc_date(*transaction):
                continue
            if not _valid_sc_date(*posting):
                continue  # need a valid posting date to anchor the recovery
            words = line.get("words", [])
            if len(words) < 5:
                continue  # cannot bound the date cells without the description start
            description_left = words[4]["left"]
            box = (
                max(0, line["left"] - pad),
                max(0, line["top"] - pad),
                description_left - pad,
                line["bottom"] + pad,
            )
            winner = _consensus_transaction_date(date_region_ocr(page["page_no"], box), posting)
            if winner is None:
                continue
            new_posting = f"{int(posting[0]):02d} {posting[1].title()}"
            new_transaction = f"{winner[0]:02d} {winner[1].title()}"
            line["text"] = _SC_DATE_PREFIX_SUB_RE.sub(
                f"{new_posting} {new_transaction} ", text, count=1
            )
            recovered += 1
            changed = True
        if changed:
            page["text"] = "\n".join(line["text"] for line in page["lines"])
    return recovered


def _amount_column_left(page: dict[str, Any]) -> int | None:
    width = page.get("width", 0)
    lefts = [
        word["left"]
        for line in page.get("lines", [])
        for word in line.get("words", [])
        if _AMOUNT_WORD_RE.match(word.get("text", "")) and word["left"] > 0.6 * width
    ]
    return min(lefts) if lefts else None


def recover_amount_column(
    pages: list[dict[str, Any]],
    region_ocr: Callable[[int, tuple[int, int, int, int]], str],
    pad: int = 8,
) -> int:
    """Re-OCR the amount cell for transaction rows whose amount was dropped.

    For each transaction date row with no amount token, the amount-column region
    at that row's vertical band is re-OCR'd via ``region_ocr``. The amount is
    accepted only when the crop yields exactly one amount token, so ambiguous or
    empty crops leave the row untouched (it stays an exception). Returns the
    number of rows recovered. Pure logic; ``region_ocr`` performs the rendering.
    """
    recovered = 0
    for page in pages:
        column_left = _amount_column_left(page)
        if column_left is None:
            continue
        width = page["width"]
        changed = False
        for line in page["lines"]:
            text = line.get("text", "")
            if not _SC_DATE_PREFIX_RE.match(text) or _AMOUNT_IN_TEXT_RE.search(text):
                continue
            box = (
                max(0, int(column_left) - 30),
                max(0, line["top"] - pad),
                width,
                line["bottom"] + pad,
            )
            crop_text = region_ocr(page["page_no"], box) or ""
            tokens = _AMOUNT_TOKEN_RE.findall(crop_text)
            if len(tokens) == 1:
                line["text"] = f"{text} {tokens[0].strip()}"
                recovered += 1
                changed = True
        if changed:
            page["text"] = "\n".join(line["text"] for line in page["lines"])
    return recovered


def build_amount_region_ocr(
    pdf_path: Path,
    dpi: int,
) -> Callable[[int, tuple[int, int, int, int]], str]:
    """Return a region-OCR callable that renders a page once and crops on demand.

    The crop is upscaled and read with PSM 7 (single line) via a temp PNG path,
    avoiding the PIL-image pipe that crashes on some tesseract builds.
    """
    configure_tesseract()
    rendered: dict[int, Image.Image] = {}

    def region_ocr(page_no: int, box: tuple[int, int, int, int], scale: int = 3) -> str:
        image = rendered.get(page_no)
        if image is None:
            with fitz.open(pdf_path) as document:
                pixmap = document.load_page(page_no - 1).get_pixmap(
                    dpi=dpi, alpha=False, colorspace=fitz.csRGB
                )
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            rendered[page_no] = image
        crop = image.crop(box)
        crop = crop.resize((crop.width * scale, crop.height * scale))
        with tempfile.TemporaryDirectory() as work_dir:
            crop_path = Path(work_dir) / "amount_cell.png"
            crop.save(crop_path)
            return pytesseract.image_to_string(
                str(crop_path), lang="eng", config="--oem 3 --psm 7", timeout=60
            ).strip()

    return region_ocr


DATE_RECOVERY_DPIS = (250, 300, 350, 400, 450)
DATE_RECOVERY_PSMS = (6, 7, 11, 13)


def build_date_region_ocr(
    pdf_path: Path,
    primary_dpi: int,
) -> Callable[[int, tuple[int, int, int, int]], list[tuple[int, int, str]]]:
    """Return a date-cell region OCR that reads across a DPI x PSM matrix.

    The box is given in the primary OCR DPI's coordinate space; for each target
    DPI the page is re-rendered and the box is scaled accordingly, then read at
    each PSM. Returns ``[(dpi, psm, text), ...]`` for consensus scoring. Separate
    from the amount region OCR so amount recovery behaviour is unchanged.
    """
    configure_tesseract()
    rendered: dict[tuple[int, int], Image.Image] = {}

    def date_region_ocr(
        page_no: int, box: tuple[int, int, int, int]
    ) -> list[tuple[int, int, str]]:
        reads: list[tuple[int, int, str]] = []
        for dpi in DATE_RECOVERY_DPIS:
            image = rendered.get((page_no, dpi))
            if image is None:
                with fitz.open(pdf_path) as document:
                    pixmap = document.load_page(page_no - 1).get_pixmap(
                        dpi=dpi, alpha=False, colorspace=fitz.csRGB
                    )
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                rendered[(page_no, dpi)] = image
            scale = dpi / primary_dpi
            scaled = tuple(int(round(coord * scale)) for coord in box)
            crop = image.crop(scaled)
            crop = crop.resize((crop.width * 3, crop.height * 3))
            with tempfile.TemporaryDirectory() as work_dir:
                crop_path = Path(work_dir) / "date_cell.png"
                crop.save(crop_path)
                for psm in DATE_RECOVERY_PSMS:
                    text = pytesseract.image_to_string(
                        str(crop_path), lang="eng", config=f"--oem 3 --psm {psm}", timeout=60
                    ).strip()
                    reads.append((dpi, psm, text))
        return reads

    return date_region_ocr


class OcrUnavailableError(RuntimeError):
    pass


def configure_tesseract() -> str:
    command = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
    if not command:
        raise OcrUnavailableError(
            "Tesseract was not found. Install it with 'brew install tesseract' "
            "or set TESSERACT_CMD."
        )
    pytesseract.pytesseract.tesseract_cmd = command
    return command


def _words_to_lines(data: dict[str, list[Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index]).strip()
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if not text or confidence < 0:
            continue
        key = (
            int(data["block_num"][index]),
            int(data["par_num"][index]),
            int(data["line_num"][index]),
        )
        groups[key].append(
            {
                "text": text,
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
                "confidence": confidence,
            }
        )
    lines = []
    for words in groups.values():
        words.sort(key=lambda word: word["left"])
        lines.append(
            {
                "text": " ".join(word["text"] for word in words),
                "left": min(word["left"] for word in words),
                "top": min(word["top"] for word in words),
                "right": max(word["left"] + word["width"] for word in words),
                "bottom": max(word["top"] + word["height"] for word in words),
                "confidence": round(sum(word["confidence"] for word in words) / len(words), 2),
                "words": words,
            }
        )
    return sorted(lines, key=lambda line: (line["top"], line["left"]))


def _cache_suffix(first_page_only: bool, dpi: int) -> str:
    base = "ocr_first_page" if first_page_only else "ocr_pages"
    # Keep the historical filename for the default DPI so existing caches (and
    # the verified TNG OCR results) are reused untouched; higher-DPI passes get
    # their own cache file instead of clobbering them.
    if dpi != DEFAULT_OCR_DPI:
        base = f"{base}_dpi{dpi}"
    return f"{base}.json"


def ocr_pdf_pages(
    pdf_path: Path,
    cache_root: Path,
    force: bool = False,
    dpi: int = DEFAULT_OCR_DPI,
    first_page_only: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    configure_tesseract()
    cache_dir = cache_directory(pdf_path, cache_root)
    cache_file = cache_dir / _cache_suffix(first_page_only, dpi)
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8"))["pages"], True
    document = fitz.open(pdf_path)
    page_count = min(1, document.page_count) if first_page_only else document.page_count
    pages = []
    try:
        with tempfile.TemporaryDirectory() as work_dir:
            for page_index in range(page_count):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
                # Hand tesseract a PNG path rather than a PIL image: some
                # tesseract/leptonica builds emit non-UTF-8 bytes on the image
                # pipe, which crashes pytesseract's PIL-image code path.
                image_path = Path(work_dir) / f"page_{page_index + 1}.png"
                pixmap.save(image_path)
                data = pytesseract.image_to_data(
                    str(image_path),
                    lang="eng",
                    config="--oem 3 --psm 6",
                    output_type=Output.DICT,
                    timeout=180,
                )
                lines = _words_to_lines(data)
                pages.append(
                    {
                        "page_no": page_index + 1,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "text": "\n".join(line["text"] for line in lines),
                        "lines": lines,
                    }
                )
    finally:
        document.close()
    cache_file.write_text(json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8")
    return pages, False
