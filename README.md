# just-akash

Justfile recipes + Python CLI for deploying on [Akash Network](https://akash.network) via the Console API.

Self-contained — clone, configure `.env`, and run.

## What's New in v1.4.0

- **Secrets injection** via SSH (`just inject` / `just-akash inject`)
- **Remote command execution** (`just exec` / `just-akash exec`)
- **SDL env injection** at deploy time (`--env KEY=VALUE`, provider-visible)
- **Configurable Console API URL** via `AKASH_CONSOLE_URL` env var
- **Unified CLI** — all commands are top-level (`deploy`, `connect`, `exec`, `inject`, `list`, `status`, `destroy`, `tag`)
- **E2E secrets test** (`just test-secrets`) — deploy, inject, verify, cleanup
- **357 tests** with 69% coverage

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
| `just deploy` | `just deploy` | Deploy with custom SDL/image |
| `just up [tag]` | `just up my-web-app` | Deploy SSH instance + optional tag |
| `just connect` | `just connect 12345` | SSH into a running instance |
| `just exec` | `just exec "" "ls -la"` | Execute a remote command |
| `just inject` | `just inject "" .env.secrets` | Inject secrets via SSH |
| `just destroy` | `just destroy 12345` | Destroy an instance |
| `just destroy-all` | `just destroy-all` | Destroy all instances |
| `just list` | `just list` | List active instances |
| `just status` | `just status 12345` | Show instance details |
| `just tag` | `just tag 12345 my-db` | Tag a deployment with a name |
| `just test` | `just test` | Lifecycle test (deploy/SSH/destroy) |
| `just test-secrets` | `just test-secrets` | Secrets injection E2E test |
| `just lint` | `just lint` | Ruff lint + format check |
| `just secrets` | `just secrets` | Gitleaks secret scan |

### DSEQs vs Tags

**DSEQ** (Deployment Sequence) is the unique numeric ID assigned by Akash when you create a deployment.

**Tags** are human-readable names you can assign to DSEQs for easier management.

```bash
just up my-web-app         # Deploy and tag as "my-web-app"
just status my-web-app     # Check status using tag
just connect my-web-app    # SSH in using tag
just destroy my-web-app    # Destroy using tag
```

### Secrets Injection

Inject secrets into a running deployment via SSH (never exposed in the SDL or to the provider):

```bash
# From a file
just inject "" .env.secrets

# Or inline via CLI
just-akash inject --dseq 12345 --env SECRET_KEY=abc --env DB_PASS=xyz

# Or with a file
just-akash inject --dseq 12345 --env-file .env.secrets
```

Secrets are written to `/run/secrets/.env` with `chmod 600`. Requires an SSH-enabled SDL.

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

## SSH Requirement

The `connect`, `exec`, and `inject` commands require SSH to be configured in the SDL:

1. Port 22 exposed in the SDL
2. `SSH_PUBKEY` set in `.env` (injected as `SSH_PUBKEY_B64` placeholder)
3. Container entrypoint runs `sshd`

The default SSH SDL (`sdl/cpu-backtest-ssh.yaml`) handles all of this. The Akash Console API does not support lease-shell — SSH is the only remote execution path.

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
