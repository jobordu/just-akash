# Project Research Summary

**Project:** just-akash v1.5 (Lease-Shell WebSocket Transport)  
**Domain:** CLI tool adding WebSocket-based shell transport to replace SSH for Akash Network deployment access  
**Researched:** 2026-04-18  
**Confidence:** MEDIUM

## Executive Summary

The v1.5 milestone is a transport abstraction project: replacing SSH as the default shell transport with Akash's native `lease-shell` WebSocket mechanism for `exec`, `inject`, and `connect` commands. This is not a rewrite—the CLI interfaces remain stable, but the delivery mechanism shifts from SSH subprocess calls to async WebSocket I/O. The research confirms this is achievable with three core library additions (`websockets>=16.0`, `pexpect>=4.9.0`, and existing `requests`) and a clean transport abstraction layer.

The recommended approach is phased implementation starting with the abstraction layer (weeks 1-2), then non-interactive `exec` (weeks 3-4), `inject` (week 5), interactive `connect` (week 6), and finally the default switch (week 7). This order mitigates risks by proving each capability in isolation before integrating into a unified default transport system.

The primary risk is token expiry during long sessions (critical pitfall), which requires implementing a token refresh mechanism that survives WebSocket disconnects. Secondary risks include TTY state leakage on unclean exits and connection cleanup races—all addressable with async context managers and explicit close timeouts. The domain is well-understood (WebSocket patterns are standard), but Akash-specific integration details (exact token TTL, endpoint URL format, frame format) need validation during Phase 2.

## Key Findings

### Recommended Stack

The technology stack is conservative and well-supported. Three new dependencies supplement the existing HTTP/REST stack:

**Core additions:**
- **websockets >=16.0** — Async-first WebSocket client, pure Python, RFC 6455/7692 compliant, matches CLI's future concurrency model
- **pexpect >=4.9.0** — PTY emulation for interactive shell, provides pattern matching and terminal signal forwarding
- **Existing requests >=2.33.0** — Unchanged; Console API remains HTTP-based

No gRPC, protobuf, or complex build steps required. WebSocket handshake uses standard HTTPS upgrade (WSS). All dependencies are pure Python (except `ptyprocess` included with `pexpect`), available on PyPI, tested on Python 3.10+.

**Trade-off decision:** `websockets` is async-only, requiring minimal wrapping at CLI boundaries (`asyncio.run()` calls). Alternative `websocket-client>=1.9.0` is sync-friendly but less future-proof. Chose `websockets` for its RFC correctness, C extension acceleration, and alignment with future concurrent deployment operations.

### Expected Features

**Must have (table stakes):**
- Execute remote command (`exec`) over lease-shell
- Inject secrets/files (`inject`) at runtime
- Interactive shell (`connect`/`shell`) with TTY emulation
- Command output capture and exit code propagation
- Ctrl+C signal handling and terminal size sync

**Should have (differentiators):**
- No SSH key management (API key only)
- Decentralized endpoint (provider-hosted WebSocket)
- Audit trail via WebSocket handshake logging
- Per-command timeout isolation (no persistent SSH session)
- Graceful SSH fallback for deployments without lease-shell

**Defer to v1.6+:**
- Terminal size sync (SIGWINCH) — nice-to-have, not blocking
- Browser-based console integration — separate v2.0 goal
- Streaming logs via WebSocket push — requires provider feature
- Windows interactive shell support — pexpect is POSIX-only; SSH fallback available

The feature set is bounded and achievable within v1.5. User stories confirm all must-have features are implementable; no scope creep indicated.

### Architecture Approach

The architecture uses a **transport abstraction pattern** separating SSH and lease-shell implementations behind a common interface. This enables:

1. **Clean separation** — Existing SSH code extracted to `transport/ssh.py`, new WebSocket code in `transport/lease_shell.py`, both implementing `Transport` base class
2. **Backward compatibility** — CLI code updated once, both transports instantiated via factory function; no impact to deployment queries or other modules
3. **Phased rollout** — Each command (`exec`, `inject`, `connect`) can adopt the abstraction independently, de-risking the default switch

**Major components:**
- `Transport` (abstract base) — defines interface (`prepare()`, `exec()`, `inject()`, `connect()`)
- `SSHTransport` — wraps existing SSH subprocess logic, validates port 22
- `LeaseShellTransport` — WebSocket client, handles provider connection and TTY mode
- `cli.py` update — adds `--transport` flag, routes through abstraction, awaits async calls

