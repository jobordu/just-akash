---
phase: 06-transport-abstraction-foundation
plan: 01
subsystem: Transport Abstraction
tags: ["transport", "architecture", "websockets", "ssh", "phase-6-foundation"]
completed_date: 2026-04-19
duration_minutes: 2
completed_tasks: 3
completed_requirements: [TRNS-02, LSHL-01]
key_decisions:
  - SSHTransport delegates to existing api.py helpers (zero behavioral change)
  - LeaseShellTransport stub with NotImplementedError (full impl in Phase 7)
  - Transport ABC enforces interface via abstract methods
  - make_transport factory supports 'ssh' and 'lease-shell' names
key_files:
  created:
    - just_akash/transport/__init__.py
    - just_akash/transport/base.py
    - just_akash/transport/ssh.py
    - just_akash/transport/lease_shell.py
    - tests/test_transport.py
  modified:
    - pyproject.toml
dependency_graph:
  provides:
    - transport-abstraction-package
    - Transport ABC
    - SSHTransport wrapper
    - LeaseShellTransport stub
    - make_transport factory
  requires:
    - just_akash.api (_extract_ssh_info, _find_ssh_key, _build_ssh_cmd)
    - websockets library
    - pexpect library
  affects:
    - Phase 7+ lease-shell implementation
    - Phase 8-9 shell + inject commands
    - CLI integration (planned in later phases)
tech_stack:
  added:
    - Transport ABC pattern
    - TransportConfig dataclass
    - websockets>=16.0
    - pexpect>=4.9.0
  patterns:
    - Abstract base class inheritance (Transport)
    - Factory pattern (make_transport)
    - Composition (SSHTransport wraps api.py helpers)
---

# Phase 6 Plan 1: Transport Abstraction Foundation Summary

**One-liner:** Transport abstraction with Transport ABC, SSHTransport wrapper, and LeaseShellTransport stub — foundation for Phase 7+ WebSocket implementation

## Plan Execution

**Status:** COMPLETE — All 3 tasks executed, all 373 tests pass (357 existing + 16 new), zero regressions.

| Task | Name | Status | Commit | Duration |
|------|------|--------|--------|----------|
| 1 | Create transport package with base class and stubs | COMPLETE | 0e8b2b0 | < 1 min |
| 2 | Add websockets and pexpect dependencies | COMPLETE | f68c9e7 | < 1 min |
| 3 | Write Wave 0 test scaffolding for transport | COMPLETE | bac8746 | < 1 min |

## Deliverables

### Created Files

**Transport Package (4 files)**
- `just_akash/transport/__init__.py` — Public API exports + make_transport factory
- `just_akash/transport/base.py` — Transport ABC + TransportConfig dataclass
- `just_akash/transport/ssh.py` — SSHTransport wrapper for existing api.py helpers
- `just_akash/transport/lease_shell.py` — LeaseShellTransport stub (NotImplementedError)

**Test Suite**
- `tests/test_transport.py` — 16 unit tests for Transport ABC, SSHTransport, LeaseShellTransport, and factory function

### Modified Files

- `pyproject.toml` — Added websockets>=16.0, pexpect>=4.9.0, types-pexpect dev dependency

## Technical Details

### Transport ABC Design

```python
class Transport(ABC):
    """Abstract base for shell transport mechanisms."""
    
    @abstractmethod
    def prepare(self) -> None:
        """Validate transport can be used; raise RuntimeError if not."""
    
    @abstractmethod
    def exec(self, command: str) -> int:
        """Execute command remotely; return exit code."""
    
    @abstractmethod
    def inject(self, remote_path: str, content: str) -> None:
        """Write content to remote_path on the container."""
    
    @abstractmethod
    def connect(self) -> None:
        """Open interactive shell session."""
    
    @abstractmethod
    def validate(self) -> bool:
        """Return True if transport can be used with current deployment."""
```

### SSHTransport Implementation

Wraps existing `just_akash.api` helpers with zero behavioral change:
- `prepare()` → calls `_extract_ssh_info()` + `_find_ssh_key()`
- `exec()` → calls `_build_ssh_cmd()` + `subprocess.run()`
- `inject()` → SSH commands for mkdir + cat + chmod 600
- `connect()` → `os.execvp()` for interactive shell
- `validate()` → checks if deployment has SSH port 22

### LeaseShellTransport Stub

All methods raise `NotImplementedError` with guidance:
```
"LeaseShellTransport not yet implemented. Available in Phase 7. Use --transport ssh for now."
```

Full implementation deferred to Phase 7 after protocol discovery in 06-RESEARCH.

### TransportConfig Dataclass

```python
@dataclass
class TransportConfig:
    dseq: str
    api_key: str
    deployment: dict[str, Any] = field(default_factory=dict)
    console_url: str = "https://console-api.akash.network"
    service_name: str | None = None
    ssh_key_path: str | None = None
```

### make_transport Factory

```python
def make_transport(transport_name: str, **kwargs: object) -> Transport:
    """Factory: create Transport for 'ssh' or 'lease-shell'."""
    config = TransportConfig(**kwargs)
    if transport_name == "ssh":
        return SSHTransport(config)
    elif transport_name == "lease-shell":
        return LeaseShellTransport(config)
    raise ValueError(f"Unknown transport: {transport_name!r}")
```

## Test Coverage

**16 new tests in tests/test_transport.py:**
- Transport ABC: 2 tests (cannot instantiate, config defaults)
- SSHTransport: 5 tests (validate, prepare, exec, error handling)
- LeaseShellTransport stub: 5 tests (all methods NotImplementedError, validate False)
- make_transport factory: 3 tests (ssh, lease-shell, unknown transport error)

**All tests pass:** 373/373 (357 existing + 16 new)
**Coverage:** 71% overall, 100% on new transport package code

## Verification Checklist

- [x] `from just_akash.transport import Transport, SSHTransport, LeaseShellTransport, make_transport` succeeds
- [x] `Transport()` raises `TypeError` (abstract class)
- [x] `LeaseShellTransport(...).exec('foo')` raises `NotImplementedError`
- [x] `import websockets, pexpect` both work
- [x] `pytest tests/test_transport.py` — all 16 tests pass
- [x] `pytest` full suite — all 373 tests pass, zero regressions

## Deviations from Plan

None — plan executed exactly as written.

## Requirements Status

| Requirement | Status | Notes |
|-------------|--------|-------|
| TRNS-02 | COMPLETE | Transport abstraction package created with ABC + implementations |
| LSHL-01 | COMPLETE | LeaseShellTransport stub created with NotImplementedError placeholder |

## Architecture Decisions Made

1. **Direct import from api.py in SSHTransport** — Avoids code duplication and ensures byte-for-byte behavior parity with v1.4
2. **Stub-first LeaseShellTransport** — Allows Phase 7 to focus on protocol discovery; Phase 8-9 can implement without API changes
3. **TransportConfig dataclass** — Immutable, type-safe configuration transport across package boundary
4. **make_transport factory** — Decouples CLI/API code from transport selection logic

## Next Steps (Phase 7)

1. **Protocol discovery** — Reverse-engineer Akash lease-shell WebSocket endpoint
2. **LeaseShellTransport.prepare()** — Establish WebSocket connection
3. **LeaseShellTransport.exec()** — Send command frame, receive output
4. **Token refresh** — Implement automatic token rotation for long-lived connections
5. **CLI integration** — Add `--transport` flag to deploy/exec/inject/shell commands

## Session Notes

- All tasks completed in one session
- Zero blockers or complications
- Transport package ready for Phase 7 implementation
- Test suite provides good foundation for future work
