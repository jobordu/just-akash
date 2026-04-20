# Cleanup Report: Phase 10 Code Review

**Phase:** Default Transport Switch and Fallback (Phase 10)
**Date:** 2026-04-19
**Reviewer:** Claude Code

---

## Executive Summary

Phase 10 introduces default transport switching (lease-shell as default, fallback to SSH) across the CLI. Code review identified **8 findings** across 3 files:
- **High:** 3 findings (code duplication, defensive checks)
- **Medium:** 4 findings (overly specific tests, redundant validation)
- **Low:** 1 finding (defensive logging patterns)

No critical dead code or architectural over-engineering was found. The implementation is sound but contains repetitive patterns that should be simplified.

---

## File-by-File Analysis

### 1. `just_akash/cli.py`

**Location:** 239-273, 275-310, 313-390

#### Finding 1.1 (HIGH): Identical transport fallback pattern repeated 3 times

**Issue:** The connect, exec, and inject commands all implement the same transport-selection logic:
```python
use_lease_shell = args.transport == "lease-shell"
if use_lease_shell:
    from .transport import make_transport
    deployment = client.get_deployment(dseq)
    transport = make_transport("lease-shell", dseq=dseq, api_key=client.api_key, deployment=deployment)
    if not transport.validate():
        print("Notice: lease-shell transport is not available...")
        use_lease_shell = False
if use_lease_shell:
    # use transport
else:
    # fallback to SSH
```

This 15+ line pattern appears in lines 246-272, 281-307, and 343-363, verbatim except for method calls.

**Recommendation:** Extract to a helper function `_prepare_transport(args, client, dseq)` that:
- Returns `(transport, use_lease_shell)` tuple
- Handles validation and fallback notices
- Reduces duplication by ~45 lines

**Severity:** HIGH - Maintenance burden for future transport changes

---

#### Finding 1.2 (HIGH): Defensive argument validation overly permissive

**Issue:** Lines 321-325 validate `--env` format with a warning but continue executing:
```python
for pair in args.env_vars:
    if "=" not in pair:
        print(f"Error: Invalid --env format: {pair!r} (expected KEY=VALUE)")
        sys.exit(1)
    env_lines.append(pair)
```

This is correct, but preceded by:
```python
if args.env_file:
    from pathlib import Path
    env_file_path = Path(args.env_file)
    if not env_file_path.exists():
        print(f"Error: Env file not found: {args.env_file}")
        sys.exit(1)
```

Both validations are defensive but **inconsistent in scope**: env_file check only occurs if `--env-file` is provided. If user provides neither `--env` nor `--env-file`, the error at line 340 is the only catch:
```python
if not env_lines:
    print("Error: No secrets to inject. Use --env KEY=VALUE or --env-file PATH")
    sys.exit(1)
```

**Recommendation:** Move all validation to the top of the inject block:
```python
if not args.env_vars and not args.env_file:
    print("Error: Specify --env KEY=VALUE or --env-file PATH")
    sys.exit(1)
```

**Severity:** HIGH - Logic is defensive but scattered; makes control flow harder to follow

---

#### Finding 1.3 (MEDIUM): Redundant fallback notice identical across 3 commands

**Issue:** Lines 259, 294, and 355 print identical fallback notice:
```
"Notice: lease-shell transport is not available for this deployment "
"(no active lease or provider hostUri missing). Falling back to SSH."
```

This message appears 3 times verbatim.

**Recommendation:** Extract to module-level constant:
```python
FALLBACK_NOTICE = (
    "Notice: lease-shell transport is not available for this deployment "
    "(no active lease or provider hostUri missing). Falling back to SSH."
)
```

And use in all 3 places. **Benefit:** Single source of truth for user-facing message.

**Severity:** MEDIUM - Low impact but violates DRY principle

---

#### Finding 1.4 (LOW): NO_SSH_MSG could reference fallback transport

**Issue:** Lines 24-36 define `NO_SSH_MSG` which still mentions lease-shell as optional alternative:
```
"Alternatively, use lease-shell transport (default in v1.5): no SSH required."
```

This is correct, but the message is still defensive about SSH being required. Now that lease-shell is default, consider rewording to emphasize lease-shell as primary path.

**Recommendation:** Reword to:
```
"Alternatively, use the default lease-shell transport (no SSH required)."
```

**Severity:** LOW - Message is accurate but tone could be improved

---

### 2. `tests/test_default_transport.py`

**Location:** 54-113

#### Finding 2.1 (MEDIUM): Identical mock client generator repeated

**Issue:** Lines 19-37 and 40-51 define `_mock_client()` and `_mock_client_no_lease()` with nearly identical structure:

