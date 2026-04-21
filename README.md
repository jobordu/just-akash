# just-akash

Justfile recipes + Python CLI for deploying on [Akash Network](https://akash.network) via the Console API.

Self-contained — clone, configure `.env`, and run.

## What's New in v1.5.0

- **Lease-shell transport** — exec and inject via WebSocket proxy (`wss://console.akash.network/provider-proxy-mainnet`), **no SSH required**
- **Dual transport** — `--transport lease-shell` (default) or `--transport ssh` on every `exec`/`inject`/`connect` command
- **514 tests** with 68% coverage
- **CI pipeline** — ruff lint, ruff format, pyright typecheck, unit tests, E2E lease-shell test, E2E secrets test

## Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (Python package runner)
- [`just`](https://github.com/casey/just) command runner (optional, but recommended)

## Setup

```bash
git clone https://github.com/jobordu/just-akash
cd just-akash
cp .env.example .env
# Edit .env — add your API key, providers, SSH pubkey
uv sync --dev           # install package + dev tools (ruff)
uv run pre-commit install   # install gitleaks + ruff hooks
```

## Usage

### With `just` (recommended)

| Command | Usage | Purpose |
|---|---|---|
| `just deploy [sdl] [image]` | `just deploy` | Deploy with custom SDL/image |
| `just up [tag]` | `just up my-web-app` | Deploy SSH instance + optional tag |
| `just connect [dseq] [transport]` | `just connect 12345 ssh` | Connect to a running instance (lease-shell default) |
| `just exec [dseq] "cmd" [transport]` | `just exec 12345 "ls -la"` | Execute a remote command |
| `just inject [dseq] [env-file] [transport]` | `just inject 12345 .env.secrets` | Inject secrets (lease-shell default) |
| `just destroy [dseq]` | `just destroy 12345` | Destroy an instance |
| `just destroy-all` | `just destroy-all` | Destroy all instances |
| `just list` | `just list` | List active instances |
| `just status [dseq]` | `just status 12345` | Show instance details |
| `just tag [dseq] [name]` | `just tag 12345 my-db` | Tag a deployment with a name |
| `just test-shell` | `just test-shell` | E2E lease-shell transport test (deploy/exec/inject/cleanup) |
| `just test-secrets` | `just test-secrets` | E2E secrets injection test (SSH inject + lease-shell cross-check) |
| `just lint` | `just lint` | Ruff lint + format check |
| `just secrets` | `just secrets` | Gitleaks secret scan |

Transport: `connect`, `exec`, and `inject` default to `lease-shell`. Pass `ssh` as the last argument to force SSH: `just exec 12345 "cmd" ssh`.

### DSEQs vs Tags

**DSEQ** (Deployment Sequence) is the unique numeric ID assigned by Akash when you create a deployment.

**Tags** are human-readable names you can assign to DSEQs for easier management.

```bash
just up my-web-app         # Deploy and tag as "my-web-app"
just status my-web-app     # Check status using tag
just connect my-web-app    # Connect in using tag
just destroy my-web-app    # Destroy using tag
```

### Secrets Injection

Inject secrets into a running deployment — **no SSH required** (lease-shell is the default).

```bash
# From a file (lease-shell, default)
just inject "" .env.secrets

# Force SSH transport
just inject 12345 .env.secrets ssh

# Or with inline CLI args
uv run just-akash inject --dseq 12345 --env SECRET_KEY=abc --env DB_PASS=xyz

# From a file
uv run just-akash inject --dseq 12345 --env-file .env.secrets
```

Secrets are written to `/run/secrets/.env` (or custom `--remote-path`) with `chmod 600`.

### With `uv run` (direct CLI)

```bash
# Deploy
uv run just-akash deploy --sdl sdl/cpu-backtest-ssh.yaml

# Deploy with env vars (provider-visible)
uv run just-akash deploy --sdl sdl/cpu-backtest-ssh.yaml --env REGION=us-east

# Connect / exec / inject
uv run just-akash connect --dseq 12345
uv run just-akash exec --dseq 12345 "echo hello"
uv run just-akash inject --dseq 12345 --env-file .env.secrets

# Force SSH transport
uv run just-akash exec --dseq 12345 --transport ssh "echo hello"
uv run just-akash inject --dseq 12345 --transport ssh --env-file .env.secrets

# List / status / destroy
uv run just-akash list
uv run just-akash status --dseq 12345
uv run just-akash destroy --dseq 12345
uv run just-akash tag --dseq 12345 --name my-job
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AKASH_API_KEY` | Yes | Console API key |
| `AKASH_PROVIDERS` | No | Comma-separated allowlist of provider addresses (empty = accept any) |
| `SSH_PUBKEY` | For SSH SDL | SSH public key (injected into container) |
| `AKASH_CONSOLE_URL` | No | Console API base URL (default: `https://console-api.akash.network`) |
| `AKASH_DEBUG` | No | Set to `1` for verbose API/deploy logging |

## Transports

`exec`, `inject`, and `connect` support two transports:

### Lease-shell (default)

Uses the Akash Console WebSocket proxy (`wss://console.akash.network/provider-proxy-mainnet`) to relay commands to the provider. **No SSH required.** The proxy connects to the provider using a JWT with provider-scoped permissions.

```bash
just exec 12345 "echo hello"              # lease-shell (default)
just inject 12345 .env.secrets          # lease-shell (default)
```

### SSH

Traditional SSH connection to the container. Requires an SSH-enabled SDL and `SSH_PUBKEY` configured.

```bash
just exec 12345 "echo hello" ssh        # force SSH
just inject 12345 .env.secrets ssh      # force SSH
```

## Bid Selection

Deployments use a two-phase bid polling strategy:

1. **Phase 1**: Wait `--bid-wait` seconds (default 60), then pick the cheapest bid
2. **Phase 2**: If no bids received, wait `--bid-wait-retry` seconds (default 120) more

Both timeouts are configurable via CLI flags or `just` recipe overrides.

## Logs

Every `just` recipe writes timestamped logs to `.logs/just/` with start/end metadata, exit codes, and full output.

## Secret Scanning

Three layers of secret detection run on every push/PR:

- **Gitleaks** — pre-commit hook + CI (full history on schedule)
- **TruffleHog** — CI (verified secrets only)
- **detect-secrets** — baseline diff check in CI

## License

[MIT](LICENSE) — Jonathan Borduas
