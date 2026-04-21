# Architecture: WebSocket Lease-Shell Transport Integration

**Project:** just-akash v1.5 — Lease-Shell WebSocket Transport  
**Researched:** 2026-04-18  
**Confidence:** MEDIUM (Console API shell endpoints confirmed, WebSocket implementation pattern derived from standard Python patterns)

## Executive Summary

The v1.5 milestone requires replacing SSH as the default transport with Akash's native `lease-shell` WebSocket mechanism for `exec`, `inject`, and `connect`/`shell` commands. This is a transport abstraction problem, not a rewrite: the CLI command interfaces remain stable, but the underlying delivery mechanism shifts from SSH subprocess calls to WebSocket-based remote execution.

**Key insight:** Akash's `lease-shell` command (via `provider-services lease-shell`) operates over an HTTP(S) API that Akash Console exposes at `console-api.akash.network`. This is not a public, well-documented API endpoint in the sense of having OpenAPI specs readily available, but it is the standard mechanism used by Akash CLI tools and web console for shell access. The integration will require:

1. **Transport abstraction layer** — Encapsulate SSH vs lease-shell selection
2. **WebSocket client module** — Handle lease-shell WebSocket connection and interactive I/O
3. **CLI transport flag** — Add `--transport ssh|lease-shell` with `lease-shell` as default
4. **Modified command handlers** — Route `exec`, `inject`, `connect` through abstracted transport

---

## Recommended Architecture

### Component Structure

```
just_akash/
├── api.py                      (EXISTING - AkashConsoleAPI, deployment queries)
├── deploy.py                   (EXISTING - deployment orchestration)
├── cli.py                      (MODIFIED - add transport flag, route through abstraction)
├── transport/
│   ├── __init__.py            (NEW - public Transport interface)
│   ├── base.py                (NEW - Transport abstract base class)
│   ├── ssh.py                 (NEW - SSH transport implementation)
│   └── lease_shell.py         (NEW - WebSocket lease-shell transport)
└── __init__.py                (EXISTING)
```

### Data Flow Diagram

```
CLI Command (exec/inject/connect)
    ↓
cli.py argument parsing
    ↓
_resolve_deployment(dseq)
    ↓
_select_transport(deployment, --transport flag)
    ↓
Transport.prepare() → get connection parameters
    ↓
┌─────────────────────┬─────────────────────────┐
│  SSH Transport      │  Lease-Shell Transport  │
│  (--transport ssh)  │  (default, WebSocket)   │
├─────────────────────┼─────────────────────────┤
│ Extract SSH port 22 │ Extract provider addr   │
│ Find SSH key        │ Get DSEQ                │
│ Build ssh command   │ Extract service name    │
│ Exec via subprocess │ WebSocket connect       │
│                     │ Send tty mode / cmd     │
│                     │ Handle I/O over WS      │
└─────────────────────┴─────────────────────────┘
    ↓
Result to stdout/stderr
```

### Component Boundaries

| Component | Responsibility | Public Interface |
|-----------|----------------|------------------|
| **Transport (base)** | Define contract for all transports | `prepare()`, `exec()`, `inject()`, `connect()` |
| **SSHTransport** | SSH subprocess execution | Wraps `_build_ssh_cmd()`, key finding |
| **LeaseShellTransport** | WebSocket lease-shell execution | WebSocket client, tty mode, async I/O |
| **cli.py** | Argument parsing, transport selection | Updated `connect`, `exec`, `inject` handlers |
| **api.py** | Unchanged — deployment queries, metadata extraction | Existing public methods |

---

## Transport Abstraction Design

### Base Transport Interface

