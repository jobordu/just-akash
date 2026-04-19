---
phase: "10"
title: "Default Transport Switch and Fallback"
status: research-complete
researched_at: "2026-04-19"
---

# Phase 10 Research: Default Transport Switch and Fallback

## Goal

Switch the default transport for `connect`, `exec`, and `inject` from `"ssh"` to `"lease-shell"`.
Add auto-fallback: when lease-shell is not available (`transport.validate()` returns False),
silently fall back to SSH and emit a notice to stderr.

Requirements:
- TRNS-01: `just connect`, `just exec`, `just inject` all default to lease-shell (no `--transport` flag needed)
- TRNS-03: If lease-shell is unavailable (no active lease / no hostUri), fall back to SSH automatically

---

## Codebase Findings

### 1. Current Transport Defaults (`just_akash/cli.py`)

All three commands have `--transport` with `default="ssh"`:

```python
connect_p.add_argument("--transport", choices=["ssh", "lease-shell"], default="ssh", ...)
exec_p.add_argument("--transport",    choices=["ssh", "lease-shell"], default="ssh", ...)
inject_p.add_argument("--transport",  choices=["ssh", "lease-shell"], default="ssh", ...)
```

Change: `default="ssh"` → `default="lease-shell"` in all three.

### 2. Command Dispatch Pattern

Each command already has an `if args.transport == "lease-shell": ... else: # SSH` branch.
The fallback logic fits naturally in the "default" path.

Current structure for `exec` (representative):

```python
if args.transport == "lease-shell":
    # lease-shell path
else:
    # SSH path (v1.4 behavior)
```

After change, when `default="lease-shell"`, the lease-shell path runs by default.

### 3. Fallback Detection: `validate()`

`LeaseShellTransport.validate()` already exists and checks for `hostUri` in lease data:

```python
def validate(self) -> bool:
    leases = self._config.deployment.get("leases", [])
    if not leases or not isinstance(leases, list):
        return False
    lease = leases[0]
    provider = lease.get("provider", {})
    return bool(provider.get("hostUri") or provider.get("host_uri"))
```

This is the correct gate: `validate()` = False means the deployment has no active lease with a
provider hostUri, so lease-shell cannot be used.

### 4. Fallback Pattern

When `args.transport == "lease-shell"` (now the default) but `transport.validate()` is False:
print a notice to stderr and fall through to SSH.

```python
transport = make_transport("lease-shell", dseq=dseq, api_key=..., deployment=deployment)
if not transport.validate():
    print("Notice: lease-shell not available; falling back to SSH.", file=sys.stderr)
    # fall through to SSH branch
else:
    transport.prepare()
    transport.exec(args.remote_cmd)
    sys.exit(rc)
```

To avoid code duplication, the cleanest approach is to restructure each command handler as:

```
use_lease_shell = (args.transport == "lease-shell")
if use_lease_shell:
    transport = make_transport(...)
    if not transport.validate():
        use_lease_shell = False
        print("Notice: lease-shell not available; falling back to SSH.", file=sys.stderr)

if use_lease_shell:
    # lease-shell execution
else:
    # SSH path
```

### 5. `NO_SSH_MSG` — Outdated Content

`cli.py` lines 24-37:

```python
NO_SSH_MSG = (
    ...
    "The Akash Console API does not support lease-shell.\n"
    "SSH is the only way to connect, exec, or inject secrets."
)
```

