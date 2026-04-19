---
phase: 11
slug: test-coverage
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-19
---

# Phase 11 — Validation Strategy

> Template created by `/nf:plan-phase 11` (step 5.5) after research.
> Populated by `/nf:plan-phase 11` (step 11.5) after plan-checker approval.
> Governs feedback sampling during `/nf:execute-phase 11`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Pytest |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -x --tb=short` |
| **Full suite command** | `uv run pytest --tb=short` |
| **Estimated runtime** | ~30 seconds (unit); 5-10 minutes (E2E) |
| **CI pipeline** | .github/workflows/test.yml — exists |

---

## Nyquist Sampling Rate

> The minimum feedback frequency required to reliably catch errors in this phase.

- **After every task commit:** Run `uv run pytest -x --tb=short`
- **After every plan wave:** Run `uv run pytest --tb=short`
- **Before `/nf:verify-work`:** Full suite must be green
- **Maximum acceptable task feedback latency:** 30 seconds

---

## Per-Task Verification Map

*(Populated after plan-checker approval)*

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 0 | TEST-02 | unit (stubs) | `uv run pytest tests/test_transport_errors.py -v` | ❌ W0 (created in task) | ⬜ pending |
| TBD | TBD | 1 | TEST-02 | unit | `uv run pytest tests/ -k "transport" --cov=just_akash.transport` | ✅ after W0 | ⬜ pending |
| TBD | TBD | 2 | TEST-01 | integration/E2E | `just test-shell` (manual/optional in CI) | ❌ (created in task) | ⬜ pending |

*Status values: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test scaffolding committed BEFORE any implementation task. Executor runs Wave 0 first.

- [ ] `tests/test_transport_errors.py` — 8+ genuine failing tests for token expiry (close codes 4001/4003, "expired"/"unauthorized" reason strings), connection error paths, frame 103 (error frame) handling
- [ ] Tests call real `LeaseShellTransport` methods with `FakeWebSocket` and fail RED because they test edge cases not yet explicitly exercised

All Wave 0 tests must be genuine failing assertions (not `pytest.fail()` stubs) that become green once implementation is verified.

---

## Manual-Only Verifications

> Behaviors that genuinely cannot be automated, with justification.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `just test-shell` E2E against live Akash deployment | TEST-01 | Requires real Akash account, AKASH_API_KEY, AKASH_PROVIDERS, and 5-10 min runtime — not suitable for CI | Set env vars, run `just test-shell`, verify "All steps passed" output and deployment destroyed |
| Interactive connect() via lease-shell in real terminal | TEST-01 (partial) | Full-duplex TTY session cannot be verified in non-TTY CI environment | Run `just connect` against test deployment, verify shell prompt, Ctrl+C forwarding, terminal restored after exit |

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

Updated during `/nf:execute-phase 11`:

| Wave | Tasks | Tests Run | Pass | Fail | Sampling Status |
|------|-------|-----------|------|------|-----------------|
| 0 | TBD | `uv run pytest tests/test_transport_errors.py -v` | TBD | TBD | scaffold |
| 1 | TBD | `uv run pytest tests/ -k "transport" --tb=short` | TBD | TBD | ⬜ pending |
| 2 | TBD | `just test-shell` (manual) | TBD | TBD | ⬜ pending |

**Phase validation complete:** pending
