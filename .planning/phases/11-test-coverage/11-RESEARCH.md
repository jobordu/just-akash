# Phase 11: Test Coverage — Research

**Researched:** 2026-04-19
**Domain:** E2E test orchestration (deploy/teardown via CLI subprocess), unit test mocking (WebSocket + JWT), pytest fixture patterns
**Confidence:** HIGH (existing test patterns in phases 7-10 are proven; Justfile recipes exist; pytest config verified)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TEST-01 | `just test-shell` deploys an instance, runs exec, inject, and connect via lease-shell, and tears the deployment down — passing green from a clean environment | E2E recipe pattern: `uv run python -m just_akash.test_shell_e2e` (modeled on existing `test_lifecycle.py` + `test_secrets_e2e.py`) — deploy via `just up`, wait for lease, run exec/inject/connect commands via CLI subprocess, cleanup via `just destroy` |
| TEST-02 | Unit tests for the transport layer run without a network connection by using a mocked WebSocket, and cover normal operation, token refresh, and connection error paths | Existing tests in `tests/test_lease_shell_exec.py` (41 tests) cover normal exec; Phase 8 `test_transport_inject.py` has 8 tests; Phase 9 `test_interactive_shell.py` has 13 stubs. Gaps: explicit token refresh unit tests + connection error edge cases. |

</phase_requirements>

---

## Summary

Phase 11 is the final validation phase for the lease-shell transport implementation (phases 6-10). It delivers two complementary validation strategies: **(1) E2E integration testing** that exercises the full CLI stack against a real Akash deployment, and **(2) unit testing with mocked WebSockets** that isolates transport behavior without network dependencies.

The existing unit test suite is extensive (483 tests, 69% coverage) and already uses FakeWebSocket mocks established in Phase 7's `test_lease_shell_exec.py`. Phase 11 consolidates the test coverage into two focused deliverables:

1. **E2E Recipe (`just test-shell`)**: Deploy → run exec/inject/connect via lease-shell → verify outputs → teardown. Modeled on proven `test_lifecycle.py` and `test_secrets_e2e.py` patterns.
2. **Unit Test Gaps**: Formalize token refresh reconnection tests (already implemented in Phase 7), add connection error path tests, and ensure all three transport methods (exec, inject, connect) have explicit coverage with mocked WebSockets.

**Primary recommendation:** Write `just_akash/test_shell_e2e.py` as a standalone E2E orchestrator (not pytest); add a `just test-shell` recipe; create focused unit test files for token refresh and error cases; maintain the FakeWebSocket mock pattern for isolation.

---

## Standard Stack

### Core Testing Framework

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=9.0.3 | Test discovery + execution | Already in `pyproject.toml` dev dependencies; 483 tests passing |
| pytest-cov | >=7.1.0 | Coverage reporting | Already integrated; `--cov=just_akash --cov-report=term-missing` in `pyproject.toml` |
| unittest.mock | stdlib | Mocking (patch, MagicMock) | Already used in existing test suite; avoids pytest-mock dependency |
| websockets | >=16.0 | FakeWebSocket fixture + real testing | Already in core dependencies |

### Mocking Patterns

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| FakeWebSocket | custom | Mock WebSocket that yields pre-built frames | Unit tests — avoids real network calls |
| unittest.mock.patch | stdlib | Patch module-level functions (api.py, signal handlers) | Terminal resize, signal handlers, JWT fetch |
| unittest.mock.MagicMock | stdlib | Track call history, control return values | Verify exec() calls in inject(), mock AkashConsoleAPI |

### E2E Test Orchestration

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| subprocess.run | stdlib | Invoke `just` recipes and CLI commands | E2E only — deploy, verify status, exec, inject, connect, teardown |
| re (regex) | stdlib | Parse DSEQ from output, verify command results | E2E stdout/stderr parsing |
| time.sleep | stdlib | Wait for deployment + lease readiness | E2E sequencing (10s between steps) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FakeWebSocket (custom) | pytest-mock + mock.AsyncMock | pytest-mock adds dependency; async/sync mismatch with websockets.sync.client |
| subprocess.run (CLI testing) | Direct Python API calls in E2E | Avoids subprocess complexity but doesn't test real CLI argument parsing and exit codes |
| Custom E2E script (`test_shell_e2e.py`) | pytest parameterized tests | E2E requires 5+ minute deployments; pytest discovery would slow test runs; standalone script is cleaner for long-running flows |

