from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz
import pytesseract
from PIL import Image
from pytesseract import Output

from src.text_extract import cache_directory


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


def ocr_pdf_pages(
    pdf_path: Path,
    cache_root: Path,
    force: bool = False,
    dpi: int = 250,
    first_page_only: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    configure_tesseract()
    cache_dir = cache_directory(pdf_path, cache_root)
    suffix = "ocr_first_page.json" if first_page_only else "ocr_pages.json"
    cache_file = cache_dir / suffix
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8"))["pages"], True
    document = fitz.open(pdf_path)
    page_count = min(1, document.page_count) if first_page_only else document.page_count
    pages = []
    try:
        for page_index in range(page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            data = pytesseract.image_to_data(
                image,
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
