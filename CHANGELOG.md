# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.2.0] — 2026-04-12

### Added
- `--json` flag on `list`, `status`, `close`, `close-all` commands for explicit JSON output (also auto-enables when stdout is not a TTY)
- `format_deployments_json()` for machine-readable deployment listing
- `_confirm()` helper to DRY confirmation prompts across `cli.py` and `api.py`
- `pyright` type checking in dev dependencies, CI workflow, and `just typecheck` recipe
- 20 new tests: interactive picker (arrow keys, q/ctrl-c, tags+SSH), `_confirm`, `format_deployments_json`, `get_provider` response shapes
- `just typecheck` Justfile recipe

### Changed
- Confirmation prompts now use shared `_confirm()` instead of duplicated `input()` logic
- `use_json` detection unified: `args.json or not sys.stdout.isatty()`
- Fixed 15 pyright type errors (assertions on `_extract_dseq()` `str|None` returns)

### Fixed
- All pre-existing lint issues in test files (unused imports, unsorted imports)

## [1.1.0] — 2026-04-12

### Changed
- Restructured from `scripts/` flat files to a proper `just_akash/` Python package
- All CLI invocations now use `uv run just-akash` instead of `python3 scripts/...`
- Justfile recipes updated to use the new package entry point

### Added
- `-y` / `--yes` flag on `close` and `close-all` commands to skip confirmation prompts (non-interactive mode)
- Lint recipes: `just lint`, `just fmt`, `just check`
- Secret scanning recipe: `just secrets`
- Pre-commit config (gitleaks + ruff)
- GitHub Actions CI (gitleaks, trufflehog, detect-secrets, ruff, pytest)
- Community files: LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, issue/PR templates

### Fixed
- Provider registry lookup (`get_provider`) crashed silently when `/v1/providers` returned a bare list instead of a wrapped dict — now handles both response shapes correctly

## [1.0.0] — 2026-04-11

### Added
- Deploy SSH-enabled instances on Akash Network via Console API
- Two-phase bid polling: configurable `--bid-wait` (default 60s) and `--bid-wait-retry` (default 120s)
- Cheapest bid selection with allowlist filtering
- Provider diagnostics when allowed providers don't bid (on-chain status, uptime, capacity)
- SSH connectivity with auto-detected key path
- Interactive deployment picker (arrow keys) for multi-deployment environments
- Deployment tagging (DSEQ → human-readable name)
- `just` recipes for all lifecycle operations (up, connect, down, down-all, tag, ls, status, test)
- `just-akash` CLI with subcommands: `deploy`, `api`, `test`
- Timestamped log files in `.logs/just/` with start/end metadata and exit codes
- Full lifecycle integration test (up → verify → SSH → down → cleanup)
- gitleaks secret scanning with CI workflow
- TruffleHog secret scanning with CI workflow
- detect-secrets baseline scanning with CI workflow
- MIT License (Jonathan Borduas)
- Contributing guide, Code of Conduct, Security policy
- GitHub issue templates (bug report, feature request) and PR template
