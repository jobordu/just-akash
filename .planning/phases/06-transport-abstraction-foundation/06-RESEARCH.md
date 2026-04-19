# Phase 6: Transport Abstraction Foundation — Research

**Researched:** 2026-04-18
**Domain:** Python transport abstraction layer + Akash lease-shell WebSocket protocol discovery
**Confidence:** HIGH (architecture patterns), MEDIUM (Akash-specific endpoint details — confirmed via prior milestone research)

---

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LSHL-01 | Protocol implementation derived from reverse-engineered console.akash.network WebSocket handshake | Protocol note output; traffic inspection guide in `## Architecture Patterns` |
| TRNS-02 | User can opt into SSH transport via `--transport ssh` flag on exec, inject, and connect | SSHTransport class + CLI flag wiring; all three subparsers need `--transport` argument added |

</phase_requirements>

## Summary

Phase 6 is a **foundations phase** — it produces zero new user-visible features but enables every phase that follows. Two concrete deliverables:

1. **Protocol note** — A document (`PROTOCOL.md`) capturing the lease-shell WebSocket endpoint URL, auth header format, and message frame schema, derived from inspecting console.akash.network traffic. This is BLOCKING for Phase 7.

2. **Transport abstraction package** — `just_akash/transport/` with a `Transport` abstract base class, a working `SSHTransport` that wraps today's SSH subprocess logic, and a `LeaseShellTransport` stub (placeholder, not functional yet). All v1.4 commands continue to work unchanged through `SSHTransport`.

The project already has rich prior milestone research (`.planning/research/`) covering architecture, stack, features, and pitfalls. Phase 6 research consolidates what is needed specifically for this phase.

**Primary recommendation:** Create `just_akash/transport/` with `base.py`, `ssh.py`, and `lease_shell.py` (stub). Wire `--transport ssh` into `exec`, `inject`, `connect` CLI argument parsers. Extract SSH helpers from `api.py` into `ssh.py`. Perform protocol traffic inspection and write `PROTOCOL.md`.

---

## Standard Stack

### Core (Phase 6)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `abc` | stdlib | Abstract base class for `Transport` | No external dep needed; `ABC` + `abstractmethod` is idiomatic Python |
| Python `dataclasses` | stdlib | `TransportConfig` value object | Clean, type-annotated, zero overhead |
| `websockets` | >=16.0 | WebSocket client (stub import in `LeaseShellTransport`) | Already in prior research; needed by Phase 7; declare in `pyproject.toml` now |
| `pytest` | >=9.0.3 | Unit testing transport layer | Already in project |

### Dependencies to Add in pyproject.toml (Phase 6)

```toml
[project]
dependencies = [
    "websockets>=16.0",
    "pexpect>=4.9.0",
]

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-cov>=7.1.0",
    "pyright>=1.1.399",
    "ruff>=0.15.10",
    "types-pexpect>=4.9.0.20260127",
]
```

Note: `pexpect` is declared now (used in Phase 9) so the dependency is present before it is needed. Both are pure Python / PyPI; no build steps.

### NOT Needed in Phase 6

| Library | Phase | Reason |
|---------|-------|--------|
| `asyncio` (wrapping) | Phase 7 | `LeaseShellTransport` is a stub in Phase 6; no real async calls |
| `pty` / `pexpect` (active use) | Phase 9 | Interactive shell is Phase 9 scope |
| `grpcio` | v2.0 | AEP-37 LeaseRPC not yet deployed |

---

## Architecture Patterns

### Package Structure to Create

```
just_akash/
├── transport/
│   ├── __init__.py        (exports: Transport, TransportConfig, SSHTransport, LeaseShellTransport)
│   ├── base.py            (Transport ABC + TransportConfig dataclass)
│   ├── ssh.py             (SSHTransport — wraps existing api.py SSH helpers)
│   └── lease_shell.py     (LeaseShellTransport stub — raises NotImplementedError)
├── api.py                 (unchanged except: SSH helpers stay here for backward compat; no extraction needed in Phase 6)
└── cli.py                 (modified: add --transport flag, wire SSHTransport)
```

