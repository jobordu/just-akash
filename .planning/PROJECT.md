# just-akash

## What This Is

A Python CLI and Justfile recipe set for deploying workloads on Akash Network via the Console API. Users configure a `.env`, run `just up` or `just-akash deploy`, and get a running instance on decentralized cloud infrastructure. Supports both lease-shell (default) and SSH transports for remote access. Self-contained — no extra tooling beyond `uv` and optionally `just`.

## Core Value

Fastest path from "I want something running on Akash" to a live, remotely-accessible instance — single command, no manual portal steps.

## Current Milestone: v1.5 — Lease-Shell Transport

**Goal:** Replace SSH as the default transport with Akash's native `lease-shell` WebSocket mechanism across all shell-dependent commands.

**Target features:**
- lease-shell WebSocket transport for `exec`, `inject`, and `connect`/`shell` commands
- lease-shell as default; SSH opt-in via `--transport ssh` flag
- Interactive shell session via lease-shell (new `shell` command or enhanced `connect`)
- Secrets injection via lease-shell (replace SSH SCP path)
- Test coverage for lease-shell transport

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

- [ ] lease-shell WebSocket transport as default for exec, inject, connect
- [ ] `--transport ssh` flag to opt-in to SSH transport
- [ ] Interactive shell session via lease-shell
- [ ] Secrets injection via lease-shell (no SSH dependency)
- [ ] Test coverage for lease-shell transport

### Out of Scope

<!-- Defined per milestone -->

## Context

- Python 3.10+, `uv` for package management, `just` for task runner
- Akash Network Console API for deployments (no direct chain interaction)
- SSH-based access model in v1.4; v1.5 switches default to Akash lease-shell WebSocket API
- 357 tests at 69% coverage as of v1.4.0
- Akash Console exposes a lease-shell endpoint for WebSocket-based interactive shell access
- Goal: enable programmatic shell access without requiring SSH keys or port 22

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
*Last updated: 2026-04-18 — Milestone v1.5 started*
