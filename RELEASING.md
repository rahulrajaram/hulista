# Releasing hulista

This repository already has the two core automation pieces needed for a public release:

- GitHub Pages deployment for docs via [`.github/workflows/docs.yml`](.github/workflows/docs.yml)
- Trusted Publishing to PyPI and TestPyPI via [`.github/workflows/publish.yml`](.github/workflows/publish.yml)

## One-time repository setup

Before the first public release, confirm these settings in GitHub and PyPI:

1. Enable GitHub Pages for this repository and allow GitHub Actions to deploy it.
2. Create `hulista` and each leaf package on PyPI and TestPyPI if you want to reserve the names ahead of time.
3. Configure PyPI Trusted Publishing for this repository and the `pypi` environment.
4. Configure TestPyPI Trusted Publishing for this repository and the `testpypi` environment.
5. Protect the `pypi` environment if you want a manual approval gate before production publishing.

## Pre-release checklist

1. Make sure `CHANGELOG.md` reflects the release contents.
2. Confirm package versions are aligned across `pyproject.toml` files and any exported `__version__` constants.
3. Build and verify the docs locally:

```bash
python -m pip install -r docs/requirements.txt
make docs-build
```

4. Run the release gates:

```bash
make test
make coverage
make typecheck
make security
make deprecationcheck
make build
```

5. Sanity-check the umbrella package metadata:

```bash
python -m pip install -U build twine pkginfo
cd hulista
python -m build .
python -m twine check dist/*
```

## TestPyPI dry run

Use the existing `Publish` workflow before the first real release and before any packaging-heavy change:

1. Open GitHub Actions.
2. Run `Publish`.
3. Choose `repository = testpypi`.
4. Set `ref` to the branch, commit SHA, or release candidate tag you want to validate.
5. Wait for all matrix jobs to finish.

Then validate installs from TestPyPI in a clean virtual environment. Example:

```bash
python -m venv .venv-testpypi
source .venv-testpypi/bin/activate
python -m pip install -U pip
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple hulista
python -c "import hulista; print(hulista.__version__)"
```

## Production release

The production path is tag-driven. Pushing a tag that matches `v*` will publish every package in the monorepo.

Recommended sequence:

1. Merge the release commit to `master`.
2. Create an annotated tag such as `v0.1.1`.
3. Push the tag.
4. Watch [`.github/workflows/publish.yml`](.github/workflows/publish.yml) complete for every package.
5. Verify the live pages on PyPI and the docs site.

## Release model

This repo is currently set up for coordinated releases:

- one changelog
- one release tag namespace
- one publish workflow matrix for all packages

That is a good fit while the package family is still moving together. If you later want independent release cadences, the publish workflow and tag strategy should be split per package.
