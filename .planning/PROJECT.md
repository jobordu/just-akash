# just-akash

## What This Is

A Python CLI and Justfile recipe set for deploying workloads on Akash Network via the Console API. Users configure a `.env`, run `just up` or `just-akash deploy`, and get a running SSH-accessible instance on decentralized cloud infrastructure. Self-contained — no extra tooling beyond `uv` and optionally `just`.

## Core Value

Fastest path from "I want something running on Akash" to a live, SSH-accessible instance — single command, no manual portal steps.

## Profile: cli-tool

## Requirements

### Validated

- ✓ Deploy SSH-enabled instances via Akash Console API — v1.0
- ✓ Two-phase bid polling with configurable timeouts — v1.0
- ✓ Cheapest bid selection with provider allowlist filtering — v1.0
- ✓ Provider diagnostics when allowed providers don't bid — v1.0
- ✓ SSH connectivity with auto-detected key path — v1.0
- ✓ Interactive deployment picker (arrow keys) — v1.0
- ✓ Deployment tagging (DSEQ → human-readable name) — v1.0
- ✓ Full lifecycle integration test — v1.0
- ✓ Restructured to proper Python package (`just_akash/`) — v1.1
- ✓ `-y`/`--yes` flag for non-interactive mode — v1.1
- ✓ Pre-commit config (gitleaks + ruff), GitHub Actions CI — v1.1
- ✓ `--json` flag on list/status/close commands — v1.2
- ✓ `pyright` type checking — v1.2
- ✓ `_confirm()` helper DRY consolidation — v1.2
- ✓ Adversarial/edge-case test suite — v1.3
- ✓ Secrets injection via SSH (`just inject` / `just-akash inject`) — v1.4
- ✓ Remote command execution (`just exec` / `just-akash exec`) — v1.4
- ✓ SDL env injection at deploy time (`--env KEY=VALUE`) — v1.4
- ✓ Configurable Console API URL via `AKASH_CONSOLE_URL` — v1.4
- ✓ Unified CLI (all commands top-level) — v1.4

### Active

<!-- To be defined in new milestone -->

### Out of Scope

<!-- Defined per milestone -->

## Context

- Python 3.10+, `uv` for package management, `just` for task runner
- Akash Network Console API for deployments (no direct chain interaction)
- SSH-based access model: provider starts container, user SSHes in
- 357 tests at 69% coverage as of v1.4.0
- Branch `feature/issue-1-add-websocket-shell-transport` suggests next feature is WebSocket shell transport

## Constraints

- **Tech stack**: Python 3.10+, `uv`, no heavy framework dependencies
- **Compatibility**: Must work as both standalone CLI (`just-akash`) and Justfile import

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Console API over direct chain | Simpler, no wallet/key management needed | ✓ Good |
| SSH-based shell access | Works with any provider, no special protocol | ✓ Good |
| `uv` as package manager | Fast, modern, handles virtualenvs cleanly | ✓ Good |

---
*Last updated: 2026-04-18 — nForma bootstrap from existing codebase (v1.4.0)*
