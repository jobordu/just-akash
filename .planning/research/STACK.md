# Technology Stack: Akash Lease-Shell WebSocket Transport

**Project:** just-akash v1.5 (Lease-Shell WebSocket Transport)  
**Researched:** 2026-04-18  
**Focus:** NEW stack additions for WebSocket-based lease-shell transport (replacing SSH for shell operations)

## Executive Summary

Adding lease-shell WebSocket transport to just-akash requires three core library additions:

1. **WebSocket client**: `websockets>=16.0` (async) OR `websocket-client>=1.9.0` (sync) — for WebSocket protocol
2. **Terminal emulation**: `pexpect>=4.9.0` — for interactive PTY control (POSIX only)
3. **Protocol support**: No additional dependencies needed (Akash lease-shell uses standard WebSocket messaging, not gRPC)

The existing `requests>=2.33.0` HTTP client remains sufficient for Console API interaction. No protobuf/gRPC libraries required for lease-shell itself (gRPC is planned for future LeaseRPC v2).

## Recommended Stack

### WebSocket Transport

| Technology | Version | Purpose | Why This Choice |
|-----------|---------|---------|-----------------|
| websockets | >=16.0 | WebSocket client for lease-shell protocol | Pure Python, async-first (future-proof), RFC 6455/7692 compliant, built on asyncio (matches CLI's async model) |
| websocket-client | >=1.9.0 | Alternative: sync WebSocket client | If sync-only needed; wider ecosystem compatibility, less dependency management |

**Decision Rationale**: Use `websockets>=16.0` as primary recommendation. It's the modern Python WebSocket library with async support, proper RFC compliance, C extension acceleration, and active maintenance (v16.0 released Jan 2026). For CLI usage, async aligns with future extensibility (concurrent deployments, better timeout handling). If the codebase must remain purely synchronous, fall back to `websocket-client>=1.9.0`.

### Terminal Emulation (Interactive Shell)

| Technology | Version | Purpose | Why This Choice |
|-----------|---------|---------|-----------------|
| pexpect | >=4.9.0 | PTY control for interactive shell emulation | Provides expect-like pattern matching over pseudo-terminals; works with Windows; enables local terminal echo/input handling for remote shells |

**Decision Rationale**: `pexpect` provides the abstraction layer between raw WebSocket messages and a functional interactive terminal. It handles local echo, line editing, and signal forwarding (Ctrl+C, Ctrl+D) without reimplementing terminal emulation from scratch. Type stub package `types-pexpect>=4.9.0.20260127` available for type-aware development.

### HTTP/REST (Existing, Unchanged)

| Technology | Version | Purpose | Status |
|-----------|---------|---------|--------|
| requests | >=2.33.0 | Console API HTTP interaction (deploy, list, status) | Existing; validated in v1.0-1.4 |
| urllib | stdlib | Backup for lightweight requests (no external dep) | Existing; used in api.py |

**Note**: No changes to HTTP/REST stack. Akash Console API remains HTTP-based; WebSocket is only for lease-shell transport layer.

### Standard Library Usage (Verified)

The current codebase uses only Python stdlib for core operations:
- `json` — deployment/response parsing
- `subprocess` — SSH execution (will be replaced by WebSocket for lease-shell)
- `argparse` — CLI interface (compatible with WebSocket additions)
- `os`, `sys`, `pathlib`, `tempfile` — file/env handling
- `logging` — debug output (compatible)
- `pty` (POSIX only) — may be needed directly for pexpect integration

All WebSocket work can be isolated in new modules without breaking existing imports.

## Installation & Integration

### Adding to pyproject.toml

```toml
[project]
name = "just-akash"
requires-python = ">=3.10"
dependencies = [
    "websockets>=16.0",
    "pexpect>=4.9.0",
    "requests>=2.33.0",  # existing HTTP client
]

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-cov>=7.1.0",
    "pyright>=1.1.399",
    "ruff>=0.15.10",
    "types-pexpect>=4.9.0.20260127",  # type checking
]
```

### Installation via uv

```bash
# Core dependencies
uv pip install websockets>=16.0 pexpect>=4.9.0 requests>=2.33.0

# With dev dependencies (for type checking)
uv pip install -e ".[dev]"

# Or via uv sync with updated pyproject.toml
uv sync
```

### Minimal WebSocket Client Example (Integration Test)

```python
import asyncio
import websockets
import json

async def lease_shell_exec(ws_url: str, dseq: str, provider: str, service: str, cmd: str):
    """Execute command via lease-shell WebSocket."""
    async with websockets.connect(ws_url) as ws:
        # Send command frame (binary or JSON depending on provider API)
        msg = {"type": "exec", "dseq": dseq, "provider": provider, "service": service, "cmd": cmd}
        await ws.send(json.dumps(msg))
        
        # Receive output frames until EOF
        output = []
        async for message in ws:
            data = json.loads(message)
            if data.get("type") == "output":
                output.append(data.get("data", ""))
            elif data.get("type") == "exit":
                break
        return "".join(output)

# Usage
result = asyncio.run(lease_shell_exec(
    "wss://console.akash.network/api/v1/leases/{lease_id}/shell",
    dseq="123456",
    provider="akash1...",
    service="app",
    cmd="ls -la"
))
print(result)
```

### Interactive Shell Integration with pexpect

```python
import pexpect
import subprocess
import asyncio
from just_akash.lease_shell import WebSocketShellTransport

async def connect_interactive(dseq: str, provider: str, service: str):
    """Open interactive lease-shell session with local TTY control."""
    # Initialize WebSocket transport (handles message framing)
    transport = WebSocketShellTransport(dseq=dseq, provider=provider, service=service)
    
    # Spawn pexpect session wrapping the transport
    # pexpect handles: local echo, input buffering, signal forwarding (Ctrl+C, etc.)
    shell = pexpect.spawn(
        "python -m just_akash.shell_bridge",  # local subprocess speaking to WebSocket
        timeout=30,
        encoding='utf-8'
    )
    
    # User can now interact as if over SSH:
    # - type commands
    # - see output with proper terminal formatting
    # - press Ctrl+C, Ctrl+D
    shell.interact()
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not | Trade-off |
|----------|-------------|-------------|---------|-----------|
| WebSocket | websockets >=16.0 | websocket-client >=1.9.0 | Sync-only, less RFC-correct, smaller ecosystem | Sync simplicity vs async future-proofing |
| WebSocket | websockets >=16.0 | asyncio.StreamWriter directly | No protocol handling, error-prone | Manual framing = bugs |
| Terminal | pexpect >=4.9.0 | pty stdlib module directly | Low-level, error handling painful, no expect patterns | Lower abstraction = more code |
| Terminal | pexpect >=4.9.0 | blessed library | TUI toolkit (too heavy for this use case) | Overkill for simple shell bridge |
| HTTP | requests >=2.33.0 | httpx (async) | Adds async overhead for deploy/list commands; not needed yet | Complexity vs current sync model |
| Protocol | Native WebSocket msgs | gRPC + protobuf | gRPC only for future LeaseRPC (not yet deployed); lease-shell uses simple JSON/binary frames | Future-proofing vs now complexity |

## Dependencies Tree

```
just-akash (CLI)
├── websockets>=16.0
│   └── (async protocol layer, no sub-deps in production)
├── pexpect>=4.9.0
│   └── ptyprocess (included with pexpect)
└── requests>=2.33.0 (existing)
    ├── charset-normalizer
    ├── certifi
    ├── idna
    └── urllib3

Dev dependencies:
├── types-pexpect>=4.9.0.20260127 (type stubs)
└── [existing pytest, ruff, pyright, coverage]
```

## Known Constraints & Rationale

### 1. **POSIX-only PTY (pexpect.spawn)**
- Limitation: `pexpect.spawn()` and `pty` module only work on Unix/Linux/macOS
- Impact: Interactive shell (`connect --transport lease-shell`) unavailable on Windows  
- Mitigation: 
  - Non-interactive exec/inject (via websockets only) work on all platforms
  - SSH (`--transport ssh`) remains available on Windows as fallback
  - Windows support deferred to v1.6; see PITFALLS.md

### 2. **No gRPC Dependency (Yet)**
- Akash LeaseRPC proposal (AEP-37) uses gRPC + protobuf, but **not yet deployed**
- Console API (current) uses HTTP + optional WebSocket for lease-shell
- Decision: Use native WebSocket framing for now; add `grpcio` + `grpcio-tools` only when LeaseRPC becomes available (likely v2.0)
- Avoids: Premature dependency bloat, code generation complexity

### 3. **Async-first Design (websockets)**
- `websockets>=16.0` is async-only (coroutine-based API)
- Current CLI uses sync (`subprocess`, `requests`)
- Integration: Wrap async WebSocket ops in `asyncio.run()` at CLI boundary (minimal changes)
- Rationale: Enables future concurrent lease operations (e.g., exec multiple services in parallel)

## Security Considerations

| Aspect | Implementation | Rationale |
|--------|----------------|-----------|
| TLS/SSL | WebSocket Secure (WSS) via `wss://` URIs | Console API requires WSS for auth headers |
| Verification | `websockets` handles cert validation by default | No extra config needed unless self-signed certs (rare on Akash Console) |
| Auth | Akash API key passed via HTTP header (existing pattern) | WebSocket upgrade request inherits headers from Console API session |
| Secret Injection | Avoids SSH key storage; uses API key + WebSocket | Reduces SSH key management surface |

## Deployment Notes

- **Python 3.10+**: All libraries tested on 3.10, 3.11, 3.12, 3.13
- **Package Installation**: All available on PyPI; no custom build steps
- **Type Checking**: `pyright` with `types-pexpect` stubs ensures type safety
- **Testing**: Existing `pytest` suite compatible; add `test_lease_shell.py` with mock WebSocket server

## Sources

- [websockets 16.0 PyPI](https://pypi.org/project/websockets/) — Latest version, released Jan 2026
- [websocket-client 1.9.0 GitHub Releases](https://github.com/websocket-client/websocket-client/releases) — Alternative, released Oct 2025
- [pexpect 4.9.0 PyPI](https://pypi.org/project/pexpect/) — PTY control library
- [Akash Lease Control API via gRPC (AEP-37)](https://akash.network/roadmap/aep-37/) — Future gRPC direction (not yet deployed)
- [Python WebSocket Libraries Comparison (CodeRivers)](https://coderivers.org/blog/python-websocket-vs-websockets-vs-websocketclient/) — Design decision rationale
- [requests 2.33.0+ PyPI](https://pypi.org/project/requests/) — Existing HTTP client for Console API
- [Python pty Module Documentation](https://docs.python.org/3/library/pty.html) — PTY control (POSIX only)
