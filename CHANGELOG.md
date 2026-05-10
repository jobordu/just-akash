# Changelog

All notable changes to this project will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.6.0] — 2026-05-10

### Added
- **Tiered provider selection** (issue #11): new `AKASH_PROVIDERS_BACKUP` env var and `--provider` / `--backup-provider` CLI flags. Three-phase bid-selection state machine — preferred-only patience → preferred-grace (first-wins) → backup fallback. Cheapest preferred wins when healthy; bounded `T1+T2` patience for slow preferred; cheapest backup wins when preferred fully unresponsive. Each bid tagged `[PREFERRED]` / `[BACKUP]` / `[FOREIGN]` in logs; selection log line names which phase chose the winner.
- `.env.example` ships with 3 vetted preferred providers + 10 backup providers — `cp .env.example .env` gets tiered selection out of the box.
- Tier-aware provider assertion in all three e2e tests: verifies the selected provider is in `AKASH_PROVIDERS ∪ AKASH_PROVIDERS_BACKUP`.
- `just_akash/_e2e.py` shared cleanup module: `robust_destroy()` with retry + audit, SIGINT/SIGTERM-safe `install_signal_cleanup()`, tier resolution, provider classification.
- Tests: 109 new (39 deploy state-machine + 70 cleanup helpers + e2e wiring); full suite at 653 tests, `just_akash/deploy.py` and `just_akash/_e2e.py` both at 100% line coverage.

### Changed
- **BME migration**: bid-price denom defaults from `uakt` (legacy) to `uact`. Bid responses pass through whatever denom they carry; only display fallbacks for malformed bids changed.
- SDL pricing ceiling raised from 1000 → 10000 uact (more provider headroom; cheapest-wins still applies).
- README: env-var table documents `AKASH_PROVIDERS_BACKUP`; new "Tiered providers" section with state-machine table.
- All three e2e tests now wrap post-deploy work in `try/finally` (was missing in `test_lifecycle.py` and `test_secrets_e2e.py`); `robust_destroy` retries up to 3× and audits via `just list`.

### Fixed
- **Cleanup leak: substring DSEQ collision** in audit — `dseq="123"` falsely flagged a different deployment `"12345"` as lingering. Fixed via word-boundary regex (`_dseq_in_list_output`).
- **Cleanup leak: `retries < 0` silently skipped destroy** but returned True from audit — caller saw "success", deployment lived on. Fixed via `retries = max(retries, 0)`.
- **Cleanup leak: double `install_signal_cleanup` orphaned the first dseq_ref** — second call replaced the SIGINT handler, first deployment leaked on signal. Fixed via module-level `_REGISTERED_DSEQ_REFS` registry; signal handler iterates all registered refs; `signal.signal()` invoked exactly once.
- **Cleanup leak: signal-handler reentrancy** — impatient double-Ctrl-C re-iterated the registry, multiplying destroy calls per ref. Fixed via `_HANDLER_RUNNING` guard with try/finally.
- `_log_bid_table()` now safely handles non-dict bid entries when tier-tagging.

### Acknowledgements
Hardened against 4 real cleanup-leak bugs surfaced by the adversarial /nf:harden loop.

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
