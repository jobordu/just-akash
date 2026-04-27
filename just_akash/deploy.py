#!/usr/bin/env python3
"""
Multi-step Akash deployment orchestrator.

Workflow:
1. Read SDL file
2. Create deployment via Console API
3. Poll for bids (two-phase: bid_wait, then bid_wait_retry)
4. Select cheapest bid
5. Create lease with provider
6. Return deployment DSEQ and lease details
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .api import (
    AkashConsoleAPI,
    _extract_bid_price,
    _extract_provider,
)

logger = logging.getLogger("akash.deploy")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(level: int, msg: str):
    logger.log(level, f"[{_ts()}] {msg}")
    if level >= logging.INFO:
        print(f"[{_ts()}] {msg}", flush=True)


def _fmt_price(bid) -> str:
    amount, denom = _extract_bid_price(bid)
    return f"{amount} {denom}"


def _log_bid_table(bids: list, label: str):
    if not bids:
        _log(logging.INFO, f"  {label}: (none)")
        return
    _log(logging.INFO, f"  {label}: {len(bids)} bid(s)")
    for i, b in enumerate(bids):
        if not isinstance(b, dict):
            _log(logging.INFO, f"    [{i + 1}] (invalid bid entry)")
            continue
        provider = _extract_provider(b) or "unknown"
        _nested = b.get("bid", {})
        state = b.get("state", _nested.get("state", "?") if isinstance(_nested, dict) else "?")
        _log(
            logging.INFO,
            f"    [{i + 1}] provider={provider}  price={_fmt_price(b)}  state={state}",
        )


def _inject_env_into_sdl(sdl_content: str, env_vars: list[str]) -> str:
    if not env_vars:
        return sdl_content
    override_keys = {v.split("=", 1)[0] for v in env_vars}
    env_match = re.search(r"^(\s+)env:\s*\n", sdl_content, re.MULTILINE)
    if env_match:
        indent = env_match.group(1)
        entry_indent = indent + "  "
        block_start = env_match.end()
        remaining = sdl_content[block_start:]
        lines = remaining.splitlines(keepends=True)
        kept = []
        consumed = 0
        for line in lines:
            stripped = line.rstrip("\n")
            if stripped and not stripped.startswith(entry_indent):
                break
            consumed += len(line)
            if any(re.match(r"\s*- " + re.escape(key) + r"=", line) for key in override_keys):
                continue
            kept.append(line)
        new_entries = "".join(f"{entry_indent}- {var}\n" for var in env_vars)
        return sdl_content[:block_start] + new_entries + "".join(kept) + remaining[consumed:]
    expose_match = re.search(r"^(\s+)expose:\s*\n", sdl_content, re.MULTILINE)
    if expose_match:
        indent = expose_match.group(1)
        new_block = f"{indent}env:\n"
        for var in env_vars:
            new_block += f"{indent}  - {var}\n"
        return (
            sdl_content[: expose_match.start()] + new_block + sdl_content[expose_match.start() :]
        )
    return sdl_content


def deploy(
    sdl_path: str,
    gpu: bool = False,
    image: str | None = None,
    bid_wait: int = 60,
    bid_wait_retry: int = 120,
    env_vars: list[str] | None = None,
) -> dict:
    api_key = os.environ.get("AKASH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "AKASH_API_KEY environment variable not set. "
            "Please set your API key: export AKASH_API_KEY='your-key'"
        )

    client = AkashConsoleAPI(api_key)

    providers_env = os.environ.get("AKASH_PROVIDERS", "")
    allowed = [a.strip() for a in providers_env.split(",") if a.strip()]

    _log(
        logging.INFO,
        f"CONFIG  sdl={sdl_path}  gpu={gpu}  image={image or '(default)'}  "
        f"bid_wait={bid_wait}s  bid_wait_retry={bid_wait_retry}s",
    )
    if allowed:
        _log(logging.INFO, f"ALLOWED_PROVIDERS ({len(allowed)}): {allowed}")
    else:
        _log(logging.INFO, "ALLOWED_PROVIDERS: (any — no allowlist set)")

    # Step 1: Read SDL file
    _log(logging.INFO, f"STEP 1: Reading SDL from {sdl_path}")
    sdl_path_obj = Path(sdl_path)
    if not sdl_path_obj.exists():
        raise RuntimeError(f"SDL file not found: {sdl_path}")

    with open(sdl_path_obj) as f:
        sdl_content = f.read()
    _log(logging.DEBUG, f"SDL content length: {len(sdl_content)} bytes")

    if image:
        sdl_content = re.sub(
            r"image:\s+[^\n]+",
            lambda _: f"image: {image}",
            sdl_content,
            count=1,
        )
        _log(logging.INFO, f"Overrode image to: {image}")

    if "PLACEHOLDER_SSH_PUBKEY_B64" in sdl_content:
        import base64

        ssh_pubkey = os.environ.get("SSH_PUBKEY", "")
        if not ssh_pubkey:
            raise RuntimeError(
                "SDL requires SSH_PUBKEY but it's not set. "
                "Add your public key to .env or export SSH_PUBKEY."
            )
        encoded = base64.b64encode(ssh_pubkey.encode()).decode()
        sdl_content = sdl_content.replace("PLACEHOLDER_SSH_PUBKEY_B64", encoded)
        _log(logging.INFO, "Injected SSH public key (base64) into SDL")

    if env_vars:
        sdl_content = _inject_env_into_sdl(sdl_content, env_vars)
        _log(logging.INFO, f"Injected {len(env_vars)} env var(s) into SDL (provider-visible)")

    # Step 2: Create deployment (with stale-deployment recovery)
    _log(logging.INFO, "STEP 2: Creating deployment via Console API...")
    try:
        deployment_response = client.create_deployment(sdl_content)
    except RuntimeError as e:
        if "already exists" in str(e).lower():
            _log(
                logging.WARNING,
                "Deployment already exists — closing stale deployments and retrying...",
            )
            try:
                active = client.list_deployments(active_only=True)
                for dep in active:
                    # Only close deployments without a lease (stale from failed runs)
                    leases = dep.get("leases") or dep.get("lease", [])
                    if leases:
                        continue
                    stale_dseq = dep.get("dseq") or dep.get("deployment", {}).get("dseq")
                    if stale_dseq:
                        client.close_deployment(str(stale_dseq))
                        _log(logging.INFO, f"Closed stale deployment {stale_dseq}")
            except Exception as cleanup_err:
                _log(logging.ERROR, f"Stale deployment cleanup failed: {cleanup_err}")
            # Retry once after cleanup
            try:
                deployment_response = client.create_deployment(sdl_content)
            except RuntimeError as retry_err:
                _log(logging.ERROR, f"Create deployment FAILED after retry: {retry_err}")
                raise RuntimeError(
                    f"Failed to create deployment after retry: {retry_err}"
                ) from retry_err
        else:
            _log(logging.ERROR, f"Create deployment FAILED: {e}")
            raise RuntimeError(f"Failed to create deployment: {e}") from e

    dseq = deployment_response.get("dseq")
    _manifest_raw = deployment_response.get("manifest", "")
    manifest = _manifest_raw if isinstance(_manifest_raw, str) else ""
    if dseq is None:
        _log(
            logging.ERROR,
            f"No DSEQ in response: {json.dumps(deployment_response, default=str)}",
        )
        raise RuntimeError(
            f"No DSEQ returned from API. Response: {json.dumps(deployment_response)}"
        )

    _log(logging.INFO, f"Deployment created  DSEQ={dseq}  manifest_len={len(manifest)}")
    _log(
        logging.DEBUG,
        f"Full deployment response: {json.dumps(deployment_response, default=str)[:500]}",
    )

    # Step 3: Poll for bids — wait bid_wait then pick cheapest;
    #          if no bids, wait bid_wait_retry more
    _log(
        logging.INFO,
        f"STEP 3: Polling for bids (wait {bid_wait}s, then pick cheapest; "
        f"if none, wait {bid_wait_retry}s more)...",
    )
    start_time = time.time()
    bids = []
    poll_count = 0
    last_bid_count = -1

    def _poll_bids(deadline):
        nonlocal bids, poll_count, last_bid_count
        while time.time() < deadline:
            poll_count += 1
            elapsed = int(time.time() - start_time)
            try:
                bids = client.get_bids(str(dseq))
                current_count = len(bids)
            except RuntimeError as e:
                _log(
                    logging.WARNING,
                    f"  poll #{poll_count} @ {elapsed}s: API error: {e}",
                )
                print(
                    f"\r  Waiting for bids... {elapsed}s (poll #{poll_count})",
                    end="",
                    flush=True,
                )
                time.sleep(5)
                continue

            if current_count != last_bid_count:
                last_bid_count = current_count
                if current_count == 0:
                    _log(logging.DEBUG, f"  poll #{poll_count} @ {elapsed}s: 0 bids")
                else:
                    _log(
                        logging.INFO,
                        f"  poll #{poll_count} @ {elapsed}s: {current_count} bid(s) received",
                    )
                    for i, b in enumerate(bids):
                        if not isinstance(b, dict):
                            continue
                        p = _extract_provider(b) or "unknown"
                        nested = b.get("bid", {})
                        nested_state = (
                            nested.get("state", "?") if isinstance(nested, dict) else "?"
                        )
                        s = b.get("state", nested_state)
                        if allowed:
                            in_allowlist = "ALLOWED" if p in allowed else "FOREIGN"
                        else:
                            in_allowlist = "ACCEPTED"
                        _log(
                            logging.INFO,
                            f"    bid[{i}] provider={p}  "
                            f"price={_fmt_price(b)}  state={s}  [{in_allowlist}]",
                        )

            if current_count > 0:
                print(f"\r  {current_count} bid(s) received after {elapsed}s", flush=True)
            else:
                print(
                    f"\r  Waiting for bids... {elapsed}s (poll #{poll_count})",
                    end="",
                    flush=True,
                )

            time.sleep(5)

    _log(logging.INFO, f"  Phase 1: waiting {bid_wait}s for bids...")
    _poll_bids(start_time + bid_wait)
    print()

    if not bids:
        _log(
            logging.WARNING,
            f"No bids after {bid_wait}s — waiting {bid_wait_retry}s more...",
        )
        _poll_bids(start_time + bid_wait + bid_wait_retry)
        print()

    if not bids:
        _log(
            logging.ERROR,
            f"No bids after {poll_count} polls over {int(time.time() - start_time)}s",
        )
        _log(
            logging.ERROR,
            "Possible causes: SDL unsatisfiable, providers offline, network partition, "
            "deposit too low, or no capacity on allowed providers",
        )
        _log(logging.INFO, f"Cleaning up deployment {dseq} (no bids)...")
        try:
            client.close_deployment(str(dseq))
            _log(logging.INFO, f"Deployment {dseq} closed after no bids received")
        except Exception as cleanup_err:
            _log(logging.ERROR, f"Cleanup of deployment {dseq} failed: {cleanup_err}")
        raise RuntimeError(
            f"No bids received within {bid_wait + bid_wait_retry}s. "
            "Your SDL may be unsatisfiable or all providers are busy."
        )

    _log(
        logging.INFO,
        f"Bid polling complete: {len(bids)} total bid(s) in {int(time.time() - start_time)}s",
    )
    _log_bid_table(bids, "ALL BIDS")

    if allowed:
        bidding_providers = {_extract_provider(b) for b in bids if _extract_provider(b)}
        no_bid_from = [p for p in allowed if p not in bidding_providers]
        if no_bid_from:
            _log(logging.WARNING, f"NO BID FROM {len(no_bid_from)} allowed provider(s):")
            for p in no_bid_from:
                _log(logging.WARNING, f"  {p}")
                try:
                    prov_info = client.get_provider(p)
                    if prov_info:
                        online = prov_info.get("isOnline")
                        valid = prov_info.get("isValidVersion")
                        uptime = prov_info.get("uptime1d")
                        stats = prov_info.get("stats") or {}
                        if not isinstance(stats, dict):
                            stats = {}
                        cpu = stats.get("cpu") or {}
                        if not isinstance(cpu, dict):
                            cpu = {}
                        mem = stats.get("memory") or {}
                        if not isinstance(mem, dict):
                            mem = {}
                        _log(
                            logging.WARNING,
                            f"    on-chain status: isOnline={online} "
                            f"isValidVersion={valid} uptime1d={uptime} "
                            f"cpu_avail={cpu.get('available')} "
                            f"cpu_active={cpu.get('active')} "
                            f"mem_avail={mem.get('available')} "
                            f"mem_active={mem.get('active')}",
                        )
                    else:
                        _log(
                            logging.WARNING,
                            "    on-chain status: NOT FOUND in provider registry",
                        )
                except RuntimeError as e:
                    _log(logging.WARNING, f"    on-chain status: query failed: {e}")

    # Step 4: Filter bids to allowed providers
    _log(logging.INFO, "STEP 4: Filtering bids...")
    if allowed:
        our_bids = [b for b in bids if isinstance(b, dict) and _extract_provider(b) in allowed]
        foreign_bids = [
            b for b in bids if isinstance(b, dict) and _extract_provider(b) not in allowed
        ]

        _log_bid_table(our_bids, "ALLOWED PROVIDERS")
        _log_bid_table(foreign_bids, "FOREIGN (rejected)")

        if not our_bids:
            foreign = [_extract_provider(b) or "unknown" for b in bids]
            _log(logging.ERROR, f"All {len(bids)} bid(s) are from non-allowed providers")
            _log(logging.ERROR, f"  Allowed: {allowed}")
            _log(logging.ERROR, f"  Received from: {foreign}")
            _log(logging.INFO, f"Cleaning up deployment {dseq} (foreign bids only)...")
            try:
                client.close_deployment(str(dseq))
                _log(logging.INFO, f"Deployment {dseq} closed after foreign bids rejection")
            except Exception as cleanup_err:
                _log(logging.ERROR, f"Cleanup of deployment {dseq} failed: {cleanup_err}")
            raise RuntimeError(
                f"Received {len(bids)} bid(s) but NONE from our providers.\n"
                f"  Allowed: {allowed}\n"
                f"  Received from: {foreign}\n"
                "Check that your providers are online and have capacity."
            )
    else:
        our_bids = [b for b in bids if isinstance(b, dict)]
        _log_bid_table(our_bids, "ALL BIDS (no allowlist)")
        if not our_bids:
            _log(logging.ERROR, f"All {len(bids)} bid(s) are invalid (non-dict entries)")
            _log(logging.INFO, f"Cleaning up deployment {dseq} (no valid bids)...")
            try:
                client.close_deployment(str(dseq))
            except Exception as cleanup_err:
                _log(logging.ERROR, f"Cleanup of deployment {dseq} failed: {cleanup_err}")
            raise RuntimeError("No valid bids received — all bid entries were malformed.")

    # Step 5: Select cheapest bid
    _log(logging.INFO, "STEP 5: Selecting cheapest bid from allowed providers...")
    for i, b in enumerate(sorted(our_bids, key=lambda b: _extract_bid_price(b)[0])):
        p = _extract_provider(b) or "unknown"
        marker = " <-- SELECTED" if i == 0 else ""
        _log(logging.INFO, f"  rank[{i + 1}] provider={p}  price={_fmt_price(b)}{marker}")

    cheapest_bid = min(our_bids, key=lambda b: _extract_bid_price(b)[0])
    provider = _extract_provider(cheapest_bid) or ""
    price_amount, price_denom = _extract_bid_price(cheapest_bid)

    if not provider:
        _log(logging.INFO, f"Cleaning up deployment {dseq} (no provider in bid)...")
        try:
            client.close_deployment(str(dseq))
            _log(logging.INFO, f"Deployment {dseq} closed after no-provider bid")
        except Exception as cleanup_err:
            _log(logging.ERROR, f"Cleanup of deployment {dseq} failed: {cleanup_err}")
        raise RuntimeError("Selected bid has no provider address")

    _log(
        logging.INFO,
        f"SELECTED  provider={provider}  price={price_amount} {price_denom}",
    )

    # Step 6: Create lease
    _log(logging.INFO, "STEP 6: Creating lease...")
    try:
        lease_response = client.create_lease(
            dseq=str(dseq),
            provider=provider,
            manifest=manifest,
        )
    except RuntimeError as e:
        _log(logging.ERROR, f"Lease creation FAILED: {e}")
        _log(logging.INFO, f"Cleaning up deployment {dseq}...")
        try:
            client.close_deployment(str(dseq))
            _log(logging.INFO, f"Deployment {dseq} closed after lease failure")
        except Exception as cleanup_err:
            _log(logging.ERROR, f"Cleanup of deployment {dseq} also failed: {cleanup_err}")
        raise RuntimeError(f"Failed to create lease: {e}") from e

    _log(logging.INFO, "Lease created successfully!")
    _log(
        logging.INFO,
        f"DEPLOYMENT SUMMARY  DSEQ={dseq}  "
        f"provider={provider}  price={price_amount} {price_denom}",
    )
    print("\nDeployment Summary:")
    print(f"  DSEQ: {dseq}")
    print(f"  Provider: {provider}")
    print(f"  Price: {price_amount} {price_denom}")
    print(f"\nUse 'just-akash status {dseq}' to check deployment status")

    return {
        "dseq": dseq,
        "provider": provider,
        "price": price_amount,
        "price_denom": price_denom,
        "lease": lease_response,
    }


def deploy_main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy to Akash Network",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sdl",
        default="sdl/cpu-backtest.yaml",
        help="Path to SDL file (default: sdl/cpu-backtest.yaml)",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use GPU variant SDL if available",
    )
    parser.add_argument(
        "--image",
        help="Override container image",
    )
    parser.add_argument(
        "--bid-wait",
        type=int,
        default=60,
        help="Seconds to wait for bids before picking cheapest (default: 60)",
    )
    parser.add_argument(
        "--bid-wait-retry",
        type=int,
        default=120,
        help="Seconds to wait for bids if none received after first phase (default: 120)",
    )
    parser.add_argument(
        "--env",
        action="append",
        dest="env_vars",
        default=[],
        help="KEY=VALUE env var to inject into SDL (repeatable, provider-visible)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("AKASH_DEBUG") else logging.INFO,
        format="",
    )

    try:
        deploy(
            sdl_path=args.sdl,
            gpu=args.gpu,
            image=args.image,
            bid_wait=args.bid_wait,
            bid_wait_retry=args.bid_wait_retry,
            env_vars=args.env_vars,
        )
        sys.exit(0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