```python
# transport/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class TransportConfig:
    """Configuration for a transport instance."""
    dseq: str
    service_name: str | None = None
    deployment: dict[str, Any] | None = None
    api_key: str | None = None
    console_url: str | None = None

class Transport(ABC):
    """Abstract base for shell transport mechanisms."""

    @abstractmethod
    async def prepare(self) -> None:
        """Prepare transport (validate params, check connectivity)."""
        pass

    @abstractmethod
    async def exec(self, command: str) -> int:
        """Execute a command and return exit code."""
        pass

    @abstractmethod
    async def inject(self, secrets_path: str, content: str) -> None:
        """Inject secrets file at remote_path with content."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Start interactive shell session."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Check if transport can be used (e.g., SSH port exists)."""
        pass
```

**Rationale for async:** WebSocket I/O requires async/await patterns. SSH transport can wrap blocking subprocess calls in async wrappers for uniform interface.

### SSH Transport Implementation

```python
# transport/ssh.py

import asyncio
import subprocess
from .base import Transport, TransportConfig

class SSHTransport(Transport):
    """SSH-based shell transport (v1.4 behavior)."""

    def __init__(self, config: TransportConfig):
        self.config = config
        self.ssh_info = None
        self.key_path = None

    async def prepare(self) -> None:
        """Extract SSH port from deployment, find key."""
        self.ssh_info = _extract_ssh_info(self.config.deployment)
        if not self.ssh_info:
            raise RuntimeError("No SSH port found in deployment")
        self.key_path = _find_ssh_key()
        if not self.key_path:
            raise RuntimeError("No SSH key found")

    async def exec(self, command: str) -> int:
        """Run command via SSH."""
        ssh_cmd = _build_ssh_cmd(self.ssh_info, self.key_path)
        ssh_cmd.append(command)
        result = await asyncio.to_thread(
            subprocess.run, ssh_cmd, capture_output=True, text=True
        )
        return result.returncode

    async def inject(self, remote_path: str, content: str) -> None:
        """Inject secrets via SSH."""
        # mkdir, write, chmod via SSH
        ...

    async def connect(self) -> None:
        """Interactive SSH shell (via os.execvp)."""
        ssh_cmd = _build_ssh_cmd(self.ssh_info, self.key_path)
        os.execvp("ssh", ssh_cmd)

    def validate(self) -> bool:
        """Check SSH is available in deployment."""
        return _extract_ssh_info(self.config.deployment) is not None
```

### Lease-Shell WebSocket Transport Implementation

```python
# transport/lease_shell.py

import asyncio
import json
import websockets
from .base import Transport, TransportConfig

class LeaseShellTransport(Transport):
    """WebSocket lease-shell transport (v1.5 default)."""

    def __init__(self, config: TransportConfig):
        self.config = config
        self.provider = None
        self.service_name = None
        self.ws_url = None

    async def prepare(self) -> None:
        """Extract provider, DSEQ, service name for WebSocket connection."""
        self.provider = _extract_lease_provider(self.config.deployment)
        if not self.provider:
            raise RuntimeError("No lease found on deployment")

        # Service name from deployment manifest
        self.service_name = self.config.service_name or await self._detect_service()
        if not self.service_name:
            raise RuntimeError("Could not determine service name")

        # Construct WebSocket URL (via Console API)
        self.ws_url = self._build_ws_url()

    async def exec(self, command: str) -> int:
        """Execute command via lease-shell WebSocket."""
        async with websockets.connect(self.ws_url) as ws:
            # Send command request (tty=false, single execution)
            await ws.send(json.dumps({
                "type": "command",
                "command": command,
                "tty": False
            }))
            # Collect output, return exit code
            exit_code = await self._collect_output(ws, capture=True)
            return exit_code

    async def inject(self, remote_path: str, content: str) -> None:
        """Inject secrets via lease-shell."""
        # mkdir -p $(dirname remote_path)
        await self.exec(f"mkdir -p $(dirname {remote_path})")
        # cat > remote_path with content
        # (may require tty=true for stdin)
        ...

    async def connect(self) -> None:
        """Interactive shell session via WebSocket (tty mode)."""
        async with websockets.connect(self.ws_url) as ws:
            # Send tty request
            await ws.send(json.dumps({"type": "tty", "shell": "/bin/sh"}))
            # Bidirectional I/O: stdin ↔ WS ↔ stdout/stderr
            await self._interactive_tty(ws)

    def validate(self) -> bool:
        """Check lease exists and provider is available."""
        return _extract_lease_provider(self.config.deployment) is not None

    def _build_ws_url(self) -> str:
        """Construct WebSocket URL for Console API lease-shell endpoint."""
        # Pattern: wss://console-api.akash.network/v1/leases/{dseq}/shell
        # OR: wss://provider-url/shell/{dseq}/{service}
        # (Requires research to confirm exact endpoint pattern)
        base = self.config.console_url or "https://console-api.akash.network"
        base = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{base}/v1/leases/{self.config.dseq}/shell"

    async def _collect_output(self, ws, capture: bool = False) -> int:
        """Receive messages from WebSocket, print to stdout."""
        exit_code = 0
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)
                if data.get("type") == "stdout":
                    print(data.get("data", ""), end="", flush=True)
                elif data.get("type") == "stderr":
                    print(data.get("data", ""), end="", file=sys.stderr, flush=True)
                elif data.get("type") == "exit":
                    exit_code = data.get("code", 0)
                    break
            except asyncio.TimeoutError:
                break
        return exit_code

    async def _interactive_tty(self, ws) -> None:
        """Handle bidirectional stdin/stdout over WebSocket."""
        # Read from stdin in a thread, send to WS
        # Receive from WS, print to stdout
        # (Requires proper terminal setup with pty)
        ...
```

