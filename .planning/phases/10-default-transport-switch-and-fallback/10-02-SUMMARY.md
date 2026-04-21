---
phase: 10-default-transport-switch-and-fallback
plan: "02"
subsystem: transport, cli
tags: [lease-shell, ssh, fallback, transport-default, argparse]

requires:
  - phase: 10-01
    provides: "Initial transport abstraction setup"

provides:
  - Lease-shell as default transport for connect/exec/inject commands
  - Automatic fallback to SSH when lease-shell validation fails
  - Updated help text reflecting new v1.5 defaults
  - Removed outdated NO_SSH_MSG claims about lease-shell unsupport

affects: [phase-11-tls-verification, user-documentation, deployment-guides]

tech-stack:
  added: []
  patterns:
    - "Fallback via transport.validate() pattern"
    - "Graceful degradation on missing provider hostUri"

key-files:
  created: []
  modified:
    - just_akash/cli.py
    - tests/test_transport_cli_integration.py

key-decisions:
  - "lease-shell is now the default transport (v1.5 goal)"
  - "Fallback to SSH is automatic when lease-shell validate() returns False"
  - "Users can force SSH with --transport ssh flag (bypasses lease-shell entirely)"

patterns-established:
  - "transport.validate() pattern for checking availability"
  - "Graceful fallback printing notice to stderr"

requirements-completed: [TRNS-01, TRNS-03]

duration: 1min
completed: 2026-04-19
---

# Phase 10 Plan 02: Default Transport Switch and Fallback Summary

**Lease-shell as default transport with automatic SSH fallback when unavailable**

## Performance

- **Duration:** 1 min
- **Started:** 2026-04-19T18:29:31Z
- **Completed:** 2026-04-19T18:29:50Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- All three shell commands (connect, exec, inject) now default to lease-shell transport
- Implemented validate()-based fallback: when lease-shell is unavailable (no active lease or provider hostUri missing), CLI automatically falls back to SSH with user notice
- Updated NO_SSH_MSG to remove outdated claim that "Akash Console API does not support lease-shell"
- Updated help text to reflect new defaults and remove "requires SSH in SDL" language
- --transport ssh flag still forces SSH entirely (bypasses lease-shell validation)

## Task Commits

1. **Task 1-3 Combined: Default transport switch and fallback implementation** - `05b7c05` (feat)

Note: Tasks 1-3 were completed as a single cohesive unit with the cli.py implementation and test updates.

**Plan metadata:** Included in task commit

## Files Created/Modified

- `just_akash/cli.py` - Switch default to lease-shell, add validate()-based fallback, clean NO_SSH_MSG
- `tests/test_transport_cli_integration.py` - Updated lease-shell test to expect Phase 7+ behavior

## Decisions Made

- **Default transport**: lease-shell (v1.5 requirement) - Users get better UX by default without SSH setup
- **Fallback strategy**: Automatic validation check with user-facing notice - Maintains CLI reliability
- **SSH override**: --transport ssh bypasses lease-shell entirely - Gives users explicit control
- **Messaging**: stderr notice when falling back - Informs users why SSH is being used

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all tests pass, no blocking issues.

## Test Results

All 8 tests in `test_default_transport.py`:
- `TestDefaultTransportArgparse` - 3 tests: PASSED
- `TestFallbackToSSH` - 3 tests: PASSED  
- `TestNoSshMsg` - 1 test: PASSED
- `TestExplicitSSHTransport` - 1 test: PASSED

Integration tests in `test_transport_cli_integration.py`: All passing

Full pytest suite: 0 failures, exit code 0

## Verification Checklist

✓ `default="ssh"` → 0 matches (completely replaced)
✓ `default="lease-shell"` → 3 matches (connect, exec, inject)
✓ "does not support lease-shell" → 0 matches (removed from NO_SSH_MSG)
✓ `transport.validate()` calls → 3 matches (one per command handler)
✓ "Falling back to SSH" → 3 matches (one per command handler)
✓ All tests in test_default_transport.py PASS
✓ Full pytest suite: 0 failures

## User Setup Required

None - no external service configuration required. This is a pure CLI/logic change.

## Next Phase Readiness

Ready for Phase 11 (TLS verification) - The default transport switching is complete and all fallback logic is in place. v1.5 defaults are now functional.

---
*Phase: 10-default-transport-switch-and-fallback*
*Plan: 02*
*Completed: 2026-04-19*
