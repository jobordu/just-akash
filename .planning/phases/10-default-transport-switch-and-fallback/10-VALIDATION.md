---
phase: 10
slug: default-transport-switch-and-fallback
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-19
---

# Phase 10 — Validation Strategy

> Template created by `/nf:plan-phase 10` (step 5.5) after research.
> Populated by `/nf:plan-phase 10` (step 11.5) after plan-checker approval.
> Governs feedback sampling during `/nf:execute-phase 10`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest -x --tb=short` |
| **Full suite command** | `pytest --tb=short -q` |
| **Estimated runtime** | ~30 seconds |
| **CI pipeline** | .github/workflows/test.yml — exists |

---

## Nyquist Sampling Rate

> The minimum feedback frequency required to reliably catch errors in this phase.

- **After every task commit:** Run `pytest -x --tb=short`
- **After every plan wave:** Run `pytest --tb=short -q`
- **Before `/nf:verify-work`:** Full suite must be green
- **Maximum acceptable task feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | TRNS-01, TRNS-03 | unit | `pytest tests/test_default_transport.py --tb=short -q` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | TRNS-01, TRNS-03 | unit | `pytest tests/test_default_transport.py --tb=short -q` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 2 | TRNS-01 | unit | `pytest tests/test_default_transport.py::TestDefaultTransportArgparse -v` | ✅ W0 | ⬜ pending |
| 10-02-02 | 02 | 2 | TRNS-01, TRNS-03 | unit | `pytest tests/test_default_transport.py --tb=short -q` | ✅ W0 | ⬜ pending |
| 10-02-03 | 02 | 2 | TRNS-01, TRNS-03 | integration | `pytest tests/test_transport_cli_integration.py --tb=short -q` | ✅ | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

- [ ] `tests/test_default_transport.py` — stubs for TRNS-01, TRNS-03 (9 tests: 8 RED before implementation, 1 GREEN for --transport ssh bypass)

---

## Manual-Only Verifications

All phase behaviors have automated verification coverage.

---

## Validation Sign-Off

Updated by `nf-plan-checker` when plans are approved:

- [x] All tasks have `<verify>` commands or Wave 0 dependencies
- [x] No 3 consecutive implementation tasks without automated verify (sampling continuity)
- [x] Wave 0 test files cover all MISSING references (test_default_transport.py created in Plan 10-01)
- [x] No watch-mode flags in any automated command
- [x] Feedback latency per task: < 30s ✅
- [x] `nyquist_compliant: true` set in frontmatter

**Plan-checker approval:** approved on 2026-04-19

---

## Execution Tracking

Updated during `/nf:execute-phase 10`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 0 | 2 | — | — | — | scaffold |
| 1 | 2 | `pytest tests/test_default_transport.py` | — | — | ⬜ pending |
| 2 | 3 | `pytest --tb=short -q` | — | — | ⬜ pending |

**Phase validation complete:** pending
