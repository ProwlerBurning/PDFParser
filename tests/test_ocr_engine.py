from pathlib import Path

import fitz
import pytesseract

from src import ocr_engine


def _make_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "SAMPLE OCR PAGE 10.00")
    document.save(path)
    document.close()


def _fake_image_to_data(*args, **kwargs):
    # Record what kind of first argument pytesseract received.
    _fake_image_to_data.received_arg = args[0] if args else kwargs.get("image")
    return {
        "text": ["SAMPLE", "10.00"],
        "conf": ["95", "95"],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [10, 200],
        "top": [10, 10],
        "width": [80, 50],
        "height": [20, 20],
    }


def test_ocr_passes_file_path_not_pil_image(tmp_path, monkeypatch):
    # The pytesseract PIL-image path crashes on some tesseract builds; OCR must
    # hand tesseract a file path string instead.
    monkeypatch.setattr(ocr_engine, "configure_tesseract", lambda: "tesseract")
    monkeypatch.setattr(pytesseract, "image_to_data", _fake_image_to_data)
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf)

    pages, cached = ocr_engine.ocr_pdf_pages(pdf, tmp_path / "cache")

    assert not cached
    assert pages[0]["text"]
    assert isinstance(_fake_image_to_data.received_arg, str)
    assert Path(_fake_image_to_data.received_arg).suffix == ".png"


def _sc_pages():
    return [
        {
            "page_no": 1,
            "width": 1000,
            "text": "",
            "lines": [
                {
                    "text": "01 Jan 02 Jan MERCH A Txn Ref: REF 50.00",
                    "left": 50, "top": 10, "right": 800, "bottom": 30,
                    "words": [{"text": "50.00", "left": 760}],
                },
                {
                    "text": "03 Jan 04 Jan GRAB RIDES-EC Txn Ref:",
                    "left": 50, "top": 50, "right": 400, "bottom": 70, "words": [],
                },
                {
                    "text": "PETALING JAMY 24506185279027397641718",
                    "left": 120, "top": 72, "right": 600, "bottom": 90, "words": [],
                },
            ],
        }
    ]


def test_recover_amount_column_appends_single_amount():
    pages = _sc_pages()
    calls = []

    def region_ocr(page_no, box):
        calls.append((page_no, box))
        return "9.00 |"  # column-border artifact alongside the amount

    recovered = ocr_engine.recover_amount_column(pages, region_ocr)

    assert recovered == 1
    assert calls == [(1, calls[0][1])]  # only the missing-amount date row was re-OCR'd
    assert pages[0]["lines"][1]["text"].endswith("Txn Ref: 9.00")
    assert pages[0]["text"].count("9.00") == 1


def test_recover_amount_column_rejects_ambiguous_or_empty_crops():
    for crop_result in ("12.00 34.00", "| |", ""):
        pages = _sc_pages()
        recovered = ocr_engine.recover_amount_column(pages, lambda page_no, box: crop_result)
        assert recovered == 0
        assert pages[0]["lines"][1]["text"] == "03 Jan 04 Jan GRAB RIDES-EC Txn Ref:"


def _date_pages():
    return [
        {
            "page_no": 1,
            "width": 2975,
            "text": "11 Mar 41 Mar DUITNOW PAY-TO-ACCOUNT Txn Ref: 2025031101561108311809 500.00CR",
            "lines": [
                {
                    "text": "11 Mar 41 Mar DUITNOW PAY-TO-ACCOUNT Txn Ref: 2025031101561108311809 500.00CR",
                    "left": 457, "top": 1930, "bottom": 1966,
                    "words": [
                        {"text": "11", "left": 457}, {"text": "Mar", "left": 501},
                        {"text": "41", "left": 684}, {"text": "Mar", "left": 728},
                        {"text": "DUITNOW", "left": 863},
                    ],
                }
            ],
        }
    ]


def test_recover_transaction_dates_fixes_invalid_day_with_anchor():
    pages = _date_pages()
    # both scales agree on 11 Mar 11 Mar
    recovered = ocr_engine.recover_transaction_dates(
        pages, lambda page_no, box, scale=3: "11 Mar 11 Mar"
    )
    assert recovered == 1
    assert pages[0]["lines"][0]["text"].startswith("11 Mar 11 Mar DUITNOW")
    assert "41 Mar" not in pages[0]["lines"][0]["text"]
    assert "41 Mar" not in pages[0]["text"]


def test_recover_transaction_dates_rejects_when_scales_disagree():
    # scale 3 reads 14 Mar, scale 4 reads 11 Mar -> not deterministic -> keep as exception
    def region_ocr(page_no, box, scale=3):
        return "11 Mar 14 Mar" if scale == 3 else "11 Mar 11 Mar"

    pages = _date_pages()
    recovered = ocr_engine.recover_transaction_dates(pages, region_ocr)
    assert recovered == 0
    assert "41 Mar" in pages[0]["lines"][0]["text"]


def test_recover_transaction_dates_keeps_row_when_not_deterministically_valid():
    # still-invalid txn, anchor mismatch, junk, empty -> no change (stays an exception downstream)
    for crop in ("11 Mar 41 Mar", "13 Mar 11 Mar", "garbage", ""):
        pages = _date_pages()
        recovered = ocr_engine.recover_transaction_dates(
            pages, lambda page_no, box, scale=3: crop
        )
        assert recovered == 0
        assert "41 Mar" in pages[0]["lines"][0]["text"]


def test_recover_transaction_dates_ignores_valid_rows():
    pages = _date_pages()
    pages[0]["lines"][0]["text"] = "11 Mar 10 Mar DUITNOW PAY-TO-ACCOUNT Txn Ref: 2025031101561108311809 500.00CR"
    pages[0]["lines"][0]["words"][2]["text"] = "10"
    calls = []
    recovered = ocr_engine.recover_transaction_dates(
        pages, lambda page_no, box, scale=3: calls.append(box) or "x"
    )
    assert recovered == 0 and calls == []


def test_ocr_cache_filename_encodes_non_default_dpi(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_engine, "configure_tesseract", lambda: "tesseract")
    monkeypatch.setattr(pytesseract, "image_to_data", _fake_image_to_data)
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf)
    cache_root = tmp_path / "cache"

    ocr_engine.ocr_pdf_pages(pdf, cache_root, dpi=350)

    cache_dirs = list(cache_root.iterdir())
    assert cache_dirs
    files = {p.name for p in cache_dirs[0].iterdir()}
    assert "ocr_pages_dpi350.json" in files
    assert "ocr_pages.json" not in files