**Key design decision:** Do NOT extract SSH helpers from `api.py` in Phase 6. Keep `_find_ssh_key`, `_build_ssh_cmd`, `_extract_ssh_info` in `api.py`. `SSHTransport.prepare()` imports them from there. Extraction is a Phase 6 goal only if it does not break tests — since the existing test suite tests api.py helpers directly, extraction risks coverage regressions. The transport package in Phase 6 calls into api.py; full migration can happen in a later phase.

### Transport Base Class

```python
# just_akash/transport/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransportConfig:
    """Immutable configuration for a transport instance."""
    dseq: str
    api_key: str
    deployment: dict[str, Any] = field(default_factory=dict)
    console_url: str = "https://console-api.akash.network"
    service_name: str | None = None
    ssh_key_path: str | None = None  # optional override for SSH


class Transport(ABC):
    """
    Abstract transport interface for shell-dependent commands.

    All transports MUST be usable via:
        transport = SomeTransport(config)
        transport.prepare()        # validate + setup
        rc = transport.exec(cmd)   # run remote command
        transport.inject(path, content)  # write file
        transport.connect()        # interactive shell

    Phase 6 only implements SSHTransport fully.
    LeaseShellTransport is a stub (raises NotImplementedError).
    """

    @abstractmethod
    def prepare(self) -> None:
        """Validate transport can be used; raise RuntimeError if not."""
        ...

    @abstractmethod
    def exec(self, command: str) -> int:
        """Execute command remotely; return exit code."""
        ...

    @abstractmethod
    def inject(self, remote_path: str, content: str) -> None:
        """Write content to remote_path on the container."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Open interactive shell session (never returns)."""
        ...

    @abstractmethod
    def validate(self) -> bool:
        """Return True if transport can be used with current deployment."""
        ...
```

**Why synchronous interface in Phase 6:** `SSHTransport` wraps synchronous `subprocess` calls. Making the base interface `async` now would require wrapping every sync call with `asyncio.to_thread()`, adding complexity for no benefit in Phase 6. Phase 7 will evaluate whether to promote the interface to async; the stub `LeaseShellTransport` can document this as a future concern.

### SSHTransport Implementation

```python
# just_akash/transport/ssh.py

import os
import subprocess
from .base import Transport, TransportConfig
from just_akash.api import _build_ssh_cmd, _extract_ssh_info, _find_ssh_key


class SSHTransport(Transport):
    """SSH transport — exact v1.4 behavior, wrapped in Transport interface."""

    def __init__(self, config: TransportConfig) -> None:
        self._config = config
        self._ssh_info: dict | None = None
        self._key_path: str | None = None

    def prepare(self) -> None:
        self._ssh_info = _extract_ssh_info(self._config.deployment)
        if not self._ssh_info:
            from just_akash.cli import NO_SSH_MSG
            raise RuntimeError(NO_SSH_MSG)
        self._key_path = _find_ssh_key(self._config.ssh_key_path or "")
        if not self._key_path:
            raise RuntimeError("No SSH key found. Specify with --key")

    def exec(self, command: str) -> int:
        ssh_cmd = _build_ssh_cmd(self._ssh_info, self._key_path)
        ssh_cmd.append(command)
        result = subprocess.run(ssh_cmd, text=True)
        return result.returncode

    def inject(self, remote_path: str, content: str) -> None:
        ssh_cmd = _build_ssh_cmd(self._ssh_info, self._key_path)
        # mkdir -p
        subprocess.run(ssh_cmd + [f"mkdir -p $(dirname {remote_path})"],
                       capture_output=True, text=True, check=True)
        # write content
        result = subprocess.run(ssh_cmd + [f"cat > {remote_path}"],
                                input=content, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to write secrets: {result.stderr.strip()}")
        # chmod
        subprocess.run(ssh_cmd + [f"chmod 600 {remote_path}"],
                       capture_output=True, text=True)

    def connect(self) -> None:
        ssh_cmd = _build_ssh_cmd(self._ssh_info, self._key_path)
        os.execvp("ssh", ssh_cmd)

    def validate(self) -> bool:
        return _extract_ssh_info(self._config.deployment) is not None
```

