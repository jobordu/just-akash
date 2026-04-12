# just-akash

Justfile recipes + Python CLI for deploying on [Akash Network](https://akash.network) via the Console API.

Self-contained — clone, configure `.env`, and run.

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
|---------|-------|---------|
| `just up [tag]` | `just up my-backtest` | Deploy SSH-enabled instance (polls bids, picks cheapest) |
| `just connect [dseq]` | `just connect 12345` | SSH into a running instance |
| `just down [dseq]` | `just down 12345` | Stop an instance |
| `just down-all` | `just down-all` | Stop all instances |
| `just tag DSEQ NAME` | `just tag 12345 my-job` | Tag a deployment with a name |
| `just ls` | `just ls` | List active instances |
| `just status [dseq]` | `just status 12345` | Show instance details |
| `just test` | `just test` | Full lifecycle test (up → verify → SSH → down → cleanup) |
| `just lint` | `just lint` | Ruff lint + format check |
| `just secrets` | `just secrets` | Gitleaks secret scan |

### With `uv run` (direct CLI)

```bash
# Deploy
uv run just-akash deploy --sdl sdl/cpu-backtest-ssh.yaml --bid-wait 60 --bid-wait-retry 120

# API operations
uv run just-akash api list
uv run just-akash api status --dseq 12345
uv run just-akash api connect --dseq 12345
uv run just-akash api close --dseq 12345
uv run just-akash api tag --dseq 12345 --name my-job

# Lifecycle test
uv run python -m just_akash.test_lifecycle
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AKASH_API_KEY` | Yes | Console API key |
| `AKASH_PROVIDERS` | No | Comma-separated allowlist of provider addresses (empty = accept any) |
| `SSH_PUBKEY` | For SSH SDL | SSH public key (injected into container) |
| `AKASH_DEBUG` | No | Set to `1` for verbose API/deploy logging |

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