**Installation:** No new packages required. All dependencies already in `pyproject.toml`.

---

## Architecture Patterns

### Recommended Project Structure

```
just_akash/
├── test_shell_e2e.py           # NEW: E2E orchestrator (just test-shell invokes this)
├── transport/
│   └── lease_shell.py          # (unchanged — phases 6-10 complete)
└── api.py                       # (unchanged)

tests/
├── test_lease_shell_exec.py    # Phase 7: 41 tests (exec happy path + token refresh)
├── test_transport_inject.py    # Phase 8: 8 tests (inject three-step command sequence)
├── test_interactive_shell.py   # Phase 9: 13 tests (connect, TTY setup, signals)
├── test_default_transport.py   # Phase 10: 9 tests (transport selection, fallback)
├── test_transport_errors.py    # NEW: Token expiry edge cases, connection close codes
└── test_transport_mocks.py     # NEW: Shared FakeWebSocket, fixtures for all transport tests
```

### Pattern 1: FakeWebSocket Mock

**What:** A minimal mock WebSocket that yields pre-built binary frames then signals `ConnectionClosedOK`.
**When to use:** Unit tests that isolate frame dispatch, reconnection logic, and error handling without network.

```python
# Source: tests/test_lease_shell_exec.py (Phase 7)

class FakeWebSocket:
    """Minimal WebSocket mock that serves pre-built frames then closes."""
    def __init__(self, frames):
        self._frames = iter(frames)

    def recv(self, timeout=None):
        try:
            return next(self._frames)
        except StopIteration:
            raise ConnectionClosedOK(None, None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def send(self, data):
        """Stub for frames sent to the WebSocket (used in connect() tests)."""
        pass

    def close(self):
        pass
```

### Pattern 2: E2E Test Orchestration (Subprocess-Based)

**What:** A standalone Python script that orchestrates Justfile recipes (deploy, verify, test, teardown) via subprocess.run().
**When to use:** Integration testing that exercises the full CLI stack against real Akash deployments.

Example structure (from `test_lifecycle.py` + `test_secrets_e2e.py`):

```python
# Source: just_akash/test_shell_e2e.py (NEW for Phase 11)

def run(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Execute a shell command and return result."""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

def main():
    """E2E test: deploy → exec/inject/connect via lease-shell → cleanup."""
    failures = []
    dseq = None

    # Step 1: Validate environment (AKASH_API_KEY, AKASH_PROVIDERS, SSH_PUBKEY)
    # Step 2: Deploy instance via `just up`
    # Step 3: Wait for lease (10s delay, status check)
    # Step 4: Run exec() via `uv run just-akash exec "echo hello"`
    # Step 5: Run inject() via `uv run just-akash inject --env-file .env.test`
    # Step 6: Run connect() with TTY test (send "echo test" + Ctrl+D)
    # Step 7: Cleanup via `just destroy <dseq>`

    if failures:
        sys.exit(1)
```

### Pattern 3: Connection Error Detection

**What:** Detect JWT expiry via WebSocket close code (4001/4003) and reason string matching ("expired", "unauthorized").
**When to use:** Unit tests for token refresh logic and connection error recovery.

```python
# Source: lease_shell.py (Phase 7)

def _is_auth_expiry(exc: ConnectionClosedError) -> bool:
    """Return True if close event indicates JWT expiry or auth failure."""
    rcvd = getattr(exc, "rcvd", None)
    if rcvd is not None:
        code = getattr(rcvd, "code", None)
        if code in (4001, 4003):
            return True
        reason = getattr(rcvd, "reason", "") or ""
        if _is_auth_expiry_message(reason):
            return True
    return _is_auth_expiry_message(str(exc))
```

### Anti-Patterns to Avoid