```python
def _mock_client(dseq="99999"):
    client = MagicMock()
    client.api_key = "test-key"
    client.list_deployments.return_value = [...]
    client.get_deployment.return_value = {
        "deployment": {...},
        "leases": [{"provider": {"hostUri": "..."}, ...}],
    }
    return client

def _mock_client_no_lease(dseq="99999"):
    client = MagicMock()
    client.api_key = "test-key"
    client.list_deployments.return_value = [...]
    client.get_deployment.return_value = {
        "deployment": {...},
        "leases": [],  # Only difference
    }
    return client
```

**Recommendation:** Refactor to single parameterized helper:
```python
def _mock_client(dseq="99999", has_lease=True):
    client = MagicMock()
    client.api_key = "test-key"
    client.list_deployments.return_value = [{"deployment": {"dseq": dseq, "state": "active"}}]
    leases = [{"provider": {"hostUri": "..."}, ...}] if has_lease else []
    client.get_deployment.return_value = {
        "deployment": {"dseq": dseq, "state": "active"},
        "leases": leases,
    }
    return client
```

**Severity:** MEDIUM - Duplication creates maintenance burden for mock evolution

---

#### Finding 2.2 (MEDIUM): Test assertions overly specific to private implementation details

**Issue:** Lines 72-83 test that `LeaseShellTransport.exec` is called:
```python
with patch("just_akash.transport.lease_shell.LeaseShellTransport.prepare"), \
     patch("just_akash.transport.lease_shell.LeaseShellTransport.exec", return_value=0) as mock_exec, \
     patch("just_akash.transport.lease_shell.LeaseShellTransport.validate", return_value=True):
    rc = _run(monkeypatch, ["just-akash", "exec", "--dseq", "99999", "echo hello"])
assert mock_exec.called, "exec command did not route to LeaseShellTransport.exec()..."
```

This test **requires knowledge of internal transport class structure** and would break if the transport layer is refactored (e.g., if `exec()` is renamed to `execute_command()`).

**Recommendation:** Test behavior, not implementation:
```python
with patch("just_akash.transport.make_transport") as mock_factory:
    mock_transport = MagicMock()
    mock_transport.validate.return_value = True
    mock_transport.exec.return_value = 0
    mock_factory.return_value = mock_transport
    rc = _run(monkeypatch, ["just-akash", "exec", "--dseq", "99999", "echo hello"])

# Assert transport was selected and methods called, without hardcoding class path
assert mock_factory.called_with("lease-shell", ...)
assert mock_transport.exec.called
```

**Severity:** MEDIUM - Brittle tests that couple to implementation details

---

#### Finding 2.3 (MEDIUM): Redundant test coverage for identical code paths

**Issue:** Lines 85-99 and 101-113 test `inject_defaults_to_lease_shell` and `connect_defaults_to_lease_shell` using identical logic to `exec_defaults_to_lease_shell`. Each test:
1. Mocks the same client
2. Patches the same transport methods
3. Asserts the same thing (method was called)

Since all 3 commands share identical transport logic (see Finding 1.1), testing all 3 separately is redundant.

**Recommendation:** Keep one representative test (exec), remove the others, document that connect/inject/inject follow the same pattern. Or use a parametrized test:
```python
@pytest.mark.parametrize("cmd,method", [
    (["exec", "--dseq", "99999", "echo hi"], "exec"),
    (["inject", "--dseq", "99999", "--env", "K=V"], "inject"),
    (["connect", "--dseq", "99999"], "connect"),
])
def test_defaults_to_lease_shell(cmd, method):
    # Single test covers all 3 paths
```

**Severity:** MEDIUM - Maintenance burden; 3 tests do redundant work

---

### 3. `tests/test_transport_cli_integration.py`

**Location:** 62-153

#### Finding 3.1 (MEDIUM): Over-defensive mock client with unused fields

**Issue:** Lines 32-56 define `_mock_client()` that includes detailed port forwarding data:
```python
{
    "leases": [
        {
            "status": {
                "forwarded_ports": {
                    "app": [
                        {
                            "port": 22,
                            "host": "provider.akash.network",
                            "externalPort": 32022,
                        }
                    ]
                }
            }
        }
    ]
}
```

But not all tests use this structure. Tests like `test_exec_accepts_transport_lease_shell` (line 82) override with a lease-shell specific deployment:
```python
lease_shell_deployment = {
    "leases": [{
        "provider": {"hostUri": "https://provider.example.com:8443"},
        "status": {"services": {"web": {}}},
    }]
}
client = _mock_client(deployment=lease_shell_deployment)
```

This creates two different deployment formats for SSH vs. lease-shell, causing mental overhead.

**Recommendation:** Simplify `_mock_client()` to accept minimal structure, or create separate `_mock_ssh_client()` and `_mock_lease_shell_client()` factory functions:
```python
def _mock_ssh_client(dseq="99999"):
    # Returns client with SSH port 22 forwarding
    ...

def _mock_lease_shell_client(dseq="99999"):
    # Returns client with lease-shell provider
    ...
```

**Severity:** MEDIUM - Overloaded mock makes test intent less clear

