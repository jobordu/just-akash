#!/usr/bin/env python3
"""
End-to-end lifecycle test for Akash deployments.

Tests the real user workflow by calling `just` targets:
  just up → just ls → just status → just connect (SSH verify) → just down → just ls

Requires AKASH_API_KEY, AKASH_PROVIDERS, and SSH_PUBKEY in environment.

Usage:
    just test
"""

import os
import re
import subprocess
import sys
import time

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

TOTAL_STEPS = 7


def log_step(n, msg):
    print(f"\n{BOLD}[{n}/{TOTAL_STEPS}]{RESET} {msg}")


def log_pass(msg):
    print(f"  {GREEN}PASS{RESET} {msg}")


def log_fail(msg):
    print(f"  {RED}FAIL{RESET} {msg}")


def log_info(msg):
    print(f"  {YELLOW}INFO{RESET} {msg}")


def run(cmd: str, timeout: int = 60, input_text: str = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
    )


def main():
    failures = []
    dseq = None

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Akash Lifecycle Test (SSH){RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    log_step(1, "Validate environment")

    for var in ("AKASH_API_KEY", "AKASH_PROVIDERS", "SSH_PUBKEY"):
        if os.environ.get(var):
            log_pass(f"{var} is set")
        else:
            log_fail(f"{var} not set")
            sys.exit(1)

    providers = [p.strip() for p in os.environ["AKASH_PROVIDERS"].split(",") if p.strip()]
    log_info(f"Allowed providers: {len(providers)}")
    for p in providers:
        log_info(f"  {p}")

    ssh_key = None
    for candidate in [
        os.path.expanduser(f"~/.ssh/id_ed25519_akash_node{i}") for i in range(1, 4)
    ] + [os.path.expanduser("~/.ssh/id_ed25519")]:
        if os.path.exists(candidate):
            ssh_key = candidate
            break
    if not ssh_key:
        log_fail("No SSH private key found")
        sys.exit(1)
    log_pass(f"SSH key: {ssh_key}")

    log_step(2, "just ls — check initial state")

    r = run("just ls")
    if r.returncode != 0:
        log_fail(f"just ls failed: {r.stderr.strip()}")
        sys.exit(1)
    log_pass("API reachable")
    log_info(r.stdout.strip())

    log_step(3, "just up — deploy SSH instance")

    r = run("just up", timeout=300)
    output = r.stdout + r.stderr
    print(output)

    if r.returncode != 0:
        log_fail("just up failed")
        failures.append(f"up: exit {r.returncode}")
        m = re.search(r"DSEQ[:\s]+(\d+)", output)
        if m:
            dseq = m.group(1)
            _cleanup(dseq)
        _summary(failures)
        sys.exit(1)

    m = re.search(r"DSEQ[:\s]+(\d+)", output)
    if not m:
        log_fail("Could not parse DSEQ from 'just up' output")
        failures.append("up: no dseq in output")
        _summary(failures)
        sys.exit(1)

    dseq = m.group(1)
    log_pass(f"Deployed: DSEQ={dseq}")

    log_step(4, f"just status {dseq} — verify our provider")

    log_info("Waiting 10s for lease propagation...")
    time.sleep(10)

    r = run(f"just status {dseq}")
    status_output = r.stdout
    print(status_output)

    if r.returncode != 0:
        log_fail(f"just status failed: {r.stderr.strip()}")
        failures.append("status: failed")
    else:
        provider_found = False
        for p in providers:
            if p in status_output:
                log_pass(f"CONFIRMED: running on OUR provider: {p}")
                provider_found = True
                break
        if not provider_found:
            log_fail("Provider not found in status output or not ours")
            failures.append("status: foreign or missing provider")

        if "ssh -p" in status_output:
            log_pass("SSH connection info available")
        else:
            log_info("No SSH info in status (port may still be propagating)")

    log_step(5, f"just connect {dseq} — SSH into container")

    ssh_match = re.search(r"ssh -p (\d+) root@(\S+)", status_output)

    if not ssh_match:
        log_info("Retrying status for SSH details...")
        time.sleep(5)
        r = run(f"just status {dseq}")
        status_output = r.stdout
        ssh_match = re.search(r"ssh -p (\d+) root@(\S+)", status_output)

    if not ssh_match:
        log_fail("Could not extract SSH host:port from status")
        failures.append("connect: no SSH endpoint")
    else:
        ssh_port = ssh_match.group(1)
        ssh_host = ssh_match.group(2)
        log_info(f"Target: {ssh_host}:{ssh_port}")
        log_info("Probing SSH (retrying up to 3 min for sshd to start)...")

        connected = False
        for attempt in range(1, 19):
            try:
                result = subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "UserKnownHostsFile=/dev/null",
                        "-o",
                        "ConnectTimeout=10",
                        "-o",
                        "BatchMode=yes",
                        "-i",
                        ssh_key,
                        "-p",
                        ssh_port,
                        f"root@{ssh_host}",
                        "echo akash-ssh-ok",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if "akash-ssh-ok" in result.stdout:
                    connected = True
                    break
            except (subprocess.TimeoutExpired, OSError):
                pass
            print(f"\r  SSH attempt {attempt}/18 — waiting for sshd...", end="", flush=True)
            time.sleep(10)
        print()

        if connected:
            log_pass(f"SSH connection to {ssh_host}:{ssh_port} SUCCEEDED")
        else:
            log_fail("SSH connection FAILED after 18 attempts")
            failures.append(f"connect: SSH failed to {ssh_host}:{ssh_port}")

    log_step(6, f"just down {dseq} — stop instance")

    r = run(f"just down {dseq}", input_text="y\n")
    output = r.stdout + r.stderr
    print(output.strip())

    if r.returncode != 0:
        log_fail(f"just down failed: {r.stderr.strip()}")
        failures.append("down: failed")
    elif "closed" in output.lower():
        log_pass(f"Deployment {dseq} closed")
    else:
        log_fail("Unexpected down output")
        failures.append("down: unexpected output")

    log_step(7, "just ls — verify instance is gone")

    time.sleep(3)
    r = run("just ls")
    ls_output = r.stdout

    if dseq not in ls_output:
        log_pass(f"Deployment {dseq} no longer in list")
    else:
        log_fail(f"Deployment {dseq} still in list")
        failures.append("cleanup: still active")

    _summary(failures)
    sys.exit(1 if failures else 0)


def _cleanup(dseq: str):
    log_info(f"Cleaning up {dseq}...")
    run(f"just down {dseq}", input_text="y\n", timeout=30)


def _summary(failures: list):
    passed = TOTAL_STEPS - len(failures)
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    if failures:
        print(f"{RED}{BOLD}  FAILED{RESET} — {passed}/{TOTAL_STEPS} steps passed")
        for f in failures:
            print(f"  {RED}x{RESET} {f}")
    else:
        print(f"{GREEN}{BOLD}  ALL PASSED{RESET} — {TOTAL_STEPS}/{TOTAL_STEPS} steps")
    print(f"{BOLD}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
