# Roadmap

This roadmap is indicative and may change. It does **not** commit to dates.

## v0.1.0 readiness
- Stabilize the three supported providers.
- Governance, security, support, and CI documentation in place.
- Repository safety checks enforced in CI.

## Near-term
- Safer fixture generation tooling (easier creation of synthetic, privacy-safe
  fixtures).
- More synthetic tests across edge cases and providers.
- Better validation and reconciliation reporting (clearer exception reasons and
  per-statement checks).

## Later
- Additional Malaysian banks or e-wallets (driven by synthetic fixtures and
  redacted layout notes).
- Packaging improvements (installation and distribution).

## Explicit non-goals
- **No plan to add cloud parsing to the normal parser flow.**
- **No plan to add LLM fallback to the normal parser flow.**
- Normal extraction will remain local, deterministic, and masked-by-default.
