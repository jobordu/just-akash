---
plan: 06-02
phase: 06-transport-abstraction-foundation
status: complete
commit: 4f234e0
---

# Plan 06-02 Summary: CLI Transport Wiring + PROTOCOL.md

## What was done

**Task 1 — `--transport` flag wired into CLI** (completed in prior session, commit `0dfcfe3`):
- Added `--transport {ssh,lease-shell}` to `exec_p`, `inject_p`, `connect_p` subparsers (default=`ssh`)
- SSH path is byte-for-byte identical to v1.4 behavior (zero regression)
- `lease-shell` branch calls `make_transport("lease-shell", ...)` → `transport.prepare()` → raises `NotImplementedError` in Phase 6 → caught as `RuntimeError` → `sys.exit(1)`

**Task 2 — `docs/PROTOCOL.md`** (research sourced from `akash-network/provider` Go source):
- Endpoint: `wss://{provider_host}:{port}/lease/{dseq}/{gseq}/{oseq}/shell`
- Auth: `Authorization: Bearer <JWT_TOKEN>` with `shell` scope
- Binary frame codes 100–105 (stdout/stderr/result/failure/stdin/resize)
- Query params: `cmd`, `tty`, `service`, `stdin`, `podIndex`
- Connection lifecycle diagrams (non-interactive exec + interactive shell)
- Python implementation notes with `websockets>=16.0`
- Provider address discovery from Console API `leases[0].provider.hostUri`
- TLS/mTLS notes and unconfirmed fields section

**Task 3 — Integration tests + full regression** (commit `4f234e0`):
- `tests/test_transport_cli_integration.py`: 33 tests across 7 classes
- Full suite: **406 passed, 0 failed**

## Verification results

| SC | Check | Result |
|----|-------|--------|
| SC-1 | Zero regression — 406 tests pass | ✅ PASS |
| SC-2 | `--transport {ssh,lease-shell}` on exec/inject/connect | ✅ PASS |
| SC-3 | `docs/PROTOCOL.md` has ≥4 `##` sections | ✅ PASS (7 sections) |
| SC-4 | `from just_akash.transport import Transport, SSHTransport, LeaseShellTransport, make_transport` | ✅ PASS |

## Artifacts

- `just_akash/cli.py` — `--transport` flag, SSHTransport routing (commit `0dfcfe3`)
- `docs/PROTOCOL.md` — lease-shell WebSocket protocol reference (commit `4f234e0`)
- `tests/test_transport_cli_integration.py` — 33 integration tests (commit `4f234e0`)

## Phase 7 unlock

`PROTOCOL.md` provides the complete protocol specification for Phase 7 (`LeaseShellTransport` implementation):
- WebSocket endpoint construction
- JWT bearer auth header
- Binary frame encoding/decoding (codes 100–105)
- Provider address discovery from deployment data
- Graceful close sequence
