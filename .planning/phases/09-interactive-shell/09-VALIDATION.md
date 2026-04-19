---
phase: 9
slug: interactive-shell
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-19
---

# Phase 9 — Validation Strategy

> Template created by `/nf:plan-phase 9` (step 5.5) after research.
> Populated by `/nf:plan-phase 9` (step 11.5) after plan-checker approval.
> Governs feedback sampling during `/nf:execute-phase 9`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Pytest |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest -x --tb=short` |
| **Full suite command** | `pytest --tb=short` |
| **Estimated runtime** | ~30 seconds |
| **CI pipeline** | .github/workflows/test.yml — exists |

---

## Nyquist Sampling Rate

> The minimum feedback frequency required to reliably catch errors in this phase.

- **After every task commit:** Run `pytest -x --tb=short`
- **After every plan wave:** Run `pytest --tb=short`
- **Before `/nf:verify-work`:** Full suite must be green
- **Maximum acceptable task feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 0 | SHLL-01, SHLL-02, SHLL-03, SHLL-04 | unit (stubs) | `pytest tests/test_interactive_shell.py --tb=short -q` | ❌ W0 (created in task) | ⬜ pending |
| 09-02-01 | 02 | 1 | SHLL-01, SHLL-04 | unit | `pytest tests/test_interactive_shell.py -k "tty or restore" -v` | ✅ after W0 | ⬜ pending |
| 09-02-02 | 02 | 1 | SHLL-02, SHLL-03 | unit | `pytest tests/test_interactive_shell.py -k "resize or sigint or ctrl" -v` | ✅ after W0 | ⬜ pending |
| 09-02-03 | 02 | 1 | SHLL-01, SHLL-02, SHLL-03, SHLL-04 | unit (full) | `pytest tests/test_interactive_shell.py --tb=short` | ✅ after W0 | ⬜ pending |
| 09-03-01 | 03 | 2 | SHLL-01, SHLL-04 | unit | `pytest tests/test_transport.py -k "connect" -v` | ✅ | ⬜ pending |
| 09-03-02 | 03 | 2 | SHLL-01, SHLL-04 | integration | `pytest tests/test_transport_cli_integration.py -k "connect" -v` | ✅ | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

- [ ] `tests/test_interactive_shell.py` — 14 genuine failing tests for SHLL-01 through SHLL-04: TTY setup/guards, terminal dimension frame, Ctrl+C SIGINT forwarding, SIGWINCH resize, I/O loop, terminal restore under all exit conditions

All 14 tests call `LeaseShellTransport.connect()` with patched `termios`/`tty`/`signal`/WebSocket and fail RED because `connect()` raises `NotImplementedError`. Tests are genuine test contracts — not `pytest.fail()` stubs.

---

## Manual-Only Verifications

> Behaviors that genuinely cannot be automated, with justification.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Interactive TTY session looks/feels correct in real terminal | SHLL-01 | Live terminal session with full duplex I/O cannot be fully verified in CI | Run `just connect --transport lease-shell` against a real deployment; verify shell prompt appears, commands execute, arrow keys work |
| Terminal is usable after session ends (no `reset` needed) | SHLL-04 | Requires real TTY — CI runs with non-TTY stdin | After session ends normally (Ctrl+D), verify `echo hello` works in the local terminal without running `reset` |

---

## Validation Sign-Off

Updated by `nf-plan-checker` when plans are approved:

- [x] All tasks have `<automated>` verify commands or Wave 0 dependencies
- [x] No 3 consecutive implementation tasks without automated verify (sampling continuity)
- [x] Wave 0 test files cover all MISSING references
- [x] No watch-mode flags in any automated command
- [x] Feedback latency per task: < 30s ✅
- [x] `nyquist_compliant: true` set in frontmatter

**Plan-checker approval:** approved on 2026-04-19

---

## Execution Tracking

Updated during `/nf:execute-phase 9`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 0 | 1 | `pytest tests/test_interactive_shell.py -q` | TBD | TBD | scaffold |
| 1 | 3 | `pytest --tb=short` | TBD | TBD | ⬜ pending |
| 2 | 2 | `pytest --tb=short` | TBD | TBD | ⬜ pending |

**Phase validation complete:** pending