Data flow is straightforward: CLI resolves deployment, selects transport (explicit flag or auto-detect), calls transport methods, returns to stdout. Interactive shell mode uses bidirectional I/O with proper terminal state management (raw mode, signal handlers, SIGWINCH).

### Critical Pitfalls

Five critical pitfalls identified; top three are implementation-blocking:

1. **Auth token expiry mid-session** — Lease-shell WebSocket tokens expire (typically 15-60 min). Long-running interactive sessions crash when token becomes invalid. Prevention: implement token refresh wrapper that reconnects with new token on failure, warn user if token expiry is imminent. **Phase responsibility:** v1.5-core (basic refresh); v1.5-hardening (monitoring).

2. **TTY raw mode leaking on unclean exit** — If CLI crashes or receives SIGKILL while in interactive mode, raw mode persists and terminal becomes unusable. Prevention: wrap terminal setup in async context manager with signal handlers ensuring `tty.setcooked()` is called even on exception or signal. **Phase responsibility:** v1.5-core (context manager).

3. **Connection teardown race conditions** — WebSocket close handshake may not complete if CLI exits immediately; sockets linger in CLOSE_WAIT state on server, causing descriptor leaks. Prevention: explicit close timeout (5-10 sec), force close if timeout expires, shield from task cancellation. **Phase responsibility:** v1.5-core (context manager with timeout).

4. **Binary frame parsing errors** — Lease-shell sends terminal data as binary frames (ANSI codes, non-UTF-8 sequences). Text-only handling crashes on binary data. Prevention: detect frame type, write bytes directly to `sys.stdout.buffer`, handle encoding errors gracefully with replacement characters. **Phase responsibility:** v1.5-core (unified binary handling).

5. **Interactive vs non-interactive mode detection breakage** — `sys.stdin.isatty()` can be wrong in piped/redirected contexts. Code branches differently by mode, causing silent failures. Prevention: explicit `--mode` flag override, log detected mode, use strict check (all three streams are TTYs). **Phase responsibility:** v1.5-core (mode flag).

## Implications for Roadmap

Research suggests an 8-week phased implementation with clear dependencies. Each phase delivers working functionality and avoids the top pitfalls.

### Phase 1: Transport Abstraction Foundation (Weeks 1-2)

**Rationale:** Establish the abstraction layer before any WebSocket code. Backward compatibility requires refactoring existing SSH logic cleanly; this phase ensures zero behavior change while setting up the infrastructure for both transports.

**Delivers:**
- `just_akash/transport/` package with base `Transport` class
- `SSHTransport` implementation wrapping existing SSH code
- CLI updated to use `SSHTransport` (drop-in replacement)
- All existing tests pass unchanged

**Avoids:** Mixing abstraction refactoring with new WebSocket code (high risk of regression)

**Features addressed:** None yet (backward compat only)

**Research needed:** None; SSH behavior is known

---

### Phase 2: Lease-Shell Non-Interactive Exec (Weeks 3-4)

**Rationale:** Simplest WebSocket feature (no TTY setup), proves the transport works, unblocks later phases. Non-interactive `exec` tests the connection, frame parsing, and exit code handling before tackling complexity of stdin/stdout bidirectionality.

**Delivers:**
- `LeaseShellTransport.prepare()` — provider extraction, URL building, validation
- `LeaseShellTransport.exec()` — command execution, output capture, exit code return
- `--transport lease-shell` flag on `exec` command
- E2E test against real Akash deployment

**Addresses pitfalls:** Pitfall #1 (token refresh) — basic version; Pitfall #4 (binary frame handling) — first real test

**Research needed (blocking for Phase 2):**
- Exact Console API lease-shell WebSocket endpoint URL pattern
- Authentication method (header vs URL param, token format)
- Message format (JSON schema for commands, stdout/stderr/exit frames)
- Provider error responses and timeout behavior

---

### Phase 3: Secrets Injection (Week 5)

**Rationale:** `inject` depends on `exec` (mkdir, chmod operations) but adds complexity: WebSocket TTY mode and stdin delivery. Implement after `exec` is proven stable.

**Delivers:**
- `LeaseShellTransport.inject()` — file creation, secret delivery, permissions
- `--transport lease-shell` flag on `inject` command
- Chunked binary frame support for large files
- E2E test: inject secrets, verify via `exec`