### LeaseShellTransport Stub

```python
# just_akash/transport/lease_shell.py

from .base import Transport, TransportConfig


class LeaseShellTransport(Transport):
    """
    Lease-shell WebSocket transport stub (Phase 6).

    Will be implemented in Phase 7.
    Endpoint, auth header format, and frame schema are documented in
    docs/PROTOCOL.md after Phase 6 traffic inspection.
    """

    def __init__(self, config: TransportConfig) -> None:
        self._config = config

    def prepare(self) -> None:
        raise NotImplementedError("LeaseShellTransport not implemented until Phase 7")

    def exec(self, command: str) -> int:
        raise NotImplementedError("LeaseShellTransport not implemented until Phase 7")

    def inject(self, remote_path: str, content: str) -> None:
        raise NotImplementedError("LeaseShellTransport not implemented until Phase 7")

    def connect(self) -> None:
        raise NotImplementedError("LeaseShellTransport not implemented until Phase 7")

    def validate(self) -> bool:
        # Stub — cannot validate without real implementation
        return False
```

### CLI Wiring Pattern (--transport flag)

Add to `exec`, `inject`, `connect` subparsers:

```python
# In cli.py — for exec_p, inject_p, connect_p subparsers:
<subparser>.add_argument(
    "--transport",
    choices=["ssh", "lease-shell"],
    default="ssh",
    dest="transport",
    help="Transport to use (default: ssh; lease-shell available in v1.5)",
)
```

CLI handler pattern (exec example):

```python
elif args.command == "exec":
    from .api import AkashConsoleAPI
    from .transport import make_transport

    try:
        client = AkashConsoleAPI(_require_api_key())
        dseq = _resolve_deployment(client, args.dseq)
        deployment = client.get_deployment(dseq)
        transport = make_transport(
            args.transport,
            dseq=dseq,
            api_key=_require_api_key(),
            deployment=deployment,
            ssh_key_path=args.key,
        )
        transport.prepare()
        rc = transport.exec(args.remote_cmd)
        sys.exit(rc)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

Factory function in `__init__.py`:

```python
# just_akash/transport/__init__.py

from .base import Transport, TransportConfig
from .ssh import SSHTransport
from .lease_shell import LeaseShellTransport


def make_transport(transport_name: str, **kwargs) -> Transport:
    """Factory: return the appropriate Transport for the given name."""
    config = TransportConfig(**kwargs)
    if transport_name == "ssh":
        return SSHTransport(config)
    elif transport_name == "lease-shell":
        return LeaseShellTransport(config)
    raise ValueError(f"Unknown transport: {transport_name!r} (expected 'ssh' or 'lease-shell')")
```

### Protocol Reverse-Engineering Pattern

The protocol note must be derived from observing console.akash.network WebSocket traffic. Recommended approach:

**Browser DevTools (no tooling needed):**
1. Open console.akash.network in Chrome/Firefox
2. Open DevTools → Network tab → filter by "WS" (WebSocket)
3. Navigate to a deployment and open its shell
4. Observe the WebSocket connection: URL, headers in the handshake request, and messages in the "Messages" sub-tab
5. Document: endpoint URL pattern, `x-api-key` or `Authorization` header, frame types (text/binary), message schema

**Expected findings based on prior research (MEDIUM confidence, must be verified):**
- Endpoint: `wss://console-api.akash.network/v1/deployments/{dseq}/shell` or similar
- Auth: `x-api-key: {AKASH_API_KEY}` header (same pattern as REST API)
- Frame format: binary frames for terminal I/O, JSON text frames for control messages
- Message schema: `{type: "stdin"|"stdout"|"stderr"|"exit"|"resize", data: ...}`

