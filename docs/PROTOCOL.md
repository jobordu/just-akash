# Akash Lease-Shell WebSocket Protocol

**Observed at:** 2026-04-19  
**Source:** akash-network/provider — `gateway/rest/router_shell.go`, `gateway/rest/constants.go`, `gateway/rest/client_shell.go`  
**Confidence:** HIGH (derived from provider Go source; binary frame constants confirmed)

---

## Endpoint

The lease-shell WebSocket endpoint is served directly by the **Akash provider daemon**, not the Console API.

```
wss://{provider_host}:{provider_port}/lease/{dseq}/{gseq}/{oseq}/shell
```

**Path parameters:**

| Param | Description | Example |
|-------|-------------|---------|
| `dseq` | Deployment sequence number | `1234567` |
| `gseq` | Group sequence (usually `1`) | `1` |
| `oseq` | Order sequence (usually `1`) | `1` |

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `cmd` | `string` | Command to execute (non-interactive exec) |
| `tty` | `bool` | Enable TTY mode for interactive shell |
| `service` | `string` | Target service name (from SDL) |
| `stdin` | `bool` | Enable stdin channel |
| `podIndex` | `int` | Pod replica index (0-based, default 0) |

**Example URL:**
```
wss://provider.us-east.akash.pub:8443/lease/1234567/1/1/shell?service=app&tty=true&stdin=true
```

**HTTP Upgrade:** Standard WebSocket upgrade via `GET` with `Connection: Upgrade` + `Upgrade: websocket` headers.

---

## Authentication

Authentication uses a **JWT bearer token** with `shell` permission scope, passed in the HTTP upgrade request header:

```
Authorization: Bearer <JWT_TOKEN>
```

**JWT claims include:**
- `scope`: must include `"shell"` permission
- `exp`: token expiry (finite TTL — typically 15–60 minutes)
- `dseq` / `leaseID`: scoped to a specific lease

**Critical:** JWT tokens expire. Long-running sessions MUST implement token refresh before expiry — see `PITFALLS.md` for implementation pattern.

**Provider address discovery:** The provider host/port is retrieved from the Console API deployment status (`leases[].provider`), then used to construct the WebSocket URL.

---

## Message Schema

All messages are **binary WebSocket frames**. Each frame begins with a **1-byte type code** followed by the payload.

```
[type: uint8 (1 byte)] [payload: bytes (remaining)]
```

**Type constants** (from `gateway/rest/constants.go`):

| Code | Constant | Direction | Payload |
|------|----------|-----------|---------|
| `100` | `LeaseShellCodeStdout` | Server → Client | Raw bytes (stdout from container) |
| `101` | `LeaseShellCodeStderr` | Server → Client | Raw bytes (stderr from container) |
| `102` | `LeaseShellCodeResult` | Server → Client | Protobuf/JSON — exit code + message |
| `103` | `LeaseShellCodeFailure` | Server → Client | UTF-8 error message string |
| `104` | `LeaseShellCodeStdin` | Client → Server | Raw bytes (stdin to container) |
| `105` | `LeaseShellCodeTerminalResize` | Client → Server | Big-endian uint16 rows + uint16 cols (4 bytes) |

### Frame encoding

**Stdin (code 104):**
```python
import struct
frame = bytes([104]) + user_input_bytes
```

**Stdout / Stderr (codes 100, 101):**
```python
code = frame[0]   # 100 or 101
data = frame[1:]  # raw bytes — write to stdout.buffer or stderr.buffer
```

**Result (code 102):**
The payload encodes the remote exit code. Parse as little-endian int32 or JSON depending on provider version:
```python
code = frame[0]   # 102
# Payload may be: 4-byte little-endian exit code, or JSON {"exit_code": N}
exit_code = int.from_bytes(frame[1:5], byteorder='little')
```

**Failure (code 103):**
```python
code = frame[0]   # 103
error_msg = frame[1:].decode('utf-8', errors='replace')
raise RuntimeError(f"Provider error: {error_msg}")
```

**Terminal resize (code 105):**
```python
import struct
rows, cols = 24, 80
frame = bytes([105]) + struct.pack('>HH', rows, cols)  # big-endian uint16 pairs
```

---

## Connection Lifecycle

### Non-interactive exec (`cmd` query param)

```
Client                          Provider
  |                                 |
  |-- WebSocket UPGRADE ----------->|
  |   ?cmd=echo+hello&service=app   |
  |   Authorization: Bearer <jwt>   |
  |<-- 101 Switching Protocols -----|
  |                                 |
  |<-- [100] stdout: "hello\n" -----|
  |<-- [102] result: exit_code=0 ---|
  |<-- WebSocket CLOSE -------------|
  |-- WebSocket CLOSE ACK --------->|
```

