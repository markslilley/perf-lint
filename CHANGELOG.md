# Changelog

All notable changes to `perf-lint-tool` are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Versioning note:** `perf-lint-tool` (this CLI) and
> [`perf-lint-action`](https://github.com/markslilley/perf-lint-action) are versioned
> **independently**. The Action being on v1.2.0 does not mean the CLI is behind — the
> Action installs whatever CLI version it is told to and only uses the stable flag
> surface (`check`, `--config`, `--severity`, `--ignore-rule`, `--no-color`,
> `--format`, `--output`, and `PERF_LINT_API_KEY` from the environment).

## [1.1.0] — 2026-08-08

### Added

- **`perf-ecosystem.yml` config discovery.** When a `perf-ecosystem.yml` is present,
  perf-lint now auto-injects the API key and URL from its
  `services.perf_lint_api` section, so a repo that already configures the ecosystem
  does not have to set `PERF_LINT_API_KEY` separately. Environment variables still
  take precedence. (`src/perf_lint/config/loader.py`)
- **Version-consistency tests** (`tests/unit/test_version.py`). `pyproject.toml` and
  `perf_lint.__version__` are two independent sources of truth, and nothing checked
  that they matched. A mismatch would publish a wheel labelled one version that
  reports another in `--version`, in SARIF uploads to GitHub Code Scanning, and in
  the API User-Agent. This release found exactly that drift and now guards it.

### Changed

- **Plugin loading is no longer silent.** Plugins resolved from absolute paths emit
  `logger.info()` so unusual plugin locations are visible in CI logs. Previously a
  plugin could load from anywhere with no indication in the output — an unhelpful
  place to have no logging, given plugins execute arbitrary code.
  (`src/perf_lint/plugins/loader.py`)

### Fixed

- Documentation pointed at `perflint.io`, which is not our domain. Corrected to
  <https://perflint.martkos-it.co.uk> throughout.
- `CLAUDE.md` tier table now records Pro/Team pricing and where the paid rules are
  sold, so the open-core boundary is unambiguous.

## [1.0.2] — 2026-03-05

- Projected score in `--fix-dry-run`; JMeter sample file corrections.

## [1.0.1] — 2026-03-01

- Post-launch fixes.

## [1.0.0] — 2026-02-28

- First public release. 18 free-tier rules across JMeter, k6 and Gatling; SARIF,
  JSON and text reporters; `--fix` auto-correction; plugin entry point for the
  Pro/Team rule packs.

[1.1.0]: https://github.com/markslilley/perf-lint/releases/tag/v1.1.0
[1.0.2]: https://pypi.org/project/perf-lint-tool/1.0.2/
[1.0.1]: https://pypi.org/project/perf-lint-tool/1.0.1/
[1.0.0]: https://pypi.org/project/perf-lint-tool/1.0.0/