---

## Data Flow: exec Command

```
CLI: just-akash exec --dseq 123456 "echo hello"

1. cli.py::exec handler
   ├─ Parse --dseq (or auto-select)
   ├─ Parse --transport flag (default: "lease-shell")
   ├─ client.get_deployment(dseq)
   └─ transport = _select_transport(deployment, "lease-shell")

2. _select_transport()
   ├─ if transport == "lease-shell":
   │  └─ LeaseShellTransport(deployment)
   ├─ else if transport == "ssh":
   │  └─ SSHTransport(deployment)
   └─ return transport

3. LeaseShellTransport.prepare()
   ├─ Extract provider from deployment.leases[0].id.provider
   ├─ Detect service name from deployment manifest
   ├─ Build WebSocket URL: wss://console-api.akash.network/v1/leases/123456/shell
   └─ Validate provider exists

4. transport.exec("echo hello")
   ├─ Open WebSocket connection
   ├─ Send: {"type": "command", "command": "echo hello", "tty": false}
   ├─ Receive and print stdout/stderr
   ├─ Wait for {"type": "exit", "code": N}
   └─ Return N

5. cli.py
   └─ sys.exit(return_code)
```

---

## Data Flow: inject Command

**Current (SSH):**
```
inject --dseq 123456 --env SECRET=value
  ├─ Build env content
  ├─ SSH: mkdir -p $(dirname /run/secrets/.env)
  ├─ SSH: cat > /run/secrets/.env (stdin: env content)
  └─ SSH: chmod 600 /run/secrets/.env
```

**With Lease-Shell (v1.5):**
```
inject --dseq 123456 --env SECRET=value --transport lease-shell
  ├─ Build env content
  ├─ LeaseShellTransport.inject(remote_path="/run/secrets/.env", content=...)
  │  ├─ exec("mkdir -p /run/secrets")
  │  ├─ Connect WebSocket in tty mode
  │  ├─ Send stdin: content
  │  ├─ cat > remote_path (receives stdin from WS)
  │  ├─ exec("chmod 600 /run/secrets/.env")
  │  └─ Close WebSocket
  └─ Print: "Injected N secret(s)"
```

