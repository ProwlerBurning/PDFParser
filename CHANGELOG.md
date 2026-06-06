# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added
- Local, deterministic PDF-to-Excel parsing of Malaysian statements (no cloud
  parsing by default, no online API calls or LLM fallback in the normal flow).
- Supported providers:
  - Touch 'n Go eWallet
  - Standard Chartered credit card
  - Hong Leong Bank credit card
- Masked output by default; `--unmask` is an explicit local debug mode only.
- Optional, review-only Parser Builder Mode for designing new deterministic
  parsers (does not run during normal extraction and does not auto-install code).
- Synthetic-only test suite and a CLI-based private sample verification helper
  that uses a temporary cache and workbook.
