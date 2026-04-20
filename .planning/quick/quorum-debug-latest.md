# quorum-debug artifact
date: 2026-04-19T00:00:00Z
failure_context: Extend LeaseShellTransport.exec() to silently re-authenticate and reconnect when the provider closes the WebSocket due to JWT expiry, then continue streaming output until the command completes. Add unit tests proving the reconnect path. Purpose: Fulfils LSHL-03. Output: exec() that retries on auth-close (WebSocket close codes 4001/4003, or ConnectionClosedError containing "expired"/"unauthorized") by fetching a fresh JWT and reopening the connection.
exit_code: 0 (tests pass — symptom only, feature not yet implemented)

## consensus
root_cause: exec() in just_akash/transport/lease_shell.py (lines 199-200) catches ConnectionClosedError and breaks without any reconnect or JWT refresh, so any auth-expiry close terminates the command instead of retrying with a fresh token
next_step: Inspect just_akash/transport/lease_shell.py lines 162-205 (exec() body) and confirm the exact exception handling shape before implementing _exec_with_refresh() and _is_auth_expiry() as specified in 07-02-PLAN.md

## formal model deliverable
reproducing_model: none
formal_verdict: no-model
constraints_extracted: 0
tsv_trace: none
refinement_iterations: N/A
converged: N/A

## constraints
none

## worker responses
| Model    | Confidence | Next Step                                |
|----------|------------|------------------------------------------|
| Gemini   | UNAVAIL    | spawn error: CLI path null               |
| OpenCode | UNAVAIL    | spawn error: CLI path null               |
| Copilot  | UNAVAIL    | spawn error: CLI path null               |
| Codex    | UNAVAIL    | spawn error: CLI path null               |
| FORMAL   | N/A        | No formal model covers this failure      |
| CONSENSUS| HIGH       | See root_cause and next_step above       |

## bundle
FAILURE CONTEXT: Extend LeaseShellTransport.exec() to silently re-authenticate and reconnect when the provider closes the WebSocket due to JWT expiry.
EXIT CODE: 0 (symptom only)
FORMAL VERDICT: no-model
CONSTRAINTS: none

File: just_akash/transport/lease_shell.py
- exec() lines 162-205: NO reconnect logic, ConnectionClosedError caught at lines 199-200 with bare break
- No MAX_RECONNECT_ATTEMPTS, _exec_with_refresh(), _is_auth_expiry() helpers
- _fetch_jwt() exists (line 52)
- Uses websockets.sync.client.connect (synchronous)

File: tests/test_lease_shell_exec.py
- 443 passing tests, NO reconnect tests

Plan 07-02-PLAN.md: fully specifies MAX_RECONNECT_ATTEMPTS=3, _exec_with_refresh(), _is_auth_expiry() with codes 4001/4003 + "expired"/"unauthorized" strings, 5 required tests.

websockets.frames.Close(code, reason) confirmed working for test construction.
ConnectionClosedError(rcvd=Close(code=4001, reason="token expired"), sent=None) produces rcvd.code=4001, rcvd.reason="token expired".
