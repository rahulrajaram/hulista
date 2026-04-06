# Releasing

This project already has automated publishing wired up in GitHub Actions. The goal is to make releases repeatable and low-drama.

## Docs publishing

The public documentation site is built from this `docs/` directory and deployed by the `Docs` workflow to GitHub Pages.

Before merging docs changes:

```bash
python -m pip install -r docs/requirements.txt
make docs-build
```

## Package publishing

The PyPI workflow publishes the `hulista` distribution only.

Important implication:

- A release tag publishes the bundled `hulista` wheel, which contains the toolkit modules from this monorepo.

## Recommended release flow

1. Update package metadata and `CHANGELOG.md`.
2. Run local quality gates: `make test`, `make coverage`, `make typecheck`, `make deprecationcheck`, `make build`.
3. Trigger a manual `Publish` workflow run against `testpypi` for the target ref.
4. Verify package pages and install commands from TestPyPI.
5. Push the release tag to publish to PyPI.
6. Confirm the docs site and PyPI pages point to the same versioned story.

See the full checklist in the repository root:

- [`RELEASING.md`](https://github.com/rahulrajaram/hulista/blob/master/RELEASING.md)
