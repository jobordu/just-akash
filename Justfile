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
        uv run just-akash tag --dseq "$dseq" --name "{{tag}}"
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
        uv run just-akash connect --dseq={{dseq}}
    else
        uv run just-akash connect
    fi

# Destroy an instance (picks interactively if no DSEQ given)
destroy dseq="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/destroy-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=destroy finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=destroy started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}}"
    set -x
    if [ -n "{{dseq}}" ]; then
        uv run just-akash destroy --dseq={{dseq}}
    else
        uv run just-akash destroy
    fi

# Destroy all instances
destroy-all:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/destroy-all-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=destroy-all finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=destroy-all started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run just-akash destroy-all

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
    uv run just-akash tag --dseq={{dseq}} --name "{{name}}"

# Inject secrets into a running instance via SSH
# Usage: just inject [dseq] [env-file]
#   just inject "" .env.secrets
#   just inject 12345 .env.secrets
inject dseq="" env-file=".env.secrets":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/inject-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=inject finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=inject started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}} env_file={{env-file}}"
    set -x
    cmd="uv run just-akash inject --env-file {{env-file}}"
    if [ -n "{{dseq}}" ]; then cmd="$cmd --dseq={{dseq}}"; fi
    eval "$cmd"

# Execute a command on a running instance via SSH
# Usage: just exec [dseq] "command"
exec dseq="" command="":
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/exec-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=exec finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=exec started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file dseq={{dseq}} command={{command}}"
    set -x
    cmd="uv run just-akash exec '{{command}}'"
    if [ -n "{{dseq}}" ]; then cmd="$cmd --dseq={{dseq}}"; fi
    eval "$cmd"

# ── Info ─────────────────────────────────────────────

# List active instances
list:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/list-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=list finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=list started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run just-akash list

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
        uv run just-akash status --dseq={{dseq}}
    else
        uv run just-akash status
    fi

# ── Testing ──────────────────────────────────────────

# Full lifecycle test: up → verify provider → SSH → down → cleanup
test:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/test-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=test finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=test started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run python -m just_akash.test_lifecycle

# Secrets injection E2E: deploy → inject via lease-shell → verify via SSH → cleanup
test-secrets:
    #!/bin/bash
    set -euo pipefail
    mkdir -p "{{log_dir}}"
    timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
    log_file="{{log_dir}}/test-secrets-${timestamp}.log"
    exec > >(tee -a "$log_file") 2>&1
    trap 'status=$?; echo "[INFO] recipe=test-secrets finished_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") exit_code=${status} log_file=${log_file}"' EXIT
    echo "[INFO] recipe=test-secrets started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ") cwd=$PWD log_file=$log_file"
    set -x
    uv run python -m just_akash.test_secrets_e2e

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