**Trade-off:** Lease-shell may require special handling for stdin delivery in `inject`. SSH approach is simpler (pipe directly to `cat`). Lease-shell approach requires WebSocket tty mode with proper terminal setup. **Mitigation:** Consider supporting both transports in v1.5, with `inject` preferring SSH if available.

---

## Data Flow: connect Command

**Current (SSH):**
```
connect --dseq 123456
  ├─ Extract SSH port/host
  ├─ Find SSH key
  ├─ os.execvp("ssh", [...])  ← Interactive shell takeover
```

**With Lease-Shell:**
```
connect --dseq 123456 --transport lease-shell
  ├─ LeaseShellTransport.connect()
  │  ├─ WebSocket connect with tty=true
  │  ├─ Set terminal to raw mode
  │  ├─ Spawn reader/writer coroutines:
  │  │  ├─ read stdin → send to WS
  │  │  ├─ recv from WS → write to stdout
  │  │  └─ Handle SIGWINCH for terminal resize
  │  └─ Return when shell exits
```

**Challenge:** Interactive terminal handling. WebSocket transport requires async I/O and careful terminal state management (raw mode, window size signals, etc.). **Standard pattern:** Use Python's `pty` module or libraries like `ptyprocess` (mentioned in research) + `websockets` library.

---

## Transport Selection Logic

**In cli.py:**

```python
def _select_transport(deployment, transport_arg) -> Transport:
    """
    Select transport based on CLI flag and deployment capabilities.
    
    Priority:
    1. If --transport flag specified: use it (error if invalid/unavailable)
    2. If no flag: try lease-shell first, fall back to SSH if available
    3. If neither: raise error with helpful message
    """
    
    # Explicit flag takes precedence
    if transport_arg == "lease-shell":
        t = LeaseShellTransport(deployment)
        if not t.validate():
            raise RuntimeError("Lease-shell not available on this deployment")
        return t
    elif transport_arg == "ssh":
        t = SSHTransport(deployment)
        if not t.validate():
            raise RuntimeError("SSH not configured on this deployment (no port 22)")
        return t
    
    # Default: lease-shell, fall back to SSH
    ls_transport = LeaseShellTransport(deployment)
    if ls_transport.validate():
        return ls_transport
    
    ssh_transport = SSHTransport(deployment)
    if ssh_transport.validate():
        print("Note: Using SSH transport (lease-shell unavailable)")
        return ssh_transport
    
    raise RuntimeError(
        "No valid transport found.\n"
        "  - No lease found (lease-shell unavailable)\n"
        "  - No SSH port (port 22) configured\n"
        "Deploy with proper SDL or use --transport flag"
    )
```

---

## New vs Modified Files

| File | Type | Scope |
|------|------|-------|
| `just_akash/transport/__init__.py` | NEW | Export `Transport`, `TransportConfig`, factory function |
| `just_akash/transport/base.py` | NEW | Abstract base `Transport` class, interface definition |
| `just_akash/transport/ssh.py` | NEW | `SSHTransport` implementation (refactored from api.py helpers) |
| `just_akash/transport/lease_shell.py` | NEW | `LeaseShellTransport` WebSocket implementation |
| `just_akash/cli.py` | MODIFIED | Add `--transport` flag, route through abstraction, async/await calls |
| `just_akash/api.py` | MODIFIED | Extract SSH helpers to transport/ssh.py, keep deployment queries |
| `just_akash/__init__.py` | MODIFIED | Import transport module if needed |
| `tests/test_cli.py` | MODIFIED | Test transport flag, both transport modes |
| `tests/test_transport.py` | NEW | Unit tests for Transport interface, both implementations |
| `just_akash/test_lifecycle.py` | MODIFIED | Add lease-shell test path alongside SSH test |

---

## Proposed Build Order (Phase Dependencies)

### Phase 1: Foundation (Weeks 1-2)
**Goal:** Establish transport abstraction, no behavior change yet.