### Interactive shell (`tty=true`, `stdin=true`)

```
Client                          Provider
  |                                 |
  |-- WebSocket UPGRADE ----------->|
  |   ?service=app&tty=true&stdin=true
  |   Authorization: Bearer <jwt>   |
  |<-- 101 Switching Protocols -----|
  |                                 |
  |-- [104] stdin: "ls\n" --------->|
  |<-- [100] stdout: "bin etc\n" ---|
  |<-- [100] stdout: "..." ---------|
  |-- [104] stdin: "exit\n" ------->|
  |<-- [102] result: exit_code=0 ---|
  |<-- WebSocket CLOSE -------------|
  |-- WebSocket CLOSE ACK --------->|
```

### Graceful close

The **server closes first** after sending a `LeaseShellCodeResult` (102) frame. Client must acknowledge with a close frame within 5 seconds or force-close.

```python
# Client-side close (always use a timeout):
try:
    await asyncio.wait_for(ws.close(), timeout=5.0)
except asyncio.TimeoutError:
    ws.transport.close()  # force-close
```

---

## Provider Address Discovery

The provider host and port are not fixed — they are resolved from the deployment's lease information via the Console API:

```python
# 1. Get deployment from Console API
deployment = client.get_deployment(dseq)

# 2. Extract provider endpoint from lease
provider_url = deployment["leases"][0]["provider"]["hostUri"]
# e.g. "https://provider.us-east.akash.pub:8443"

# 3. Construct WebSocket URL
ws_url = provider_url.replace("https://", "wss://") \
                     .replace("http://", "ws://")
ws_url += f"/lease/{dseq}/{gseq}/{oseq}/shell"
```

---

## TLS / mTLS

The provider endpoint uses **TLS**. For Console-proxied access, standard CA-signed certs are used. For direct provider access, providers may use self-signed certificates — clients must allow insecure TLS or load the provider's CA cert.

```python
import ssl
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False   # providers use self-signed certs
ssl_ctx.verify_mode = ssl.CERT_NONE  # TODO: load provider CA in production
```

---

## Python Implementation Notes

### WebSocket library

Use `websockets>=16.0` (async-first, RFC 6455 compliant):

```python
import websockets

async def connect_shell(url: str, jwt: str) -> None:
    headers = {"Authorization": f"Bearer {jwt}"}
    async with websockets.connect(url, additional_headers=headers, ssl=ssl_ctx) as ws:
        # dispatch frames by type code
        async for frame in ws:
            if isinstance(frame, bytes):
                handle_binary_frame(frame)
```

### Recv pattern

```python
async def handle_binary_frame(frame: bytes) -> int | None:
    code = frame[0]
    payload = frame[1:]
    if code == 100:
        sys.stdout.buffer.write(payload); sys.stdout.buffer.flush()
    elif code == 101:
        sys.stderr.buffer.write(payload); sys.stderr.buffer.flush()
    elif code == 102:
        return int.from_bytes(payload[:4], 'little') if len(payload) >= 4 else 0
    elif code == 103:
        raise RuntimeError(payload.decode('utf-8', errors='replace'))
    return None
```

---

## Unconfirmed Fields

The following details are inferred from source patterns and require validation against a live provider:

| Field | Assumed | Must validate |
|-------|---------|---------------|
| `LeaseShellCodeResult` payload encoding | 4-byte LE int32 exit code | May be JSON or protobuf |
| JWT token endpoint (how to get `Bearer` token) | Console API `/v1/auth` or JWT issue endpoint | Confirm exact endpoint |
| `podIndex` default behaviour | Defaults to first available pod | Confirm with multi-replica deployment |
| Provider TLS cert validity | Self-signed; skip verify in Phase 7 | Add CA cert support in Phase 8+ |
| `gseq` / `oseq` values | Always `1/1` for single-group deployments | Confirm with multi-group SDL |

---

## References

- Provider source: `github.com/akash-network/provider` — `gateway/rest/router_shell.go`, `constants.go`, `client_shell.go`
- Lease-shell CLI: `provider-services lease-shell --dseq <N> --provider <addr> <service> <cmd>`
- AEP-64 (JWT auth): `https://akash.network/roadmap/aep-64/`
- Deployment shell docs: `https://docs.akash.network/features/deployment-shell-access`
