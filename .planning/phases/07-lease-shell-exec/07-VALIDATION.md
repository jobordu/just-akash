---
phase: 7
slug: lease-shell-exec
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-18
---

# Phase 7 — Validation Strategy

> Template created by `/nf:plan-phase 7` (step 5.5) after research.
> Populated by `/nf:plan-phase 7` (step 11.5) after plan-checker approval.
> Governs feedback sampling during `/nf:execute-phase 7`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (uv run pytest) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_lease_shell_exec.py -x --tb=short` |
| **Full suite command** | `uv run pytest --tb=short -q` |
| **Estimated runtime** | ~15 seconds (full suite) |
| **CI pipeline** | none — local only |

---

## Nyquist Sampling Rate

> The minimum feedback frequency required to reliably catch errors in this phase.

- **After every task commit:** Run `uv run pytest tests/test_lease_shell_exec.py -x --tb=short`
- **After every plan wave:** Run `uv run pytest --tb=short -q`
- **Before `/nf:verify-work`:** Full suite must be green
- **Maximum acceptable task feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | LSHL-02, EXEC-01, EXEC-02, EXEC-03 | unit | `uv run pytest tests/test_lease_shell_exec.py -x --tb=short` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | LSHL-02, EXEC-01, EXEC-02, EXEC-03 | unit | `uv run pytest tests/test_lease_shell_exec.py -x --tb=short` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 2 | LSHL-03 | unit | `uv run pytest tests/test_lease_shell_exec.py -x --tb=short` | ✅ after 07-01 | ⬜ pending |
| 07-02-02 | 02 | 2 | LSHL-03 | unit | `uv run pytest --tb=short -q` | ✅ after 07-01 | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

Existing infrastructure covers all phase requirements — no Wave 0 test tasks needed.

*Note: Plan 07-01 Task 2 creates `tests/test_lease_shell_exec.py` with FakeWebSocket helper as part of Wave 1. Tests run after implementation task in the same wave.*

---

## Manual-Only Verifications

> Behaviors that genuinely cannot be automated, with justification.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live provider WebSocket exec | EXEC-01 | Requires running Akash deployment with valid AKASH_API_KEY | Run `just-akash exec --transport lease-shell --dseq <N> 'echo hello'` against real deployment |
| Token refresh on 30s JWT expiry | LSHL-03 | Server may cap TTL at 30s; requires live timing | Run `just-akash exec --transport lease-shell --dseq <N> 'sleep 60'` and observe no crash |

*Core behaviors have automated unit test coverage via FakeWebSocket mock. Manual verification supplements for live integration.*

---

## Validation Sign-Off

Updated by `nf-plan-checker` when plans are approved on 2026-04-18:

- [x] All tasks have `<automated>` verify commands or Wave 0 dependencies
- [x] No 3 consecutive implementation tasks without automated verify (sampling continuity)
- [x] Wave 0 test files covered by 07-01 Task 2 (same wave as implementation)
- [x] No watch-mode flags in any automated command
- [x] Feedback latency per task: < 30s ✅
- [x] `nyquist_compliant: true` set in frontmatter

**Plan-checker approval:** approved on 2026-04-18

---

## Execution Tracking

Updated during `/nf:execute-phase 7`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 1 | 2 | `uv run pytest tests/test_lease_shell_exec.py -x --tb=short` | — | — | ⬜ pending |
| 2 | 2 | `uv run pytest --tb=short -q` | — | — | ⬜ pending |

**Phase validation complete:** pending