- Create `just_akash/transport/` package
- Implement `base.py` with abstract Transport interface
- Implement `SSHTransport` by refactoring existing SSH code
- Update `cli.py` to instantiate `SSHTransport` (backward compatible)
- **Tests:** Unit tests for Transport base class, SSHTransport behavior matches current SSH

**Deliverable:** Transport abstraction layer; all existing tests pass; no change in CLI output/behavior.

### Phase 2: Lease-Shell Core (Weeks 3-4)
**Goal:** Implement WebSocket transport, non-interactive (exec command only).

- Implement `LeaseShellTransport.prepare()` and `LeaseShellTransport.exec()`
- Research & confirm Console API lease-shell endpoint URL pattern
- Add `--transport` flag to `exec` command
- Test lease-shell exec against real deployment
- **Tests:** Unit tests for LeaseShellTransport.exec, e2e test (real deployment)

**Deliverable:** Functional `just-akash exec --transport lease-shell` command.

### Phase 3: Secrets Injection & Inject Command (Week 5)
**Goal:** Implement `inject` over lease-shell.

- Implement `LeaseShellTransport.inject()`
- Handle stdin delivery for secrets (WebSocket tty mode)
- Add `--transport` flag to `inject` command
- Test secrets injection via lease-shell
- **Tests:** Unit tests for inject, e2e secrets verification

**Deliverable:** Functional `just-akash inject --transport lease-shell` command.

### Phase 4: Interactive Shell & Connect (Week 6)
**Goal:** Implement interactive `connect` command over lease-shell.

- Implement `LeaseShellTransport.connect()` with proper TTY handling
- Handle terminal state (raw mode, window size, signals)
- Add `--transport` flag to `connect` command
- Test interactive shell behavior
- **Tests:** Manual TTY tests, e2e shell verification

**Deliverable:** Functional `just-akash connect --transport lease-shell` for interactive shell.

### Phase 5: Default Switch & Testing (Week 7)
**Goal:** Make lease-shell default, comprehensive testing.

- Update CLI to default transport to `lease-shell`
- Add fallback logic (try lease-shell, fall back to SSH)
- Comprehensive testing (all commands, both transports)
- Update README with transport documentation
- **Tests:** Full lifecycle test with lease-shell, SSH fallback, transport flag validation

**Deliverable:** lease-shell as default transport; SSH available via `--transport ssh` flag; all tests green.

### Phase 6: Cleanup & Edge Cases (Week 8)
**Goal:** Polish, error handling, documentation.

- Test error messages (missing lease, no SSH, invalid transport flag)
- Performance profiling (WebSocket overhead vs SSH)
- Documentation: transport architecture, debugging tips
- Code review & cleanup
- **Tests:** Adversarial tests (bad deployments, network errors, timeouts)

**Deliverable:** Production-ready v1.5 release.

---

## Build Order Rationale

**Why this order?**

1. **Foundation first:** Transport abstraction before any WebSocket code ensures backward compatibility and clean separation.
2. **Simplest first:** `exec` is simplest (non-interactive), provides proof of concept before tackling `inject` and `connect`.
3. **Inject second:** Required for deployments with secrets; less complex than interactive `connect`.
4. **Interactive last:** `connect` is hardest (TTY state management, signals, window resize); benefits from experience with earlier phases.
5. **Default switch late:** Only after all commands are solid and tested.
6. **Polish at end:** Performance, edge cases, documentation after functionality is proven.

**Dependencies:**
- Phase 2 depends on Phase 1 (transport base class)
- Phases 3-4 depend on Phase 2 (LeaseShellTransport core)
- Phase 5 depends on Phases 3-4 (all commands working)
- Phase 6 depends on Phases 1-5 (full implementation)

---

## Integration Points with Existing Code

