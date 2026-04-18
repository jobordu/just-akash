# Requirements: just-akash

**Defined:** 2026-04-18
**Core Value:** Fastest path from "I want something running on Akash" to a live, remotely-accessible instance — single command, no manual portal steps.

## Milestone v1.5 Requirements

### Transport Abstraction

- [ ] **TRNS-01**: User can run exec, inject, and connect commands without requiring SSH keys — lease-shell is the default transport
- [ ] **TRNS-02**: User can opt into SSH transport via `--transport ssh` flag on exec, inject, and connect commands
- [ ] **TRNS-03**: CLI automatically falls back to SSH when lease-shell is unavailable on a deployment

### Lease-Shell Protocol

- [ ] **LSHL-01**: Protocol implementation is derived from reverse-engineered console.akash.network WebSocket handshake (endpoint URL, auth headers, frame format)
- [ ] **LSHL-02**: Lease-shell WebSocket connection authenticates using the existing AKASH_API_KEY
- [ ] **LSHL-03**: Token expiry during long sessions triggers automatic re-authentication without dropping the user session

### Exec

- [ ] **EXEC-01**: User can execute a remote command via `just exec` / `just-akash exec` using lease-shell
- [ ] **EXEC-02**: Remote command exit code is propagated as the CLI exit code
- [ ] **EXEC-03**: Remote stdout and stderr are streamed to local output

### Inject

- [ ] **INJS-01**: User can inject secrets via `just inject` / `just-akash inject` over lease-shell (no SSH/SCP dependency)
- [ ] **INJS-02**: Injected secrets are written to the remote container without exposure in SDL or logs

### Connect / Shell

- [ ] **SHLL-01**: User can open an interactive TTY session via `just connect` / `just-akash connect` over lease-shell
- [ ] **SHLL-02**: Terminal size (rows × columns) is sent to the remote session on connect
- [ ] **SHLL-03**: Ctrl+C is correctly forwarded to the remote process (not swallowed by the client)
- [ ] **SHLL-04**: Terminal is restored to cooked mode on exit — including crash, signal, or network disconnect

### Testing

- [ ] **TEST-01**: `just test-shell` E2E recipe deploys an instance, exercises exec/inject/connect via lease-shell, and tears down
- [ ] **TEST-02**: Unit tests cover the transport layer with a mocked WebSocket

## Future Requirements (v1.6+)

### Terminal

- **TERM-01**: Terminal resize (SIGWINCH) events propagated to remote session
- **TERM-02**: Windows interactive shell support (currently blocked by pexpect POSIX limitation)

### Advanced Transport

- **ADVT-01**: Connection pooling / persistent lease-shell sessions
- **ADVT-02**: Streaming log delivery via WebSocket push

## Out of Scope

| Feature | Reason |
|---------|--------|
| Windows interactive shell | pexpect is POSIX-only; SSH `--transport ssh` fallback available |
| SIGWINCH terminal resize | Nice-to-have, deferred to v1.6 |
| Browser-based console integration | Separate v2.0 goal |
| Connection pooling | Premature for CLI use-case |
| gRPC/protobuf protocol | Not yet deployed in Akash Console (AEP-37 roadmap) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TRNS-01 | — | Pending |
| TRNS-02 | — | Pending |
| TRNS-03 | — | Pending |
| LSHL-01 | — | Pending |
| LSHL-02 | — | Pending |
| LSHL-03 | — | Pending |
| EXEC-01 | — | Pending |
| EXEC-02 | — | Pending |
| EXEC-03 | — | Pending |
| INJS-01 | — | Pending |
| INJS-02 | — | Pending |
| SHLL-01 | — | Pending |
| SHLL-02 | — | Pending |
| SHLL-03 | — | Pending |
| SHLL-04 | — | Pending |
| TEST-01 | — | Pending |
| TEST-02 | — | Pending |

**Coverage:**
- v1.5 requirements: 17 total
- Mapped to phases: 0
- Unmapped: 17 ⚠️ (roadmap pending)

---
*Requirements defined: 2026-04-18*
*Last updated: 2026-04-18 after initial definition*
