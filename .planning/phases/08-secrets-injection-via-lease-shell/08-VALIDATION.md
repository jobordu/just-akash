---
phase: 8
slug: secrets-injection-via-lease-shell
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-19
---

# Phase 8 — Validation Strategy

> Template created by `/nf:plan-phase 8` (step 5.5) after research.
> Populated by `/nf:plan-phase 8` (step 11.5) after plan-checker approval.
> Governs feedback sampling during `/nf:execute-phase 8`.

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
| 08-01-01 | 01 | 1 | INJS-01, INJS-02 | unit | `pytest tests/test_transport_inject.py -v` | ❌ W0 (created in task) | ⬜ pending |
| 08-01-02 | 01 | 1 | INJS-01, INJS-02 | unit+integration | `pytest tests/test_transport_inject.py tests/test_transport.py tests/test_transport_cli_integration.py --tb=short` | ✅ | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

Existing infrastructure covers all phase requirements — no Wave 0 test tasks needed.

Note: `tests/test_transport_inject.py` is created in Task 1 (RED phase of TDD), not as a separate Wave 0 step. The test file is the scaffolding; Task 2 (GREEN) implements against it.

---

## Manual-Only Verifications

All phase behaviors have automated verification coverage.

INJS-02 (no secret in stdout) is verified by `test_inject_secret_value_not_in_exec_command_plaintext` which asserts the raw secret string never appears in any `exec()` command argument.

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

Updated during `/nf:execute-phase 8`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 1 | 2 | `pytest --tb=short` | TBD | TBD | ⬜ pending |

**Phase validation complete:** pending