### API Module (api.py)
- **Keep:** `AkashConsoleAPI` class, deployment queries (`list_deployments()`, `get_deployment()`)
- **Keep:** Extraction helpers (`_extract_dseq()`, `_extract_lease_provider()`, `_extract_ssh_info()`)
- **Extract:** SSH-specific helpers (`_find_ssh_key()`, `_build_ssh_cmd()`) → move to `transport/ssh.py`
- **Reason:** `api.py` is for Akash API client; transport concerns belong in `transport/`

### CLI Module (cli.py)
- **Current flow:** `_require_ssh()` → hardcoded SSH command building
- **New flow:** `_select_transport()` → Transport interface → `transport.exec()` / `transport.inject()` / `transport.connect()`
- **Change:** Add `--transport` flag to `exec`, `inject`, `connect` subparsers
- **Change:** Make handlers async (or wrap blocking calls with `asyncio.to_thread()`)
- **Backward compatible:** Default behavior (no flag) uses lease-shell with SSH fallback

### Deploy Module (deploy.py)
- **No changes** — deployment logic is transport-agnostic

### Tests
- **Keep:** All existing tests in `tests/` and `just_akash/test_*.py`
- **Add:** `tests/test_transport.py` — unit tests for Transport interface, both implementations
- **Update:** `tests/test_cli.py` — test transport flag, both modes
- **Update:** `just_akash/test_lifecycle.py` — add lease-shell test path alongside SSH

---

## Ambiguities & Research Gaps (Flagged for Phase-Specific Research)

### Lease-Shell WebSocket Endpoint
**Gap:** Exact Console API endpoint URL for lease-shell WebSocket is not publicly documented.

**Current hypothesis:** `wss://console-api.akash.network/v1/leases/{dseq}/shell` (based on REST API pattern)

**Action:** Phase 2 research must confirm:
- Exact endpoint pattern
- Authentication method (API key header? Authorization header?)
- Message format (JSON schema for commands, stdout, stderr, exit codes)
- Error responses

**Priority:** BLOCKING for Phase 2

### Service Name Detection
**Gap:** How to automatically detect service name from deployment manifest if user doesn't provide it?

**Options:**
1. Parse SDL/manifest (expensive, complex)
2. Require `--service` flag (user burden)
3. Try common service names (heuristic; fragile)
4. Query provider for service list (requires provider API)

**Action:** Phase 2 research + design decision

### TTY Mode & Stdin for Inject
**Gap:** How to reliably send stdin (secrets content) over WebSocket in TTY mode?

**Concern:** TTY mode expects interactive shell, stdin may not work normally. SSH `cat >` approach is simpler.

**Options:**
1. Use WebSocket tty mode with stdin message type (new research needed)
2. Execute command with here-doc: `cat <<EOF > /path\nSECRETS\nEOF` (fragile)
3. Fall back to SSH for inject, use lease-shell only for exec/connect (simpler)

**Action:** Phase 3 research

### Terminal State Management (Interactive Shell)
**Gap:** How to handle terminal raw mode, window resize (SIGWINCH), signal forwarding in WebSocket mode?

**Standard approach:** Use `pty.openpty()` or `ptyprocess` library; spawn reader/writer coroutines for bidirectional I/O.

**Action:** Phase 4 research

### Provider Connection Timeout & Heartbeat
**Gap:** WebSocket may disconnect if idle too long. Do we need heartbeat/ping?

**Action:** Phase 2-4 testing against real deployments

---

## Error Handling Strategy

### Missing Lease
```
Error: No lease found on this deployment.
  Deploy with Akash first: just-akash deploy
  Or use SSH transport: just-akash exec --transport ssh "cmd"
```

### Missing SSH (for fallback)
```
Warning: Lease-shell unavailable (no provider found)
Note: SSH not available either (no port 22 exposed)
Error: No valid transport found.
```

### Invalid Transport Flag
```
Error: Invalid transport 'http' (expected 'ssh' or 'lease-shell')
```