- **Don't mock the entire CLI context:** Use subprocess to invoke the real CLI, not mocks of argument parsing. This catches real integration issues.
- **Don't replay output on reconnect:** Accumulated stdout/stderr persists; new frames resume streaming. This is a documented feature (Phase 7) — don't change it in tests.
- **Don't use pytest for long-running E2E:** E2E tests (5+ minute deployments) slow down pytest discovery. Keep them in standalone scripts invoked via `just test-shell`.
- **Don't skip terminal cleanup:** connect() MUST restore the terminal in a finally block, even on exception. Tests should verify this with signal injection.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket mocking | Custom frame serializer/deserializer | FakeWebSocket (iter over pre-built bytes) | Frame format is binary + requires byteorder awareness; FakeWebSocket eliminates this complexity |
| Long-running test orchestration | pytest parameterized fixtures with 5-minute deployments | Standalone Python script invoked via `just test-shell` | pytest discovery and parallel execution don't mix well with 5-minute per-test waits |
| SSH key discovery | Custom key path logic | Reuse `test_lifecycle.py` pattern (check known paths) | SSH key location varies; existing pattern handles common cases |
| DSEQ extraction | Custom regex | Reuse `re.search(r"DSEQ[:\s]+(\d+)", output)` | Proven by existing E2E tests; avoids regex drift |
| Terminal dimensions | Custom os.get_terminal_size() wrapping | Direct call with OSError fallback | os module handles edge cases (non-TTY, missing terminal size) |
| Signal forwarding | Custom signal handler registration | signal.signal() + finally block restoration | signal handlers are global; improper cleanup leaks state across tests |

**Key insight:** WebSocket mocking and signal handling both require precise control over global state. Don't build custom abstractions — use stdlib functions and FakeWebSocket (proven in Phase 7) to keep the implementation clear and testable.

---

## Common Pitfalls

### Pitfall 1: E2E Timeouts and Unreliable Lease Propagation

**What goes wrong:** `just deploy` completes, but the lease is not yet visible in the Console API. Running exec immediately fails with "no leases found".
**Why it happens:** Akash providers take 10-30 seconds to bid and activate a lease. The deployment may be accepted but not yet assigned.
**How to avoid:** Insert a 10-second wait after `just up` before attempting `just status`. Then poll `just status` up to 5 times with 5-second intervals until a lease appears. Only then proceed to exec/inject/connect.
**Warning signs:** "No leases found for deployment" in test output; non-deterministic test failures based on Akash network latency.

### Pitfall 2: Terminal Not Restored on Abnormal Exit

**What goes wrong:** A test crashes during `connect()` test, leaving the terminal in raw mode. Subsequent tests or user shell are unusable (no echo, no line editing).
**Why it happens:** The finally block that calls `termios.tcsetattr()` must be unconditional and must happen even if the WebSocket connection crashes or a signal is raised.
**How to avoid:** Verify in `test_interactive_shell.py` that the finally block is always executed. Use pytest's `pytest.raises` context manager and verify terminal state after. Consider testing with explicit SIGINT injection.
**Warning signs:** User reports "my shell is broken" after test run; terminal control characters appear in test output instead of being processed.

### Pitfall 3: FakeWebSocket Iterator Exhaustion

**What goes wrong:** A test calls `recv()` more times than there are frames in FakeWebSocket, expecting `ConnectionClosedOK` but the test hangs.
**Why it happens:** FakeWebSocket uses `iter()` over a list. Once exhausted, repeated `recv()` calls raise `ConnectionClosedOK`. But if a test expects more frames than provided, it silently closes instead of erroring.
**How to avoid:** Document FakeWebSocket behavior: "Exhausted frames → ConnectionClosedOK (not error)". In tests, explicitly verify frame counts match expectations. Add a helper that builds FakeWebSocket with exact expected frames, raising AssertionError if recv() is called unexpectedly.
**Warning signs:** Tests pass but don't actually exercise the code path; frame count mismatches not caught until integration.

### Pitfall 4: Mocking Conflicts Between Unit and E2E Tests

