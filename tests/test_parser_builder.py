import json
from pathlib import Path

import pytest

from src.parser_builder import (
    ParserBuildError,
    ParserBuildSource,
    build_parser_artifacts,
    build_parser_builder_prompt,
    write_parser_build_index,
)


UNKNOWN_TEXT = """
Example Community Bank
Account Number: 123456789012
Cardholder Name: Example Person
Email: person@example.com
01 JAN SAMPLE SHOP 10.00
"""


class FakeOpenRouterClient:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, model: str) -> str:
        self.calls.append({"prompt": prompt, "model": model})
        return "# Proposed deterministic parser\n\nReview this scaffold."


class FailingClient:
    def generate(self, prompt: str, model: str) -> str:
        raise AssertionError("OpenRouter must not be called")


def source(detected_statement_type=None) -> ParserBuildSource:
    return ParserBuildSource(
        source_file="unknown_123456789012.pdf",
        extracted_text=UNKNOWN_TEXT,
        detected_statement_type=detected_statement_type,
        extraction_mode="native_text",
        pages_included=1,
    )


def test_parser_builder_dry_run_writes_prompt_and_metadata_without_key_or_call(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    metadata = build_parser_artifacts(
        source(),
        output_dir=tmp_path,
        model="test/model",
        dry_run=True,
        client=FailingClient(),
    )

    prompt_path = tmp_path / metadata["prompt_file"]
    metadata_path = tmp_path / "unknown_LONG_ID_REDACTED.metadata.json"
    assert prompt_path.is_file()
    assert metadata_path.is_file()
    assert metadata["openrouter_called"] is False
    assert "123456789012" not in prompt_path.read_text()
    assert "person@example.com" not in prompt_path.read_text()


def test_parser_builder_real_mode_calls_fake_client_and_writes_response(tmp_path: Path):
    client = FakeOpenRouterClient()

    metadata = build_parser_artifacts(
        source(),
        output_dir=tmp_path,
        model="test/model",
        dry_run=False,
        client=client,
    )

    response_path = tmp_path / metadata["response_file"]
    assert len(client.calls) == 1
    assert response_path.read_text().startswith("# Proposed deterministic parser")
    assert metadata["openrouter_called"] is True
    assert not list(tmp_path.glob("*.xlsx"))


def test_parser_builder_real_mode_requires_openrouter_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ParserBuildError, match="OPENROUTER_API_KEY"):
        build_parser_artifacts(
            source(),
            output_dir=tmp_path,
            model="test/model",
            dry_run=False,
        )


def test_supported_statement_refuses_parser_build_before_client_call(tmp_path: Path):
    with pytest.raises(ParserBuildError, match="already supported"):
        build_parser_artifacts(
            source(detected_statement_type="tng"),
            output_dir=tmp_path,
            model="test/model",
            dry_run=False,
            client=FailingClient(),
        )


def test_force_parser_build_allows_supported_statement(tmp_path: Path):
    metadata = build_parser_artifacts(
        source(detected_statement_type="sc"),
        output_dir=tmp_path,
        model="test/model",
        dry_run=True,
        force_parser_build=True,
    )

    assert metadata["detected_statement_type"] == "sc"


def test_parser_builder_prompt_requests_reviewable_deterministic_scaffolds():
    prompt = build_parser_builder_prompt(
        sanitized_text="Example Bank\n01 JAN SHOP 10.00",
        source_file="example.pdf",
        extraction_mode="native_text",
        pages_included=1,
    )

    assert "detection phrases" in prompt
    assert "parser file scaffold" in prompt
    assert "test fixture scaffold" in prompt
    assert "Do not extract runtime transactions" in prompt


def test_metadata_contains_required_audit_fields(tmp_path: Path):
    metadata = build_parser_artifacts(
        source(),
        output_dir=tmp_path,
        model="test/model",
        dry_run=True,
    )
    persisted = json.loads(
        (tmp_path / "unknown_LONG_ID_REDACTED.metadata.json").read_text()
    )

    assert persisted == metadata
    assert set(
        [
            "source_file",
            "prompt_file",
            "detected_statement_type",
            "parser_build_reason",
            "redaction_scan_passed",
            "character_count",
            "estimated_token_count",
            "pages_included",
            "extraction_mode",
            "openrouter_called",
        ]
    ).issubset(metadata)


def test_folder_index_contains_only_metadata_entries(tmp_path: Path):
    entries = [
        {
            "source_file": "unknown.pdf",
            "prompt_file": "unknown.prompt.txt",
            "openrouter_called": False,
        }
    ]

    index_path = write_parser_build_index(tmp_path, entries)

    assert json.loads(index_path.read_text()) == entries
