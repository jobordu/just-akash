#!/usr/bin/env python3
"""
Multi-step Akash deployment orchestrator.

Workflow:
1. Read SDL file
2. Create deployment via Console API
3. Poll for bids (every 5s)
4. Select cheapest bid
5. Create lease with provider
6. Return deployment DSEQ and lease details
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from akash_api import AkashConsoleAPI, _extract_provider, _extract_bid_price

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
        provider = _extract_provider(b) or "unknown"
        state = b.get("state", b.get("bid", {}).get("state", "?"))
        _log(
            logging.INFO,
            f"    [{i + 1}] provider={provider}  price={_fmt_price(b)}  state={state}",
        )


def deploy(
    sdl_path: str,
    gpu: bool = False,
    image: Optional[str] = None,
    wait_timeout: int = 120,
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
        f"wait_timeout={wait_timeout}s",
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

    with open(sdl_path_obj, "r") as f:
        sdl_content = f.read()
    _log(logging.DEBUG, f"SDL content length: {len(sdl_content)} bytes")

    if image:
        sdl_content = sdl_content.replace(
            "image: python:3.13-slim",
            f"image: {image}",
        )
        import re

        sdl_content = re.sub(
            r"image:\s+[^\n]+",
            f"image: {image}",
            sdl_content,
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

    # Step 2: Create deployment
    _log(logging.INFO, "STEP 2: Creating deployment via Console API...")
    try:
        deployment_response = client.create_deployment(sdl_content)
    except RuntimeError as e:
        _log(logging.ERROR, f"Create deployment FAILED: {e}")
        raise RuntimeError(f"Failed to create deployment: {e}") from e

    dseq = deployment_response.get("dseq")
    manifest = deployment_response.get("manifest", "")
    if not dseq:
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

    # Step 3: Poll for bids — wait for ALL allowed providers to bid (or timeout)
    if allowed:
        _log(
            logging.INFO,
            f"STEP 3: Polling for bids (timeout={wait_timeout}s, interval=5s, waiting for all {len(allowed)} allowed providers)...",
        )
    else:
        _log(
            logging.INFO,
            f"STEP 3: Polling for bids (timeout={wait_timeout}s, interval=5s, accepting any provider)...",
        )
    start_time = time.time()
    bids = []
    poll_count = 0
    last_bid_count = -1

    while time.time() - start_time < wait_timeout:
        poll_count += 1
        elapsed = int(time.time() - start_time)
        try:
            bids = client.get_bids(str(dseq))
            current_count = len(bids)
        except RuntimeError as e:
            _log(logging.WARNING, f"  poll #{poll_count} @ {elapsed}s: API error: {e}")
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
                    p = _extract_provider(b) or "unknown"
                    s = b.get("state", b.get("bid", {}).get("state", "?"))
                    if allowed:
                        in_allowlist = "ALLOWED" if p in allowed else "FOREIGN"
                    else:
                        in_allowlist = "ACCEPTED"
                    _log(
                        logging.INFO,
                        f"    bid[{i}] provider={p}  price={_fmt_price(b)}  state={s}  [{in_allowlist}]",
                    )

        if current_count > 0 and allowed:
            bidding_providers = {
                _extract_provider(b) for b in bids if _extract_provider(b)
            }
            still_waiting = [p for p in allowed if p not in bidding_providers]
            if still_waiting:
                print(
                    f"\r  Waiting for bids... {elapsed}s — still waiting for {len(still_waiting)} provider(s)",
                    end="",
                    flush=True,
                )
            else:
                _log(
                    logging.INFO,
                    f"  All {len(allowed)} allowed provider(s) have bid — proceeding to selection",
                )
                break
        elif current_count > 0 and not allowed:
            break
        else:
            print(
                f"\r  Waiting for bids... {elapsed}s (poll #{poll_count})",
                end="",
                flush=True,
            )

        time.sleep(5)

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
        raise RuntimeError(
            f"No bids received within {wait_timeout}s. "
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
            _log(
                logging.WARNING, f"NO BID FROM {len(no_bid_from)} allowed provider(s):"
            )
            for p in no_bid_from:
                _log(logging.WARNING, f"  {p}")
                try:
                    prov_info = client.get_provider(p)
                    if prov_info:
                        online = prov_info.get("isOnline")
                        valid = prov_info.get("isValidVersion")
                        uptime = prov_info.get("uptime1d")
                        stats = prov_info.get("stats", {})
                        cpu = stats.get("cpu", {})
                        mem = stats.get("memory", {})
                        _log(
                            logging.WARNING,
                            f"    on-chain status: isOnline={online} isValidVersion={valid} "
                            f"uptime1d={uptime} cpu_avail={cpu.get('available')} cpu_active={cpu.get('active')} "
                            f"mem_avail={mem.get('available')} mem_active={mem.get('active')}",
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
        our_bids = [b for b in bids if _extract_provider(b) in allowed]
        foreign_bids = [b for b in bids if _extract_provider(b) not in allowed]

        _log_bid_table(our_bids, "ALLOWED PROVIDERS")
        _log_bid_table(foreign_bids, "FOREIGN (rejected)")

        if not our_bids:
            foreign = [_extract_provider(b) or "unknown" for b in bids]
            _log(
                logging.ERROR, f"All {len(bids)} bid(s) are from non-allowed providers"
            )
            _log(logging.ERROR, f"  Allowed: {allowed}")
            _log(logging.ERROR, f"  Received from: {foreign}")
            raise RuntimeError(
                f"Received {len(bids)} bid(s) but NONE from our providers.\n"
                f"  Allowed: {allowed}\n"
                f"  Received from: {foreign}\n"
                "Check that your providers are online and have capacity."
            )
    else:
        our_bids = bids
        _log_bid_table(our_bids, "ALL BIDS (no allowlist)")

    # Step 5: Select cheapest bid
    _log(logging.INFO, "STEP 5: Selecting cheapest bid from allowed providers...")
    for i, b in enumerate(sorted(our_bids, key=lambda b: _extract_bid_price(b)[0])):
        p = _extract_provider(b) or "unknown"
        marker = " <-- SELECTED" if i == 0 else ""
        _log(
            logging.INFO, f"  rank[{i + 1}] provider={p}  price={_fmt_price(b)}{marker}"
        )

    cheapest_bid = min(our_bids, key=lambda b: _extract_bid_price(b)[0])
    provider = _extract_provider(cheapest_bid) or ""
    price_amount, price_denom = _extract_bid_price(cheapest_bid)

    if not provider:
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
        raise RuntimeError(f"Failed to create lease: {e}") from e

    _log(logging.INFO, "Lease created successfully!")
    _log(
        logging.INFO,
        f"DEPLOYMENT SUMMARY  DSEQ={dseq}  provider={provider}  price={price_amount} {price_denom}",
    )
    print(f"\nDeployment Summary:")
    print(f"  DSEQ: {dseq}")
    print(f"  Provider: {provider}")
    print(f"  Price: {price_amount} {price_denom}")
    print(f"\nUse 'just status {dseq}' to check deployment status")

    return {
        "dseq": dseq,
        "provider": provider,
        "price": price_amount,
        "price_denom": price_denom,
        "lease": lease_response,
    }


def main():
    """CLI entry point."""
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
        "--wait-timeout",
        type=int,
        default=120,
        help="Seconds to wait for bids (default: 120)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("AKASH_DEBUG") else logging.INFO,
        format="",
    )

    try:
        result = deploy(
            sdl_path=args.sdl,
            gpu=args.gpu,
            image=args.image,
            wait_timeout=args.wait_timeout,
        )
        sys.exit(0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