**What goes wrong:** A unit test patches `websockets.sync.client.connect` globally, breaking subsequent E2E tests that expect the real connection.
**Why it happens:** `unittest.mock.patch` is global unless scoped to a context manager. If a test forgets to exit the context, patches leak.
**How to avoid:** Always use `patch()` as a context manager or decorator, never module-level. Run unit tests in isolation from E2E tests (separate pytest invocations or explicit test markers).
**Warning signs:** "E2E test fails only after running unit tests" — patch leak. Check `pytest.mark.integration` and separate `pytest -m unit` from `pytest -m integration`.

### Pitfall 5: JWT TTL Validation Missed in Refresh Tests

**What goes wrong:** A test simulates token expiry but doesn't verify that the new JWT was actually fetched before reconnection.
**Why it happens:** The reconnection logic (_exec_with_refresh) might cache the old JWT instead of fetching a fresh one, defeating the purpose of token refresh.
**How to avoid:** In token refresh tests, mock `_fetch_jwt()` with a side_effect that returns different tokens on each call. Verify that the second JWT is different from the first via URL inspection or mock call counts.
**Warning signs:** "Token refresh tests pass but real long sessions still crash on token expiry" — cached JWT issue.

---

## Code Examples

Verified patterns from official sources and existing test suite:

### E2E Test Structure (Orchestration)

```python
# Source: just_akash/test_lifecycle.py + test_secrets_e2e.py (proved patterns)
# NEW for Phase 11: combine into test_shell_e2e.py

def main():
    """E2E: deploy → exec/inject/connect via lease-shell → cleanup."""
    failures = []
    dseq = None

    try:
        # Step 1: Validate environment
        for var in ("AKASH_API_KEY", "AKASH_PROVIDERS", "SSH_PUBKEY"):
            if not os.environ.get(var):
                log_fail(f"{var} not set")
                sys.exit(1)

        # Step 2: Deploy
        log_step(1, "Deploy instance via just up")
        r = run("just up", timeout=300)
        if r.returncode != 0:
            log_fail("just up failed")
            sys.exit(1)
        m = re.search(r"DSEQ[:\s]+(\d+)", r.stdout + r.stderr)
        dseq = m.group(1) if m else None
        if not dseq:
            log_fail("Could not parse DSEQ")
            sys.exit(1)
        log_pass(f"Deployed: DSEQ={dseq}")

        # Step 3: Wait for lease
        log_step(2, f"Wait for lease (DSEQ={dseq})")
        time.sleep(10)
        for attempt in range(1, 6):
            r = run(f"uv run just-akash status --dseq {dseq}", timeout=30)
            if "hostUri" in r.stdout or "host_uri" in r.stdout:
                log_pass("Lease active")
                break
            if attempt < 5:
                time.sleep(5)
        else:
            log_fail("Lease not active after 30s")
            failures.append("lease_timeout")

        # Step 4: Run exec via lease-shell
        log_step(3, f"Run exec via lease-shell (DSEQ={dseq})")
        r = run(f"uv run just-akash exec 'echo hello from lease-shell' --dseq {dseq}", timeout=30)
        if r.returncode == 0 and "hello from lease-shell" in r.stdout:
            log_pass("exec returned correct output")
        else:
            log_fail(f"exec failed or output mismatch:\n{r.stderr}")
            failures.append("exec_failed")

        # Step 5: Run inject via lease-shell
        log_step(4, f"Run inject via lease-shell (DSEQ={dseq})")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("TEST_SECRET=injected_value\n")
            env_file = f.name
        try:
            r = run(f"uv run just-akash inject --env-file {env_file} --dseq {dseq}", timeout=30)
            if r.returncode == 0:
                log_pass("inject succeeded")
            else:
                log_fail(f"inject failed:\n{r.stderr}")
                failures.append("inject_failed")
        finally:
            os.unlink(env_file)

        # Step 6: Verify inject worked (via exec reading the file)
        log_step(5, f"Verify inject (DSEQ={dseq})")
        r = run(f"uv run just-akash exec 'cat /tmp/test.env' --dseq {dseq}", timeout=30)
        if r.returncode == 0 and "injected_value" in r.stdout:
            log_pass("inject verified")
        else:
            log_fail(f"inject verification failed:\n{r.stderr}")
            failures.append("inject_verify_failed")

        # Step 7: Cleanup
        log_step(6, f"Cleanup (destroy DSEQ={dseq})")
        r = run(f"just destroy {dseq}", timeout=60)
        if r.returncode == 0:
            log_pass("Destroyed")
        else:
            log_fail(f"destroy failed:\n{r.stderr}")
            failures.append("destroy_failed")

    except Exception as e:
        log_fail(f"Unexpected error: {e}")
        failures.append(str(e))
        if dseq:
            run(f"just destroy {dseq}")

    if failures:
        log_fail(f"Test failed with {len(failures)} error(s): {failures}")
        sys.exit(1)
    else:
        log_pass("All steps passed")
```

