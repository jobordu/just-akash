---
phase: 6
slug: transport-abstraction-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 6 — Validation Strategy

> Template created by `/nf:plan-phase 6` (step 5.5) after research.
> Populated by `/nf:plan-phase 6` (step 11.5) after plan-checker approval.
> Governs feedback sampling during `/nf:execute-phase 6`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Pytest |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest -x --tb=short` |
| **Full suite command** | `pytest --tb=short` |
| **Estimated runtime** | ~30 seconds |
| **CI pipeline** | `.github/workflows/` — check if exists |

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
| 06-01-01 | 01 | 0 | LSHL-01, TRNS-02 | unit | `pytest tests/test_transport.py -x --tb=short` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | TRNS-02 | unit | `pytest tests/test_transport.py::TestSSHTransport -x --tb=short` | ✅ | ⬜ pending |
| 06-01-03 | 01 | 1 | TRNS-02 | unit | `pytest tests/test_transport.py::TestLeaseShellTransportStub -x --tb=short` | ✅ | ⬜ pending |
| 06-01-04 | 01 | 2 | TRNS-02 | integration | `pytest tests/test_cli.py -x --tb=short` | ✅ | ⬜ pending |
| 06-01-05 | 01 | 2 | LSHL-01 | manual | Review `docs/PROTOCOL.md` for endpoint, auth, frame schema | N/A | ⬜ pending |
| 06-01-06 | 01 | 2 | TRNS-02 | smoke | `pytest --tb=short` (full suite — zero regressions) | ✅ | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

- [ ] `tests/test_transport.py` — stubs for Transport ABC, SSHTransport, LeaseShellTransport stub; test that `LeaseShellTransport.exec()` raises `NotImplementedError`

*Wave 0 creates the test file with stubs so the test runner can collect it before implementation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lease-shell WebSocket endpoint, auth headers, frame schema | LSHL-01 | Requires live browser traffic inspection of console.akash.network | Open Chrome DevTools → Network → WS tab; open a shell on a deployment; document URL, headers, message format in `docs/PROTOCOL.md` |

---

## Validation Sign-Off

Updated by `nf-plan-checker` when plans are approved:

- [ ] All tasks have `<automated>` verify commands or Wave 0 dependencies
- [ ] No 3 consecutive implementation tasks without automated verify (sampling continuity)
- [ ] Wave 0 test files cover all MISSING references
- [ ] No watch-mode flags in any automated command
- [ ] Feedback latency per task: < 30s ✅
- [ ] `nyquist_compliant: true` set in frontmatter

**Plan-checker approval:** pending

---

## Execution Tracking

Updated during `/nf:execute-phase 6`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 0 | TBD | — | — | — | scaffold |
| 1 | TBD | `pytest tests/test_transport.py -x --tb=short` | — | — | ⬜ pending |
| 2 | TBD | `pytest --tb=short` | — | — | ⬜ pending |

**Phase validation complete:** pending
