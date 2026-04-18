# Feature Landscape: Lease-Shell WebSocket Transport

**Domain:** Interactive shell access to Akash Network deployments  
**Researched:** 2026-04-18

## Table Stakes

Features users expect from shell access to a running deployment.

| Feature | Why Expected | Complexity | Notes | Akash Status |
|---------|--------------|------------|-------|--------------|
| Execute remote command | Core functionality of any deployment | Low | `just-akash exec <dseq> <cmd>` | ✓ SSH v1.4, WebSocket v1.5 |
| Inject secrets/files | Deploy-time env vars insufficient; need runtime injection | Low-Medium | `just-akash inject <dseq> <file>` | ✓ SSH v1.4, WebSocket v1.5 |
| Interactive shell | Ad-hoc debugging, manual fixes without redeploy | Medium | `just-akash shell <dseq>` or `connect` | ✓ SSH v1.4, WebSocket v1.5 |
| Command output capture | Scripting, log collection | Low | Exec returns stdout/stderr | ✓ Both transports |
| Error codes from remote | Script decision-making | Low | Capture exit code from remote command | ✓ Both transports |
| Terminal size sync | Interactive shell doesn't get cut off mid-line | Medium | SIGWINCH handling | ⚠ SSH works; WebSocket needs frame support |
| Ctrl+C handling | Interrupt remote process | Low | Send SIGINT over channel | ✓ Both transports |
| File transfer | Larger datasets than env vars | Medium | `inject` over WebSocket (vs SSH SCP) | ⚠ WebSocket may need chunking |

## Differentiators

Features that set lease-shell WebSocket apart from SSH.

| Feature | Value Proposition | Complexity | Implementation Status |
|---------|-------------------|------------|----------------------|
| No SSH key management | Users don't need to generate/store SSH keys | Low | ✓ Akash API key sufficient |
| Decentralized endpoint | No single SSH server; provider hosts WebSocket | Medium | ✓ Akash Console API handles this |
| Audit trail | WebSocket handshake can log user identity | Medium | ~ Depends on Akash provider logging |
| Timeout isolation | Lease-shell timeout per-command vs persistent SSH | Low | ✓ Cleaner resource cleanup |
| Browser-compatible | Future: web console can use same endpoint | Medium | ⚠ Not v1.5 scope |
| Streaming I/O | Server can push data (logs, events) without client polling | Medium | ⚠ Not v1.5 scope; future for tailing logs |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| SSH port forwarding over WebSocket | Out of scope; SSH for this use case | Keep SSH available via `--transport ssh` |
| SCP file transfer semantics | WebSocket frame-by-frame, not SCP's binary protocol | Use simpler base64/chunked encoding for `inject` |
| Interactive terminal multiplexing (tmux/screen) | User-space concern, not transport layer | Document tmux usage over WebSocket shell |
| SSH agent forwarding | Not applicable to WebSocket | Not needed (no SSH key chain) |
| SFTP server over WebSocket | File server is separate concern | Use exec to run container file server if needed |

## Feature Dependencies

```
Exec (command execution) — Base feature, no deps
    ↓
Inject (file injection) — Requires exec + base64 encoding
    ↓
Interactive Shell — Requires exec + TTY emulation
    ↓
Terminal Size Sync — Optional enhancement for interactive shell
    ↓
Streaming Logs (future) — Requires server-side streaming support
```

## MVP Recommendation

**v1.5 should ship with:**
1. ✓ Execute remote command (`exec`) over lease-shell
2. ✓ Inject secrets/files (`inject`) over lease-shell  
3. ✓ Interactive shell (`shell` or `connect`) over lease-shell
4. ✓ Error code capture + Ctrl+C handling
5. ✓ Backward compatibility: `--transport ssh` fallback

**Defer to v1.6+:**
- Terminal size sync (SIGWINCH) — Nice to have; not blocking
- Streaming logs (server-side feature) — Depends on Akash 1.15+ provider
- Browser-based console integration — Separate v2.0 goal
- Windows interactive shell support — Use SSH fallback; pexpect POSIX-only

## User Stories (v1.5)