### Unit Test: Token Refresh Reconnection

```python
# Source: tests/test_lease_shell_exec.py (Phase 7 — existing pattern)
# NEW for Phase 11: explicit coverage in test_transport_errors.py

def test_exec_reconnects_on_token_expiry_code_4001():
    """Test _exec_with_refresh() reconnects when server closes with code 4001 (expired)."""
    config = TransportConfig(
        dseq="123",
        api_key="key",
        deployment=DEPLOYMENT_FIXTURE,
    )
    transport = LeaseShellTransport(config)

    # Mock API to return different JWTs on each call (verify refresh)
    jwt_sequence = ["jwt-1", "jwt-2"]
    jwt_calls = []
    def side_effect_jwt(ttl=3600):
        jwt_calls.append(ttl)
        return jwt_sequence[len(jwt_calls) - 1]

    # Mock WebSocket: first connection closes with 4001, second succeeds
    def side_effect_connect(url, *args, **kwargs):
        class MockWS:
            def __init__(self):
                self._attempt = len(jwt_calls)
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def recv(self, timeout=None):
                if self._attempt == 1:
                    # First attempt: auth expiry
                    close_frame = Close(code=4001, reason="JWT expired")
                    raise ConnectionClosedError(rcvd=close_frame, sent=None)
                else:
                    # Second attempt: success
                    return bytes([102]) + (0).to_bytes(4, "little")
        return MockWS()

    with patch.object(transport, "_fetch_jwt", side_effect=side_effect_jwt) as mock_fetch, \
         patch("just_akash.transport.lease_shell.connect", side_effect=side_effect_connect):
        result = transport._exec_with_refresh("echo test")

    assert result == 0
    assert len(jwt_calls) == 2
    assert jwt_calls[0] == 3600  # first JWT request
    assert jwt_calls[1] == 3600  # second JWT request (refresh)
```

### Unit Test: Connection Error Handling

```python
# Source: NEW for Phase 11 (test_transport_errors.py)

def test_exec_raises_on_provider_error_frame_103():
    """Test exec() raises RuntimeError when provider sends frame 103 (failure)."""
    config = TransportConfig(
        dseq="123",
        api_key="key",
        deployment=DEPLOYMENT_FIXTURE,
    )
    transport = LeaseShellTransport(config)

    fake_ws = FakeWebSocket([
        bytes([103]) + b"provider error: out of memory",
    ])

    with patch.object(transport, "_fetch_jwt", return_value="jwt"), \
         patch("just_akash.transport.lease_shell.connect", return_value=fake_ws):
        with pytest.raises(RuntimeError, match="provider error: out of memory"):
            transport.exec("echo test")
```

### Justfile Recipe

```makefile
# Source: NEW for Phase 11 (Justfile)

# Full E2E test: deploy → lease-shell exec/inject/connect → cleanup
test-shell:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/test-shell-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=test-shell finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=test-shell started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run python -m just_akash.test_shell_e2e
```

---

## Validation Architecture

Phase 11 requires explicit coverage of two test tiers, per `nyquist_validation_enabled: true`:

### Wave 0: Test Scaffolding and Infrastructure

**Tasks:**
1. Create `tests/test_transport_errors.py` with RED stubs for token expiry paths (4001/4003 close codes, "expired"/"unauthorized" in reason)
2. Create `tests/test_transport_mocks.py` with shared FakeWebSocket fixture and helper functions
3. Create `just_akash/test_shell_e2e.py` with stub main() orchestrator
4. Add `just test-shell` recipe to Justfile

