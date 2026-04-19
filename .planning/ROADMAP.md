# Roadmap: just-akash

## Milestones

- ✅ **v1.4 Secrets, Exec & Unified CLI** - Phases 1-5 (shipped 2026-04-18)
- 🚧 **v1.5 Lease-Shell Transport** - Phases 6-11 (in progress)

## Phases

<details>
<summary>✅ v1.4 Secrets, Exec & Unified CLI (Phases 1-5) - SHIPPED 2026-04-18</summary>

Phases 1-5 delivered secrets injection via SSH, remote exec, SDL env injection, configurable Console API URL, and a unified CLI. 357 tests at 69% coverage shipped.

</details>

### 🚧 v1.5 Lease-Shell Transport (In Progress)

**Milestone Goal:** Replace SSH as the default shell transport with Akash's native lease-shell WebSocket mechanism across exec, inject, and connect commands.

- [ ] **Phase 6: Transport Abstraction Foundation** - Reverse-engineer lease-shell protocol and establish transport abstraction layer
- [ ] **Phase 7: Lease-Shell Exec** - Non-interactive command execution over lease-shell with exit code and output streaming
- [ ] **Phase 8: Secrets Injection via Lease-Shell** - File/secret delivery over lease-shell without SSH or SCP
- [ ] **Phase 9: Interactive Shell** - Full TTY shell session over lease-shell with signal handling and terminal cleanup
- [ ] **Phase 10: Default Transport Switch and Fallback** - Lease-shell becomes default; SSH opt-in; auto-fallback when lease-shell unavailable
- [ ] **Phase 11: Test Coverage** - E2E recipe and unit tests for the transport layer

## Phase Details

### Phase 6: Transport Abstraction Foundation
**Goal**: The lease-shell protocol is understood and a clean transport abstraction layer exists; all existing commands continue to work unchanged through SSHTransport
**Depends on**: Nothing (first phase of v1.5)
**Requirements**: LSHL-01, TRNS-02
**Success Criteria** (what must be TRUE):
  1. Running `just exec` or `just connect` with no new flags produces the same behavior as v1.4 (SSH transport, zero regression)
  2. `--transport ssh` flag is accepted on exec, inject, and connect commands and routes to SSH transport
  3. The lease-shell WebSocket endpoint URL, auth header format, and message frame schema are documented in a protocol note derived from console.akash.network traffic inspection
  4. `just_akash/transport/` package exists with a Transport base class, SSHTransport implementation, and LeaseShellTransport stub
**Plans**: TBD

### Phase 7: Lease-Shell Exec
**Goal**: Users can run remote commands over lease-shell with full output streaming and exit code propagation; auth token refresh keeps long commands alive
**Depends on**: Phase 6
**Requirements**: LSHL-02, LSHL-03, EXEC-01, EXEC-02, EXEC-03
**Success Criteria** (what must be TRUE):
  1. `just exec CMD` (or `just-akash exec CMD`) runs the command on the remote container over the WebSocket transport and prints stdout/stderr locally
  2. The CLI exits with the same exit code as the remote command (non-zero exits propagate)
  3. Both stdout and stderr from the remote process appear in local terminal output in real time
  4. When a WebSocket session token expires mid-command, the CLI silently re-authenticates and the command continues rather than crashing
  5. Authentication uses only the existing AKASH_API_KEY — no SSH key required
**Plans**: TBD

### Phase 8: Secrets Injection via Lease-Shell
**Goal**: Users can inject secrets into a running container over lease-shell with no SSH or SCP dependency
**Depends on**: Phase 7
**Requirements**: INJS-01, INJS-02
**Success Criteria** (what must be TRUE):
  1. `just inject` (or `just-akash inject`) writes secrets to the remote container without requiring SSH keys or port 22 to be open
  2. Injected secret values do not appear in SDL, deployment logs, or CLI stdout during the inject operation
**Plans**: TBD

### Phase 9: Interactive Shell
**Goal**: Users can open a full interactive TTY shell session over lease-shell; the terminal is always restored cleanly regardless of how the session ends
**Depends on**: Phase 7
**Requirements**: SHLL-01, SHLL-02, SHLL-03, SHLL-04
**Success Criteria** (what must be TRUE):
  1. `just connect` (or `just-akash connect`) opens an interactive shell session in the remote container over lease-shell with a working TTY
  2. The remote session receives the correct terminal dimensions (rows and columns) on connect
  3. Pressing Ctrl+C inside the shell forwards the interrupt to the remote process rather than terminating the local CLI
  4. After the session ends — whether by normal exit, crash, signal, or network disconnect — the local terminal is fully restored to cooked mode and usable without running `reset`
**Plans**: TBD

### Phase 10: Default Transport Switch and Fallback
**Goal**: Lease-shell is the default transport for all shell-dependent commands; SSH remains available via flag; the CLI falls back gracefully when lease-shell is not available
**Depends on**: Phases 7, 8, 9
**Requirements**: TRNS-01, TRNS-03
**Success Criteria** (what must be TRUE):
  1. Running `just exec`, `just inject`, or `just connect` with no transport flag uses lease-shell by default — no SSH key or port 22 required
  2. When lease-shell is unavailable on a deployment (missing lease or unsupported provider), the CLI automatically falls back to SSH and logs a notice to the user
  3. `--transport ssh` on any shell command forces SSH transport and bypasses lease-shell entirely
**Plans**: TBD

### Phase 11: Test Coverage
**Goal**: The lease-shell transport has E2E validation against a real Akash deployment and isolated unit tests with a mocked WebSocket
**Depends on**: Phases 6-10
**Requirements**: TEST-01, TEST-02
**Success Criteria** (what must be TRUE):
  1. `just test-shell` deploys an instance, runs exec, inject, and connect via lease-shell, and tears the deployment down — passing green from a clean environment
  2. Unit tests for the transport layer run without a network connection by using a mocked WebSocket, and cover normal operation, token refresh, and connection error paths
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 6. Transport Abstraction Foundation | 0/TBD | Not started | - |
| 7. Lease-Shell Exec | 0/TBD | Not started | - |
| 8. Secrets Injection via Lease-Shell | 0/TBD | Not started | - |
| 9. Interactive Shell | 0/TBD | Not started | - |
| 10. Default Transport Switch and Fallback | 0/TBD | Not started | - |
| 11. Test Coverage | 0/TBD | Not started | - |