**PROTOCOL.md must document:**
1. Exact WebSocket endpoint URL (with placeholder for dseq/provider values)
2. HTTP headers sent in WebSocket upgrade request (auth, content-type, etc.)
3. Message frame schema (text vs binary, JSON structure for each message type)
4. Connection lifecycle (how to open, how to close, error responses)
5. Service name parameter (how the shell identifies which container service)

### Anti-Patterns to Avoid

- **Don't make the base interface async in Phase 6.** SSHTransport is synchronous. Async wrapping adds complexity before Phase 7 validates it is needed.
- **Don't extract SSH helpers from api.py in Phase 6.** Existing tests test api.py helpers directly; extraction risks regressions without corresponding benefit.
- **Don't implement real WebSocket code in LeaseShellTransport.** It is a stub. Real code goes in Phase 7 after PROTOCOL.md is written.
- **Don't change CLI behavior.** When `--transport` defaults to `ssh`, the behavior must be byte-for-byte identical to v1.4.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Abstract interface enforcement | Custom metaclass | Python `ABC` + `abstractmethod` | Standard, well-understood, pyright-compatible |
| SSH subprocess management | Manual process lifecycle | Existing `subprocess` + `os.execvp` pattern (already in project) | Already battle-tested in v1.4 |
| WebSocket protocol framing | Manual TCP socket writes | `websockets>=16.0` | Handles masking, fragmentation, ping/pong, RFC compliance |
| TTY terminal control | Manual `ioctl` calls | `pexpect` + `pty` stdlib | Handles raw mode, signal forwarding, window resize |

---

## Common Pitfalls

### Pitfall 1: Breaking v1.4 Command Behavior

**What goes wrong:** `SSHTransport` replicates SSH logic slightly differently from the original; edge cases in `_extract_ssh_info`, `_find_ssh_key`, or `_build_ssh_cmd` produce different behavior.

**Prevention:** `SSHTransport` must call the SAME api.py helpers as the current CLI handlers (`_extract_ssh_info`, `_find_ssh_cmd`, `_find_ssh_key`). Do NOT reimplement them. The test suite has 357 tests — if any fail after Phase 6, there is a regression.

**Verification:** Run full pytest suite before commit. All 357 existing tests must pass.

### Pitfall 2: Transport Flag Changes Default Behavior

**What goes wrong:** Adding `--transport` with a `default="ssh"` still changes behavior if the CLI handler logic changes.

**Prevention:** The new CLI handler path for `--transport ssh` must produce identical output to the v1.4 handler. Verify with existing CLI test cases.

### Pitfall 3: Protocol Note Based on Stale/Incorrect Assumptions

**What goes wrong:** PROTOCOL.md is written from documentation or guesswork instead of live traffic inspection; Phase 7 discovers the actual format is different and must re-research.

**Prevention:** PROTOCOL.md MUST be based on actual browser DevTools observation of console.akash.network, not documentation. The document should include a "Observed at: [date]" timestamp.

### Pitfall 4: pyproject.toml Missing New Dependencies

**What goes wrong:** `websockets` and `pexpect` are used in later phases but not declared, causing `ModuleNotFoundError` for users who install from PyPI.

**Prevention:** Declare `websockets>=16.0` and `pexpect>=4.9.0` in `[project.dependencies]` in Phase 6, even though they are only actively used in Phases 7 and 9. Install via `uv sync`.

---

## Validation Architecture

### Test Framework
| Config | Framework | Quick run | Full suite |
|--------|-----------|-----------|------------|
| `pytest.ini_options` in `pyproject.toml` | Pytest | `pytest -x --tb=short` | `pytest --tb=short` |

**Quick run command:** `pytest -x --tb=short`
**Full suite command:** `pytest --tb=short`

### Wave 0 Test Scaffolding