### Story 1: Deploy and Execute Command (No Interaction)
```bash
just-akash deploy --env KEY=value sdl/my-app.yaml
# Get dseq from output, e.g., 1234567

just-akash exec 1234567 "ls -la /app"
# Output:
# total 48
# drwxr-xr-x 2 root root ...
# -rw-r--r-- 1 root root 1234 app.jar
```
**Status**: ✓ MVP - works with both SSH and WebSocket

### Story 2: Inject Secrets at Runtime
```bash
echo "supersecret" > /tmp/secret.txt
just-akash inject 1234567 /tmp/secret.txt:/app/secret.txt

# Verify via exec
just-akash exec 1234567 "cat /app/secret.txt"
# Output: supersecret
```
**Status**: ✓ MVP - WebSocket needs base64 frame encoding (vs SSH SCP)

### Story 3: Interactive Debugging Session
```bash
just-akash shell 1234567
# Connected to deployment 1234567
> ls -la
total 48
drwxr-xr-x 2 root root ...
> ps aux
USER   PID  %CPU  %MEM  COMMAND
root   1    0.0   0.1   /entrypoint.sh
root   42   0.0   0.2   python app.py
> exit
# Session closed
```
**Status**: ✓ MVP - requires pexpect PTY bridging

### Story 4: Fallback to SSH if WebSocket Unavailable
```bash
# Provider doesn't support lease-shell (old version)
just-akash exec 1234567 "whoami"
# [WebSocket failed]
# [Falling back to SSH]
# Output: root

# Or explicit fallback
just-akash exec 1234567 --transport ssh "whoami"
# Output: root
```
**Status**: ✓ MVP - graceful degradation with `--transport ssh` flag

## Constraints & Assumptions

| Constraint | Assumption | Mitigation |
|-----------|-----------|------------|
| POSIX TTY only | Interactive shell unavailable on Windows | Document Windows SSH requirement; provide clear error message |
| WebSocket frame limit | Some providers may have frame size limits (e.g., 1MB) | Handle chunked binary frames for large file injection |
| Token TTL | Akash tokens expire (typically 15-60 min) | Implement token refresh middleware (Phase 1) |
| No multiplexing | One WebSocket per command (vs SSH multiplexing) | Accept limitation; each exec/inject opens new connection |
| Provider variability | Older Akash providers may lack lease-shell | Graceful fallback to SSH; version checking optional |

## Success Metrics (v1.5)

- [ ] `just-akash exec <dseq> <cmd>` works over lease-shell (baseline)
- [ ] `just-akash inject <dseq> <file>` works over lease-shell
- [ ] `just-akash shell <dseq>` provides interactive session (POSIX only)
- [ ] `--transport ssh` flag works for all commands as fallback
- [ ] Terminal cleanup verified (no TTY state leaks on exit)
- [ ] Akash e2e test passes with lease-shell (existing test, transport-agnostic)
- [ ] Coverage >= 70% for WebSocket code paths
- [ ] No regressions in SSH-based workflows
- [ ] Performance parity with SSH (within 10% for exec/inject)

## Notes

- **File Transfer**: Akash doesn't expose SCP over WebSocket; `inject` uses base64-encoded chunks sent as frames
- **Terminal Emulation**: pexpect bridges WebSocket I/O stream to user terminal, handling TTY state (raw mode, echo, line discipline)
- **Authentication**: Existing Akash API key flow (from .env AKASH_API_KEY) used to acquire WebSocket auth token
- **Scope**: v1.5 focuses on transport replacement; no changes to deployment creation, listing, or other non-shell features

## Sources

- [Akash Lease-Shell Documentation](https://docs.akash.network/features/deployment-shell-access)
- [Akash Console API (AEP-63)](https://akash.network/roadmap/aep-63/)
- [Akash Provider Console (GitHub)](https://github.com/akash-network/provider-console-api)
- [pexpect PTY Emulation](https://github.com/pexpect/pexpect)
- [websockets Library](https://pypi.org/project/websockets/)
- [Python TTY/PTY Handling](https://docs.python.org/3/library/pty.html)
