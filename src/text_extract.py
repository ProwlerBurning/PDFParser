from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pdfplumber


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_directory(pdf_path: Path, cache_root: Path) -> Path:
    path = cache_root / file_sha256(pdf_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def has_useful_text(pages: list[str], minimum_chars: int = 100) -> bool:
    useful = sum(len("".join(character for character in page if character.isalnum())) for page in pages)
    return useful >= minimum_chars


def extract_native_pages(
    pdf_path: Path,
    cache_root: Path,
    force: bool = False,
) -> tuple[list[str], bool]:
    cache_dir = cache_directory(pdf_path, cache_root)
    cache_file = cache_dir / "native_text.json"
    if cache_file.exists() and not force:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return payload["pages"], True
    with pdfplumber.open(pdf_path) as pdf:
        pages = [(page.extract_text(x_tolerance=2, y_tolerance=3) or "") for page in pdf.pages]
    cache_file.write_text(json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8")
    return pages, False
