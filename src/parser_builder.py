from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from src.ocr_engine import ocr_pdf_pages
from src.pdf_detect import detect_statement_type
from src.redaction import redaction_scan, sanitize_statement_text
from src.text_extract import extract_native_pages, has_useful_text


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_PARSER_BUILD_MODEL = os.environ.get(
    "OPENROUTER_PARSER_BUILD_MODEL",
    "openai/gpt-4.1-mini",
)


class ParserBuildError(RuntimeError):
    pass


class ParserBuilderClient(Protocol):
    def generate(self, prompt: str, model: str) -> str:
        ...


@dataclass(frozen=True)
class ParserBuildSource:
    source_file: str
    extracted_text: str
    detected_statement_type: str | None
    extraction_mode: str
    pages_included: int


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, timeout: int = 120):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ParserBuildError(
                "OPENROUTER_API_KEY is required for OpenRouter Parser Builder mode"
            )
        self.timeout = timeout

    def generate(self, prompt: str, model: str) -> str:
        response = requests.post(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You design deterministic local Python parsers. "
                            "Never extract runtime transaction data."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        if not response.ok:
            raise ParserBuildError(
                f"OpenRouter request failed with HTTP {response.status_code}"
            )
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ParserBuildError("OpenRouter returned an invalid response shape") from error
        if not isinstance(content, str) or not content.strip():
            raise ParserBuildError("OpenRouter returned an empty parser-builder response")
        return content


def build_parser_builder_prompt(
    sanitized_text: str,
    source_file: str,
    extraction_mode: str,
    pages_included: int,
) -> str:
    return f"""# Deterministic Statement Parser Builder

Analyze the sanitized statement sample below and propose a reviewable
development packet for a new deterministic Python parser.

Do not extract runtime transactions. Do not return transaction rows for Excel.
Do not request or reconstruct redacted private data.

Source: {source_file}
Local extraction mode: {extraction_mode}
Pages included: {pages_included}

Provide:
1. Provider name and statement category.
2. Reliable detection phrases.
3. Transaction row patterns, including wrapped-line handling.
4. Summary fields and metadata patterns.
5. Debit, credit, currency, and amount-sign rules.
6. Deterministic validation and reconciliation strategy.
7. A parser file scaffold compatible with `src/parsers/base.py`.
8. A synthetic test fixture scaffold with no real personal data.
9. Focused pytest test cases and known limitations.

Label all proposed code as review-required. Do not claim the parser is ready
until it has been tested locally against private samples.

## Sanitized statement sample

```text
{sanitized_text}
```
"""


def prepare_parser_build_source(
    pdf_path: Path,
    cache_root: Path,
    max_pages: int = 5,
    force: bool = False,
) -> ParserBuildSource:
    if max_pages < 1:
        raise ParserBuildError("--parser-build-max-pages must be at least 1")
    native_pages, _ = extract_native_pages(pdf_path, cache_root, force)
    selected_native = native_pages[:max_pages]
    if has_useful_text(selected_native):
        text = "\n".join(selected_native)
        extraction_mode = "native_text"
        pages_included = len(selected_native)
    else:
        ocr_pages, _ = ocr_pdf_pages(pdf_path, cache_root, force)
        selected_ocr = ocr_pages[:max_pages]
        text = "\n".join(page.get("text", "") for page in selected_ocr)
        extraction_mode = "ocr"
        pages_included = len(selected_ocr)
    return ParserBuildSource(
        source_file=pdf_path.name,
        extracted_text=text,
        detected_statement_type=detect_statement_type(text),
        extraction_mode=extraction_mode,
        pages_included=pages_included,
    )


def build_parser_artifacts(
    source: ParserBuildSource,
    output_dir: Path,
    model: str,
    dry_run: bool,
    force: bool = False,
    force_parser_build: bool = False,
    client: ParserBuilderClient | None = None,
) -> dict[str, object]:
    if source.detected_statement_type and not force_parser_build:
        raise ParserBuildError(
            f"Statement type '{source.detected_statement_type}' is already supported; "
            "use --force-parser-build to generate review artifacts anyway"
        )

    sanitized_text = sanitize_statement_text(source.extracted_text)
    sanitized_source_file = sanitize_statement_text(Path(source.source_file).name)
    scan = redaction_scan(f"{sanitized_source_file}\n{sanitized_text}")
    if not scan.passed:
        categories = ", ".join(scan.categories)
        raise ParserBuildError(
            f"Redaction scan failed for categories: {categories}"
        )

    safe_stem = _safe_source_stem(sanitized_source_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / f"{safe_stem}.prompt.txt"
    metadata_path = output_dir / f"{safe_stem}.metadata.json"
    response_path = output_dir / f"{safe_stem}.llm_response.md"
    paths = [prompt_path, metadata_path]
    if not dry_run:
        paths.append(response_path)
    existing = [path.name for path in paths if path.exists()]
    if existing and not force:
        raise ParserBuildError(
            "Parser-build artifacts already exist; use --force to overwrite"
        )

    prompt = build_parser_builder_prompt(
        sanitized_text=sanitized_text,
        source_file=sanitized_source_file,
        extraction_mode=source.extraction_mode,
        pages_included=source.pages_included,
    )
    prompt_scan = redaction_scan(prompt)
    if not prompt_scan.passed:
        categories = ", ".join(prompt_scan.categories)
        raise ParserBuildError(
            f"Parser-builder prompt redaction scan failed for categories: {categories}"
        )
    prompt_path.write_text(prompt, encoding="utf-8")

    metadata: dict[str, object] = {
        "source_file": sanitized_source_file,
        "prompt_file": prompt_path.name,
        "detected_statement_type": source.detected_statement_type,
        "parser_build_reason": (
            "forced_supported_provider"
            if source.detected_statement_type
            else "unsupported_provider"
        ),
        "redaction_scan_passed": True,
        "character_count": len(sanitized_text),
        "estimated_token_count": math.ceil(len(prompt) / 4),
        "pages_included": source.pages_included,
        "extraction_mode": source.extraction_mode,
        "openrouter_called": False,
        "model": model,
    }
    if not dry_run:
        active_client = client or OpenRouterClient()
        response_text = active_client.generate(prompt, model)
        response_path.write_text(response_text, encoding="utf-8")
        metadata["openrouter_called"] = True
        metadata["response_file"] = response_path.name
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return metadata


def write_parser_build_index(
    output_dir: Path,
    entries: list[dict[str, object]],
    force: bool = False,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.json"
    if index_path.exists() and not force:
        raise ParserBuildError(
            "Parser-build index already exists; use --force to overwrite"
        )
    index_path.write_text(
        json.dumps(entries, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return index_path


def _safe_source_stem(source_file: str) -> str:
    stem = Path(source_file).stem
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", stem)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or "statement"
