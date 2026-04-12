set dotenv-load

# ── Lifecycle ────────────────────────────────────────

# Start a new Akash instance (SSH-enabled, key-auth only)
# Usage: just up [tag]
up tag="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/up-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=up finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=up started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file tag={{tag}}"
    set -x
    uv run just-akash deploy --sdl sdl/cpu-backtest-ssh.yaml --bid-wait 60 --bid-wait-retry 120 | tee /tmp/.akash-last-deploy.log
    dseq=$(sed -n 's/.*DSEQ: \([0-9]*\).*/\1/p' /tmp/.akash-last-deploy.log | head -1)
    if [ -n "{{tag}}" ] && [ -n "$dseq" ]; then
        uv run just-akash api tag --dseq "$dseq" --name "{{tag}}"
    fi

# SSH into a running instance (auto-detects DSEQ if only one)
connect dseq="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/connect-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=connect finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=connect started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}}"
    set -x
    if [ -n "{{dseq}}" ]; then
        uv run just-akash api connect --dseq={{dseq}}
    else
        uv run just-akash api connect
    fi

# Stop an instance (picks interactively if no DSEQ given)
down dseq="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/down-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=down finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=down started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}}"
    set -x
    if [ -n "{{dseq}}" ]; then
        uv run just-akash api close --dseq={{dseq}}
    else
        uv run just-akash api close
    fi

# Stop all instances
down-all:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/down-all-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=down-all finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=down-all started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run just-akash api close-all

# Tag a deployment with a name
# Usage: just tag DSEQ my-backtest
tag dseq name:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/tag-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=tag finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=tag started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}} name={{name}}"
    set -x
    uv run just-akash api tag --dseq={{dseq}} --name "{{name}}"

# ── Info ─────────────────────────────────────────────

# List active instances
ls:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/ls-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=ls finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=ls started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run just-akash api list

# Show instance details (picks interactively if no DSEQ given)
status dseq="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/status-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=status finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=status started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}}"
    set -x
    if [ -n "{{dseq}}" ]; then
        uv run just-akash api status --dseq={{dseq}}
    else
        uv run just-akash api status
    fi

# ── Testing ──────────────────────────────────────────

# Full lifecycle test: up → verify provider → SSH → down → cleanup
test timeout="240":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/test-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=test finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=test started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file timeout={{timeout}}"
    set -x
    uv run python -m just_akash.test_lifecycle

# ── Lint & Quality ───────────────────────────────────

# Run ruff lint + format check
lint:
    uv run ruff check . && uv run ruff format --check .

# Run pyright type check
typecheck:
    uv run pyright

# Run ruff format (auto-fix)
fmt:
    uv run ruff format .

# Run ruff check (auto-fix)
check:
    uv run ruff check --fix .

# ── Secrets ──────────────────────────────────────────

# Scan for secrets with gitleaks
secrets:
    gitleaks detect --no-banner -v

# ── Advanced ─────────────────────────────────────────

# Deploy with custom SDL (e.g. no SSH, different image)
deploy sdl="sdl/cpu-backtest-ssh.yaml" image="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/deploy-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=deploy finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=deploy started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file sdl={{sdl}} image={{image}}"
    set -x
    cmd="uv run just-akash deploy --sdl {{sdl}}"
    if [ -n "{{image}}" ]; then cmd="$cmd --image {{image}}"; fi
    eval "$cmd"

# ── Variables ────────────────────────────────────────
log_dir := ".logs/just"
