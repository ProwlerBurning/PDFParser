# Release Checklist

Complete every item before tagging a release.

- [ ] Tests pass (`python -m pytest`).
- [ ] Compileall passes (`python -m compileall extract.py src tests scripts`).
- [ ] Repository safety workflow passes (no unsafe tracked files).
- [ ] No real statements anywhere in the tree or history of the release.
- [ ] No PDFs or XLSX files tracked.
- [ ] LICENSE present.
- [ ] README accurate and up to date.
- [ ] `VERSION` updated.
- [ ] `CHANGELOG.md` updated (move the unreleased section to the new version).
- [ ] Release tag planned (e.g. `v0.1.0`).
- [ ] Release notes drafted.
