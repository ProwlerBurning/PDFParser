# Pull Request

## Summary

<!-- Describe what this PR does and why. -->

## Checklist

- [ ] Tests pass (`pytest`).
- [ ] Compileall passes (`python -m compileall extract.py src tests scripts`).
- [ ] No real financial data included.
- [ ] No PDFs or XLSX files added.
- [ ] No cache, output, input_pdfs, or review_bundle files added.
- [ ] Normal extraction remains local and deterministic.
- [ ] No online API call added to the normal parser flow.
- [ ] No LLM fallback added to the normal parser flow.
- [ ] README updated if behavior changed.
- [ ] Synthetic fixtures only.