Phase 6 requires creating `tests/test_transport.py` before implementation starts. This file defines:
- Test stubs for `Transport` abstract class instantiation (should fail with `TypeError`)
- Test stubs for `SSHTransport` with mocked api.py helpers
- Regression test: existing CLI commands produce same output before/after transport wiring

### Per-Task Verification Map

| Task | Test Type | Notes |
|------|-----------|-------|
| Create `transport/` package + `base.py` | unit | Test abstract base prevents direct instantiation |
| Implement `SSHTransport` | unit | Mock `_extract_ssh_info`, `_find_ssh_key`, `_build_ssh_cmd` |
| Implement `LeaseShellTransport` stub | unit | Verify all methods raise `NotImplementedError` |
| Add `--transport ssh` to CLI flags | integration | Existing CLI tests pass; `--transport ssh` routes through `SSHTransport` |
| Add dependencies to pyproject.toml | smoke | `uv sync` succeeds; `import websockets` succeeds |
| Write PROTOCOL.md | manual | Inspect console.akash.network traffic; document findings |

---

## Open Questions

1. **Exact WebSocket endpoint URL**
   - What we know: Console API base URL is `https://console-api.akash.network`; prior research hypothesizes `/v1/leases/{dseq}/shell` or `/v1/deployments/{dseq}/shell`
   - What's unclear: The actual path, whether it routes through provider directly or via Console API proxy
   - Recommendation: Confirm via browser DevTools during PROTOCOL.md authoring

2. **Service name parameter**
   - What we know: Akash deployments can have multiple services; lease-shell needs to target one
   - What's unclear: Whether Console API shell endpoint auto-selects the first service, or requires explicit `?service=` param
   - Recommendation: Observe in browser traffic inspection; default to first service if multiple

3. **Sync vs async Transport interface**
   - What we know: `SSHTransport` is sync; `LeaseShellTransport` will need async WebSocket I/O
   - What's unclear: Whether to make the base interface async now or defer to Phase 7
   - Recommendation: Keep sync in Phase 6 (documented in Anti-Patterns); Phase 7 will assess

---

## Sources

### Primary (HIGH confidence)
- `.planning/research/ARCHITECTURE.md` — Transport abstraction design, component structure, integration points
- `.planning/research/STACK.md` — websockets + pexpect library selection rationale, versions
- `.planning/research/PITFALLS.md` — Critical pitfalls: token expiry, TTY cleanup, connection teardown
- `.planning/research/FEATURES.md` — Feature scope, what belongs in v1.5 vs deferred
- `.planning/research/SUMMARY.md` — Confidence assessment, gaps to address in Phase 2 (now Phase 7)
- `just_akash/api.py` — SSH helpers (`_extract_ssh_info`, `_find_ssh_key`, `_build_ssh_cmd`) to reuse
- `just_akash/cli.py` — Current command dispatch patterns to mirror in refactored handlers
- `pyproject.toml` — Dependency declaration location; test framework config

### Secondary (MEDIUM confidence)
- [Akash Console API swagger](https://console-api.akash.network/v1/swagger) — REST API patterns suggest WebSocket endpoint naming convention
- [websockets 16.0 PyPI](https://pypi.org/project/websockets/) — Library version and installation
- [pexpect 4.9.0 PyPI](https://pypi.org/project/pexpect/) — Interactive PTY library

---

## Metadata

**Confidence breakdown:**
- Package structure and base class: HIGH — standard Python ABC pattern, well-established
- SSHTransport implementation: HIGH — directly wraps existing tested code
- CLI flag wiring: HIGH — simple argparse addition, same pattern as existing flags
- Protocol note content: LOW → MEDIUM (after traffic inspection) — Akash-specific, must be verified live
- pyproject.toml dependency additions: HIGH — websockets + pexpect are on PyPI, versions confirmed

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (30 days; library versions stable; endpoint URL needs re-validation if Akash upgrades Console API)