**Test Command (Wave 0 RED):**
```bash
uv run pytest tests/test_transport_errors.py -v  # RED: 8+ failing tests for edge cases
uv run pytest tests/test_transport_mocks.py -v   # PASS: fixture validation
```

### Wave 1: Unit Test Implementation

**Task:** Implement token refresh and error path tests
**Test Types:**
- **unit (isolated)**: FakeWebSocket mocks, no network — `tests/test_transport_errors.py`, `tests/test_lease_shell_exec.py` additions
- **unit (mocked API)**: `unittest.mock.patch` for AkashConsoleAPI and signal handlers — `tests/test_transport_inject.py`, `tests/test_interactive_shell.py`

**Test Command:**
```bash
uv run pytest tests/ -k "transport" -v --cov=just_akash.transport --cov-report=term-missing
```

Expected: 483 tests passing (existing + new), >85% coverage on `lease_shell.py`

### Wave 2: E2E Integration Testing

**Task:** Implement `test_shell_e2e.py` orchestrator
**Test Type:**
- **integration (E2E)**: Real Akash deployment, CLI subprocess, no mocks — deploy → exec → inject → connect → cleanup
- **manual (optional)**: User runs `just test-shell` in live environment

**Test Command:**
```bash
just test-shell  # Requires AKASH_API_KEY, AKASH_PROVIDERS, SSH_PUBKEY; 5-10 minute runtime
```

Expected: "All steps passed" message; DSEQ deployed and destroyed; exec/inject output verified.

### Per-Task Test Specification

| Task | Unit | Integration | Smoke | Manual |
|------|------|-------------|-------|--------|
| Create test_transport_errors.py + fixtures | ✓ RED stubs | — | — | — |
| Implement token refresh tests | ✓ FakeWebSocket | — | — | — |
| Implement connection error tests | ✓ close codes 4001/4003 | — | — | — |
| Implement test_shell_e2e.py + just test-shell | — | ✓ real deployment | — | ✓ human verify |
| Verify exec/inject/connect via CLI | — | ✓ subprocess | ✓ manual echo test | — |
| Terminal cleanup guarantee | ✓ finally block + signal test | — | ✓ verify tcsetattr | — |

### Quick-Run Test Command

```bash
# Unit only (fast, no network)
uv run pytest tests/ -v --cov=just_akash --cov-report=term-missing

# Unit + smoke (verify transport layer doesn't crash on known inputs)
uv run pytest tests/ -k "transport" -v

# E2E only (requires Akash account, 5+ minutes)
just test-shell
```

### Coverage Targets

| Module | Existing | Target | New Tests |
|--------|----------|--------|-----------|
| `lease_shell.py` | 65% | 88% | Token refresh + error paths + connect integration |
| `base.py` | 100% | 100% | (no changes) |
| `ssh.py` | 100% | 100% | (unchanged) |
| **Overall** | 69% | 75% | +10 unit tests, 1 E2E script |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSH-only transport | Lease-shell with SSH fallback | Phase 10 (2026-04-19) | V1.5 ships with WebSocket by default; SSH is fallback |
| Manual E2E testing (human runs `just up` then `just connect`) | Automated E2E recipe (`just test-shell`) | Phase 11 (this phase) | Validation is reproducible and CI-able |
| FakeWebSocket in test_lease_shell_exec only | Shared fixture in test_transport_mocks.py | Phase 11 (this phase) | Reduces test duplication, ensures consistent mocking |
| No explicit token refresh tests | Token refresh reconnection tested in test_transport_errors.py | Phase 11 (this phase) | LSHL-03 compliance verified automatically |

**Deprecated/outdated:**
- SSH-only E2E testing: `test_lifecycle.py` becomes optional (users can still manually run it), but `test_shell_e2e.py` is the new primary E2E validation.
- Manual lease-shell verification: Phase 11 makes it reproducible.

---

## Validation Checklist

**Unit Tests (pytest fast path):**
- [ ] `pytest tests/test_transport_errors.py -v` — 8+ tests for token expiry, close codes, auth errors
- [ ] `pytest tests/test_transport_mocks.py -v` — Fixtures and helpers validate
- [ ] `pytest tests/test_lease_shell_exec.py -v` — 41 existing tests still pass (unchanged)
- [ ] `pytest tests/ -k "transport" --cov=just_akash.transport` — >85% coverage on lease_shell.py

