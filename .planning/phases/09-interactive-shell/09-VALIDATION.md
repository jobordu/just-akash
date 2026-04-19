---
phase: 9
slug: interactive-shell
status: draft
nyquist_compliant: false
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
| 09-01-01 | 01 | 1 | SHLL-01, SHLL-02, SHLL-03, SHLL-04 | unit | `pytest tests/test_interactive_shell.py -v` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | SHLL-01, SHLL-02, SHLL-03, SHLL-04 | unit | `pytest tests/test_interactive_shell.py --tb=short` | ✅ | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

- [ ] `tests/test_interactive_shell.py` — stubs/failing tests for SHLL-01 through SHLL-04 (TTY setup, terminal dimensions, Ctrl+C forwarding, terminal restore)

---

## Manual-Only Verifications

> Behaviors that genuinely cannot be automated, with justification.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Interactive TTY session looks/feels correct | SHLL-01 | Live terminal session with full duplex I/O cannot be fully automated in CI | Run `just connect --transport lease-shell` against a real deployment; verify shell prompt appears and commands execute |
| Terminal restore after Ctrl+D exit | SHLL-04 | Requires real TTY — CI runs with non-TTY stdin | After session ends, verify `echo hello` works without running `reset` |

---

## Validation Sign-Off

Updated by `nf-plan-checker` when plans are approved:

- [ ] All tasks have `<automated>` verify commands or Wave 0 dependencies
- [ ] No 3 consecutive implementation tasks without automated verify (sampling continuity)
- [ ] Wave 0 test files cover all MISSING references
- [ ] No watch-mode flags in any automated command
- [ ] Feedback latency per task: < 30s ✅
- [ ] `nyquist_compliant: true` set in frontmatter

**Plan-checker approval:** {pending / approved on YYYY-MM-DD}

---

## Execution Tracking

Updated during `/nf:execute-phase 9`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 0 | {N} | — | — | — | scaffold |
| 1 | {N} | `pytest --tb=short` | TBD | TBD | ⬜ pending |

**Phase validation complete:** pending