The last two lines are false as of v1.5. Remove them. The message is still valid
(it's shown when no SSH port is exposed) — just strip the outdated lease-shell claim.

`_require_ssh()` still uses `NO_SSH_MSG` — that function only runs in the SSH fallback path,
so the message remains relevant there.

### 6. Help Text Updates

argparse help for `--transport`:
- Current: `"Transport to use: 'ssh' (default) or 'lease-shell' (available in v1.5)"`
- New: `"Transport to use: 'lease-shell' (default) or 'ssh'"`

Command-level help text (e.g., "requires SSH in SDL") should be updated to remove SSH-mandatory
language since lease-shell no longer requires SSH.

### 7. `transport.prepare()` Call Flow

After `validate()` passes, `prepare()` must still be called — it sets `_ws_url` and `_service`.
The existing code calls `transport.prepare()` before `transport.exec()` / `transport.connect()`.
This ordering is correct; no changes needed.

### 8. `inject` Command Special Case

`inject` resolves dseq before the transport branch. The fallback pattern works the same way:
create transport, call `validate()`, fall back if needed.

For the SSH inject fallback, `_require_ssh()` is called — that requires SSH to be present,
so the fallback path naturally exits with the `NO_SSH_MSG` if SSH is also absent.

---

## Test Strategy

### New test file: `tests/test_default_transport.py`

**Wave 0 stubs (RED before implementation):**

1. `test_connect_defaults_to_lease_shell` — argparse `connect` command has `default="lease-shell"`
2. `test_exec_defaults_to_lease_shell` — argparse `exec` command has `default="lease-shell"`
3. `test_inject_defaults_to_lease_shell` — argparse `inject` command has `default="lease-shell"`
4. `test_exec_fallback_to_ssh_when_validate_false` — when `transport.validate()` returns False,
   SSH path runs; notice printed to stderr
5. `test_connect_fallback_to_ssh_when_validate_false` — same for connect
6. `test_inject_fallback_to_ssh_when_validate_false` — same for inject
7. `test_no_ssh_msg_does_not_mention_lease_shell` — `NO_SSH_MSG` no longer contains
   "does not support lease-shell"
8. `test_exec_uses_lease_shell_when_validate_true` — when validate() is True, lease-shell runs

### Existing tests that need updating

- `tests/test_transport_cli_integration.py`:
  - Tests that check `default="ssh"` or explicitly test SSH-default behavior must be updated.
  - Tests using `--transport lease-shell` remain valid.

- `tests/test_cli.py`:
  - Any argparse default assertions must be updated.

---

## Implementation Plan (for Planner)

### Plan 10-01: Change Defaults + Update `NO_SSH_MSG` (cli.py only)

Files: `just_akash/cli.py`

Changes:
1. `default="ssh"` → `default="lease-shell"` in all three `--transport` arguments
2. Remove the two outdated lines from `NO_SSH_MSG`
3. Update `--transport` help text for all three commands
4. Update command-level help text (remove "requires SSH in SDL" language)

No behavior change yet (existing `--transport ssh` path still works; default path unchanged
because tests pass `--transport` explicitly).

### Plan 10-02: Add Fallback Logic (cli.py)

Files: `just_akash/cli.py`

Changes:
1. Restructure `connect`, `exec`, and `inject` handlers to:
   a. Create `LeaseShellTransport` when `args.transport == "lease-shell"`
   b. Call `transport.validate()`; if False, print fallback notice, use SSH path
   c. Otherwise proceed with lease-shell path
2. Remove the `transport.prepare()` stub comment (no longer Phase 6 placeholder)

### Plan 10-03: Wave 0 Tests → GREEN

Files: `tests/test_default_transport.py` (new), update `tests/test_transport_cli_integration.py`

Changes:
1. Create `tests/test_default_transport.py` with all 8 stubs (Wave 0 RED)
2. Implement changes from 10-01 + 10-02 (should already be done; tests go GREEN)
3. Update `test_transport_cli_integration.py` tests that expected `default="ssh"`

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Existing SSH tests fail after default switch | Medium | Update tests in Plan 10-03 |
| `validate()` called before dseq resolved | Low | dseq resolved before `make_transport()` |
| `NO_SSH_MSG` change breaks SSH error path | Low | Message still valid; only removes lease-shell claim |
| `inject` fallback double-validates SSH | Low | `_require_ssh()` handles missing SSH port cleanly |

---

## RESEARCH COMPLETE
