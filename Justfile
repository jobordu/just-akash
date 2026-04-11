set dotenv-load
set positional-arguments

log_dir := ".logs/just"

# Default recipe: list available targets
default:
    @just --list --unsorted

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
    python3 -u scripts/deploy.py --sdl sdl/cpu-backtest-ssh.yaml --wait-timeout 180 | tee /tmp/.akash-last-deploy.log
    dseq=$(sed -n 's/.*DSEQ: \([0-9]*\).*/\1/p' /tmp/.akash-last-deploy.log | head -1)
    if [ -n "{{tag}}" ] && [ -n "$dseq" ]; then
        python3 scripts/akash_api.py tag --dseq "$dseq" --name "{{tag}}"
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
        python3 scripts/akash_api.py connect --dseq {{dseq}}
    else
        python3 scripts/akash_api.py connect
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
        python3 scripts/akash_api.py close --dseq {{dseq}}
    else
        python3 scripts/akash_api.py close
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
    python3 scripts/akash_api.py close-all

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
    python3 scripts/akash_api.py tag --dseq {{dseq}} --name "{{name}}"

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
    python3 scripts/akash_api.py list

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
        python3 scripts/akash_api.py status --dseq {{dseq}}
    else
        python3 scripts/akash_api.py status
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
    python3 scripts/test_lifecycle.py --wait-timeout {{timeout}} --sdl sdl/cpu-backtest-ssh.yaml --ssh

# ── Advanced ─────────────────────────────────────────

# Deploy with custom SDL (e.g. no SSH, different image)
deploy sdl="sdl/cpu-backtest.yaml" image="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/deploy-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=deploy finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=deploy started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file sdl={{sdl}} image={{image}}"
    set -x
    cmd="python3 scripts/deploy.py --sdl {{sdl}}"
    if [ -n "{{image}}" ]; then cmd="$cmd --image {{image}}"; fi
    eval "$cmd"