**E2E (Akash deployment):**
- [ ] `just test-shell` runs with AKASH_API_KEY + AKASH_PROVIDERS set
- [ ] Deployment succeeds, DSEQ extracted, lease appears within 30s
- [ ] exec() outputs "hello from lease-shell" correctly
- [ ] inject() succeeds, verified by exec() reading the file
- [ ] connect() (if manual) shows interactive shell with proper terminal control
- [ ] Teardown succeeds, deployment is closed

**Terminal Cleanup:**
- [ ] After test run, terminal is in cooked mode (echo works, line editing works)
- [ ] No "Bad file descriptor" or similar errors in logs
- [ ] Raw mode state doesn't leak to subsequent tests

---

## Open Questions

1. **Should `test_shell_e2e.py` use the real CLI or call Python APIs directly?**
   - **What we know:** Existing `test_lifecycle.py` uses subprocess to invoke `just` targets.
   - **What's unclear:** Is this approach sufficient for TEST-01, or should we verify both CLI argument parsing and Python-level integration?
   - **Recommendation:** Use subprocess (proven pattern) — it catches CLI parsing bugs. If API-level integration is needed, add a separate pytest test that calls `Transport.exec()` directly with mocked WebSocket.

2. **What terminal size should `test_shell_e2e.py` use for connect() testing?**
   - **What we know:** `os.get_terminal_size()` returns actual terminal dimensions; tests should handle both TTY and non-TTY environments.
   - **What's unclear:** Should E2E test inject a fixed terminal size (e.g., 80x24) or use whatever the test runner provides?
   - **Recommendation:** Use `os.get_terminal_size()` with fallback to 80x24 if not a TTY. Log the actual size used for debugging.

3. **Should unit tests for connect() use pytest fixtures or manual setup?**
   - **What we know:** Existing `test_interactive_shell.py` uses manual setup with patched signal handlers.
   - **What's unclear:** Would pytest fixtures make the tests more readable, or would they obscure the signal handling complexity?
   - **Recommendation:** Keep manual setup (status quo). Signals are global state and require explicit restoration; fixtures can hide this. If tests proliferate, consider a context manager for signal fixture management.

---

## Sources

### Primary (HIGH confidence)

- **Existing test suite** — 483 tests verified passing, FakeWebSocket pattern established in Phase 7, pytest config in `pyproject.toml`
- **Justfile recipes** — `just test` (test_lifecycle.py), `just test-secrets` (test_secrets_e2e.py) — proven E2E orchestration patterns
- **Transport implementation** — `just_akash/transport/lease_shell.py` (phases 6-10) — connection error detection via `_is_auth_expiry()` verified via close code 4001/4003 and reason string matching
- **pytest official docs** (verified 2026-04-19) — parametrization, fixtures, coverage integration

### Secondary (MEDIUM confidence)

- **websockets library docs** — `ConnectionClosedError.rcvd.code` attribute confirmed; frame format binary structure
- **Python stdlib documentation** — `unittest.mock.patch`, `signal.signal()` behavior, `termios.tcsetattr()` restoration guarantees

### Tertiary (LOW confidence)

- None — all recommendations are either from working code (existing tests) or official library docs.

---

## Metadata

**Confidence breakdown:**
- **Standard stack:** HIGH — pytest, pytest-cov, FakeWebSocket pattern all proven in existing test suite
- **Architecture:** HIGH — E2E orchestration pattern copied from `test_lifecycle.py` + `test_secrets_e2e.py`; mocking patterns established in Phase 7
- **Pitfalls:** MEDIUM — lease propagation delay (10-30s) is known from real Akash network behavior; terminal cleanup is empirically tested in Phase 9; connection error paths are documented in Phase 7 implementation
- **Validation plan:** HIGH — Wave 0/1/2 test taxonomy matches project patterns; per-task test types specified; quick-run commands provided

**Research date:** 2026-04-19
**Valid until:** 2026-05-19 (30 days — test infrastructure is stable; pytest/websockets versions locked in pyproject.toml)
