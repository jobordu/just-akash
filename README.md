# just-akash

Justfile recipes for deploying on [Akash Network](https://akash.network) via the Console API.

Self-contained — clone, configure `.env`, and run.

## Prerequisites

- Python 3.10+
- [`just`](https://github.com/casey/just) command runner
- Akash Console account + API key ([console.akash.network](https://console.akash.network))

## Setup

```bash
cp .env.example .env
# Edit .env — add your API key, providers, SSH pubkey
```

## Recipes

| Command | Usage | Purpose |
|---------|-------|---------|
| `just up [tag]` | `just up my-backtest` | Deploy SSH-enabled instance (waits for all providers to bid, picks cheapest) |
| `just connect [dseq]` | `just connect 12345` | SSH into a running instance |
| `just down [dseq]` | `just down 12345` | Stop an instance |
| `just down-all` | `just down-all` | Stop all instances |
| `just tag DSEQ NAME` | `just tag 12345 my-job` | Tag a deployment with a name |
| `just ls` | `just ls` | List active instances |
| `just status [dseq]` | `just status 12345` | Show instance details |
| `just test` | `just test` | Full lifecycle test (up → verify → SSH → down → cleanup) |
| `just deploy [sdl] [image]` | `just deploy sdl/cpu-backtest-ssh.yaml` | Deploy with custom SDL |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AKASH_API_KEY` | Yes | Console API key |
| `AKASH_PROVIDERS` | Yes | Comma-separated allowlist of provider addresses |
| `SSH_PUBKEY` | For SSH SDL | SSH public key (injected into container) |
| `AKASH_DEBUG` | No | Set to `1` for verbose API/deploy logging |

## Bid Selection

Deployments poll for bids from **all** allowed providers before selecting the cheapest. If a provider doesn't bid, it's logged with on-chain status diagnostics.

## Logs

Every recipe writes timestamped logs to `.logs/just/` with start/end metadata, exit codes, and full output.