**Avoids:** Pitfalls #3 (cleanup) — minimal interactive I/O

**Research needed:**
- TTY mode stdin delivery mechanism (WebSocket message type? special framing?)
- Frame size limits (chunking strategy for large files)

---

### Phase 4: Interactive Shell (Week 6)

**Rationale:** Most complex phase. Requires bidirectional I/O, TTY state management, signal handling. Implement after simpler `exec`/`inject` are stable.

**Delivers:**
- `LeaseShellTransport.connect()` — interactive shell via WebSocket
- TTY context manager with signal handlers (Pitfall #2 full solution)
- Terminal window resize handling (SIGWINCH)
- Bidirectional stdin/stdout/stderr over WebSocket
- E2E test: interactive commands, manual TTY verification

**Addresses pitfalls:** #2 (TTY cleanup), #3 (connection cleanup), #5 (mode detection)

**Uses:** `pexpect` for terminal emulation, async context managers for cleanup

---

### Phase 5: Default Transport Switch & Fallback (Week 7)

**Rationale:** Only after all three commands are proven over lease-shell should the default switch occur. Fallback logic (try lease-shell, fall back to SSH) requires all code paths to be stable.

**Delivers:**
- CLI default changed to `--transport lease-shell`
- Automatic fallback to SSH if lease-shell unavailable (missing lease, no provider)
- Deprecation path for SSH users (clear docs, `--transport ssh` flag)
- Full lifecycle test: deploy → exec (lease-shell) → inject → connect → destroy

**Avoids:** Pitfall #6 (breaking SSH users) — `--transport` flag available throughout, migration guide provided

**Tests:** Full suite with both transports, SSH fallback verification

---

### Phase 6: Hardening & Edge Cases (Week 8)

**Rationale:** Polish, performance, error handling, and production readiness. Implement after all features work.

**Delivers:**
- Token expiry monitoring and refresh (Pitfall #1 hardening)
- Connection leak detection and monitoring
- Comprehensive adversarial testing (bad deployments, network errors, timeouts)
- Performance benchmarking (WebSocket vs SSH throughput/latency)
- Documentation: transport architecture, debugging tips, migration guide

**Uses:** All stack elements, all architectural components

---

### Phase Ordering Rationale

1. **Abstraction first:** Enables parallel SSH maintenance and WebSocket development; zero risk of regression
2. **Exec first:** Unblocks other phases; simplest to implement and test
3. **Inject next:** Builds on exec; less complex than interactive mode
4. **Interactive last:** Hardest (TTY state, signals); benefits from experience with earlier phases
5. **Default switch late:** Only after all commands proven; fallback logic requires stability
6. **Hardening at end:** Performance, monitoring, edge cases after functionality is solid

**Dependency chain:**
- Phase 2 depends on Phase 1 (abstraction)
- Phase 3 depends on Phase 2 (LeaseShellTransport core)
- Phase 4 depends on Phases 2-3 (proven stability, token refresh pattern)
- Phase 5 depends on Phases 2-4 (all commands working, fallback ready)
- Phase 6 depends on Phases 1-5 (full implementation, testing infrastructure)

---

## Research Flags

### Phases needing deeper research during planning:

- **Phase 2 (Lease-Shell Exec)** — BLOCKING: Exact Console API endpoint URL, authentication method, message format. Requires checking Akash provider-services source or running integration test against real endpoint. Recommend: reserve 2-3 days for endpoint discovery and protocol validation before coding.

- **Phase 3 (Inject)** — TTY mode stdin delivery mechanism not yet specified. May require experimenting with WebSocket tty frame format or alternative approaches (base64-encoded stdin chunks). Recommend: Phase 2 research to overlap, test with real provider in Phase 2.

- **Phase 4 (Interactive Shell)** — Terminal state management across async boundaries. Standard Python patterns exist (`pty` module, `pexpect`), but integration with WebSocket async I/O needs validation. Low risk; well-documented patterns.

### Phases with standard patterns (can skip `/nf:research-phase`):

- **Phase 1 (Abstraction)** — Transport pattern is well-established in industry (e.g., `paramiko` vs `fabric` abstractions). No research needed.

- **Phase 5 (Default Switch)** — Fallback logic is straightforward; no novel concerns.

- **Phase 6 (Hardening)** — Performance tuning and monitoring are standard practices; no research needed (just engineering effort).

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | `websockets`, `pexpect`, `requests` are mature, widely-used libraries with clear documentation. Installation straightforward via PyPI. Versions pinned; no compatibility issues expected. |
| Features | HIGH | Feature list matches Akash lease-shell capabilities (exec, inject, shell all documented). Table stakes vs differentiators clearly scoped. No feature overlap or ambiguity. |
| Architecture | MEDIUM | Transport abstraction pattern is standard; data flow is clear. However, exact Console API endpoint, authentication, and message format not yet validated against real Akash provider. Phase 2 research will confirm. |
| Pitfalls | MEDIUM | Five critical pitfalls identified with prevention patterns documented. Token refresh, TTY state, and connection cleanup are well-understood patterns in Python async community. Akash-specific concerns (token TTL, provider behavior) need validation. |

**Overall confidence:** MEDIUM

Confidence is held at MEDIUM due to Akash-specific integration unknowns (exact endpoint URL, message schema, token refresh API). The general approach (Python WebSocket client, async patterns, transport abstraction) is sound and well-documented. Phase 2 research will elevate confidence to HIGH once real provider integration is tested.

### Gaps to Address

1. **Exact Console API Lease-Shell Endpoint** — Current design assumes `wss://console-api.akash.network/v1/leases/{dseq}/shell`, but this needs confirmation against actual Akash provider or documentation. **Action:** Phase 2 research, contact Akash team if needed.

2. **Token Refresh Mechanism** — How does token refresh work? Does Akash provide a separate refresh endpoint? Does client request new token inline? Are tokens in JWT format (extractable exp claim)? **Action:** Phase 2 research, check Akash Console API spec.

3. **Service Name Detection** — If user doesn't provide `--service`, how should `LeaseShellTransport` determine the service name? Options: parse SDL (expensive), require flag (user burden), query provider (complex). Currently unresolved. **Action:** Phase 2 design decision during research.

4. **Frame Format & Binary Handling** — Does Akash send text frames (JSON) or binary frames (raw bytes)? Current design assumes mixed handling; needs validation. **Action:** Phase 2 integration test.

5. **Performance Implications** — WebSocket throughput vs SSH for large file transfer (`inject`). Any known limitations on frame size? **Action:** Phase 3 benchmarking during Inject implementation.

6. **Windows Interactive Shell** — pexpect is POSIX-only; `connect` won't work on Windows. Mitigation documented (SSH fallback available), but Windows users should have clear error message. **Action:** Phase 4 testing, error message design.

---

## Sources

### Primary (HIGH confidence — verified against official/current documentation)
- [websockets 16.0 PyPI](https://pypi.org/project/websockets/) — Latest library, released Jan 2026
- [pexpect 4.9.0 PyPI](https://pypi.org/project/pexpect/) — PTY control, tested on 3.10+
- [Akash Lease-Shell Documentation](https://docs.akash.network/features/deployment-shell-access) — Feature overview and capabilities
- [Python asyncio Documentation](https://docs.python.org/3/library/asyncio.html) — Context managers, signal handling, async patterns

### Secondary (MEDIUM confidence — widely-used patterns, community consensus)
- [websockets Library Documentation](https://websockets.readthedocs.io/) — Best practices, error handling, async patterns
- [Python TTY & Terminal Control](https://docs.python.org/3/library/tty.html) — Signal handling, raw mode management
- [Transport Pattern in Python](https://github.com/websocket-client/websocket-client) — Reference implementations in similar libraries
- [Async Context Managers](https://medium.com/@hitorunajp/asynchronous-context-managers-f1c33d38c9e3) — Cleanup patterns and pitfalls

### Tertiary (MEDIUM confidence — specific to Akash, needs validation in Phase 2)
- [Akash Console API v1 OAS 3.0](https://console-api.akash.network/v1/swagger) — API documentation (endpoint details to be verified)
- [Akash Provider Console API GitHub](https://github.com/akash-network/provider-console-api) — Source reference for WebSocket implementation
- [Akash AEP-37 (LeaseRPC Proposal)](https://akash.network/roadmap/aep-37/) — Future gRPC direction (not relevant for v1.5, uses native WebSocket)

---

*Research completed: 2026-04-18*  
*Ready for roadmap: YES*