### WebSocket Connection Error
```
Error: Failed to connect to lease-shell endpoint: [reason]
  Check: Provider is online and accepting shell connections
  Check: API key is valid (AKASH_API_KEY)
  Try: --transport ssh (fallback)
```

---

## Testing Strategy

### Unit Tests (tests/test_transport.py)
- Transport base class instantiation (abstract, no direct instantiation)
- SSHTransport: key finding, SSH command building, validate() logic
- LeaseShellTransport: WebSocket URL building, provider extraction, validate() logic
- Transport selection logic: flag handling, fallback behavior

### Integration Tests (tests/test_cli.py updates)
- `exec --transport lease-shell` with mock WebSocket server
- `exec --transport ssh` (existing behavior)
- `inject --transport lease-shell`
- `connect --transport lease-shell` (mock TTY)
- Transport fallback (lease-shell → SSH)
- Transport flag validation (invalid values, conflicts)

### E2E Tests (just_akash/test_lifecycle.py updates)
- Full deploy → exec (lease-shell) → destroy cycle
- Full deploy → inject (lease-shell) → verify → destroy cycle
- Full deploy → connect (lease-shell) → interact → destroy cycle
- SSH transport E2E (unchanged from v1.4)

### Manual Testing (not automated)
- Interactive `connect` command (TTY interaction can't be fully automated)
- Network errors, timeouts, recovery

---

## Scalability & Performance Considerations

| Concern | At 1 deployment | At 10 deployments | At 100 deployments |
|---------|-----------------|-------------------|--------------------|
| WebSocket pool | Single connection per cmd | One per deploy cmd | Connection pooling likely needed |
| TTY state | Per-connection | Per-connection | Per-connection |
| Async overhead | Minimal | Minimal | Minimal (async scales well) |
| Memory | <50MB Python process | <50MB | <100MB (reasonable) |

**Scaling recommendation:** For 100+ concurrent deployments, consider connection pooling to the same Console API endpoint. Current design (one-shot per command) scales fine for CLI usage.

---

## Security Considerations

### API Key Handling
- WebSocket connection requires `AKASH_API_KEY` header (same as REST API)
- **Risk:** API key sent over HTTPS/WSS (encrypted in transit)
- **Mitigation:** Use HTTPS/WSS only (enforce in client), warn if HTTP in env

### Command Injection
- User-provided commands are sent as JSON in WebSocket message
- **Risk:** If server doesn't properly escape, command injection possible
- **Mitigation:** Trust Akash provider implementation; commands executed via provider-services (assumed safe)

### Secrets in Logs
- Inject commands may include secrets via `--env KEY=VALUE`
- **Risk:** CLI argv may be logged
- **Mitigation:** Document: don't use CLI args for secrets, use `--env-file` instead (already in v1.4)

---

## Sources

### Akash Documentation
- [Deployment Shell Access - Akash Guidebook](https://docs.akash.network/features/deployment-shell-access)
- [Shell Access | Akash Network](https://akash.network/docs/learn/core-concepts/shell-access/)
- [Access a Deployment's Shell - Akash Guidebook](https://docs.akash.network/guides/cli/akash-cli-booster/access-a-deployments-shell)
- [Akash Console API v1 OAS 3.0](https://console-api.akash.network/v1/swagger)

### Python Libraries & Patterns
- [websockets 16.0 Documentation](https://websockets.readthedocs.io/)
- [Python pty Module](https://docs.python.org/3/library/pty.html)
- [ptyprocess Documentation](https://ptyprocess.readthedocs.io/)
- [asyncio Client - websockets](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html)
- [GitHub - aluzzardi/wssh: SSH to WebSockets Bridge](https://github.com/aluzzardi/wssh)

### GitHub References
- [GitHub - akash-network/provider-console-api](https://github.com/akash-network/provider-console-api)
- [GitHub - akash-network/console](https://github.com/akash-network/console)
- [GitHub - python-websockets/websockets](https://github.com/python-websockets/websockets)