---

#### Finding 3.2 (MEDIUM): TestDefaultTransportIsSSH class title contradicts Phase 10 goal

**Issue:** Lines 159-194 test that "Default Transport is SSH" with class name `TestDefaultTransportIsSSH`, but Phase 10 **changes the default to lease-shell**.

The tests are labeled correctly (test methods use SSH), but the class name and docstring claim:
```python
class TestDefaultTransportIsSSH:
    """Omitting --transport behaves identically to --transport ssh."""
```

This is now **outdated and misleading**. These tests actually verify **zero regression** (SSH still works when explicitly requested), not that SSH is the default.

**Recommendation:** Rename to `TestSSHTransportStillWorks` or `TestSSHTransportRegression` and update docstring to clarify this is regression testing, not default behavior.

**Severity:** MEDIUM - Misleading documentation that contradicts Phase 10's goal

---

#### Finding 3.3 (LOW): Protocol constant validation uses hardcoded codes

**Issue:** Lines 442-449 define `EXPECTED_CODES` dict:
```python
EXPECTED_CODES = {
    "stdout": 100,
    "stderr": 101,
    "result": 102,
    "failure": 103,
    "stdin": 104,
    "resize": 105,
}
```

This dict is defined but **never used**. The test at lines 463-467 hardcodes the codes again:
```python
for code in [100, 101, 102, 103, 104, 105]:
    assert str(code) in content, f"Frame code {code} not documented in PROTOCOL.md"
```

**Recommendation:** Either:
1. Use `EXPECTED_CODES.values()` in the loop, or
2. Remove `EXPECTED_CODES` dict as dead code

**Severity:** LOW - Unused variable; minor code quality issue

---

## Summary Table

| Finding | File | Severity | Type | Lines |
|---------|------|----------|------|-------|
| 1.1 | cli.py | HIGH | Duplication | 246-272, 281-307, 343-363 |
| 1.2 | cli.py | HIGH | Defensive Logic | 321-340 |
| 1.3 | cli.py | MEDIUM | Duplication | 259, 294, 355 |
| 1.4 | cli.py | LOW | Messaging | 24-36 |
| 2.1 | test_default_transport.py | MEDIUM | Duplication | 19-51 |
| 2.2 | test_default_transport.py | MEDIUM | Over-Specific Tests | 72-113 |
| 2.3 | test_default_transport.py | MEDIUM | Redundant Coverage | 85-113 |
| 3.1 | test_transport_cli_integration.py | MEDIUM | Over-Defensive Mocks | 32-56 |
| 3.2 | test_transport_cli_integration.py | MEDIUM | Misleading Docs | 159-194 |
| 3.3 | test_transport_cli_integration.py | LOW | Dead Code | 442-449 |

**Total: 10 findings** (3 High, 6 Medium, 1 Low)

---

## Recommendations by Priority

### Priority 1 (Do Now - Phase 10 wrap-up)

1. **Extract transport fallback logic** (Finding 1.1)
   - Create `_prepare_transport(args, client, dseq)` helper
   - Eliminates 45 lines of duplication
   - Impact: Reduces cli.py by ~12%, improves maintainability for Phase 11+

2. **Consolidate fallback notice** (Finding 1.3)
   - Move to module constant `FALLBACK_NOTICE`
   - Impact: Single source of truth for messaging

3. **Rename misleading test class** (Finding 3.2)
   - Change `TestDefaultTransportIsSSH` → `TestSSHTransportRegression`
   - Update docstring to clarify zero-regression intent
   - Impact: Prevents future confusion about Phase 10's actual goal

### Priority 2 (Phase 10 cleanup window)

4. **Refactor mock clients** (Findings 2.1, 3.1)
   - Unify `_mock_client()` with `has_lease` parameter
   - Or create `_mock_ssh_client()` and `_mock_lease_shell_client()` factories
   - Impact: Easier to add/modify test scenarios in Phase 11+

5. **Remove dead code** (Finding 3.3)
   - Delete unused `EXPECTED_CODES` or integrate into test
   - Impact: Minimal, but improves code quality

### Priority 3 (Future phases)

6. **Reduce test specificity** (Finding 2.2)
   - Move from class path patching to behavior assertions
   - Impact: Allows Phase 11+ transport refactoring without test rewrites

7. **Consolidate validation logic** (Finding 1.2)
   - Validate all inject preconditions before processing
   - Impact: Improves clarity of control flow

---

## Risk Assessment

**No breaking changes** to functionality. All recommended changes are:
- Code style/organization improvements
- Test refactoring
- Documentation updates

Applying these recommendations will:
- Reduce cli.py from 539 to ~500 lines (7% reduction)
- Reduce test duplication by ~25%
- Improve future maintainability for Phases 11-12

**Recommendation:** Apply Priority 1 and Priority 2 recommendations before Phase 11 to prevent tech debt accumulation.
