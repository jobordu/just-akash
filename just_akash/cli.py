#!/usr/bin/env python3
"""
Unified CLI for just-akash.

Subcommands:
  deploy   — Deploy to Akash Network
  api      — Interact with Akash Console API (list, status, connect, close, tag)
  test     — End-to-end lifecycle test
"""

import argparse
import logging
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="just-akash",
        description="CLI for deploying on Akash Network via the Console API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── deploy ─────────────────────────────────────────
    deploy_p = subparsers.add_parser("deploy", help="Deploy to Akash Network")
    deploy_p.add_argument("--sdl", default="sdl/cpu-backtest.yaml", help="Path to SDL file")
    deploy_p.add_argument("--gpu", action="store_true", help="Use GPU variant SDL")
    deploy_p.add_argument("--image", default=None, help="Override container image")
    deploy_p.add_argument(
        "--bid-wait", type=int, default=60, help="Seconds to wait for bids (default: 60)"
    )
    deploy_p.add_argument(
        "--bid-wait-retry",
        type=int,
        default=120,
        help="Seconds to retry if no bids (default: 120)",
    )

    # ── api ────────────────────────────────────────────
    api_p = subparsers.add_parser("api", help="Interact with Akash Console API")
    api_p.add_argument(
        "api_command", nargs="?", default=None, help="list, status, connect, close, close-all, tag"
    )
    api_p.add_argument("--dseq", default="")
    api_p.add_argument("--name", default="")
    api_p.add_argument("--key", default="")
    api_p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")

    # ── test ────────────────────────────────────────────
    test_p = subparsers.add_parser("test", help="End-to-end lifecycle test")
    test_p.add_argument("--sdl", default="sdl/cpu-backtest-ssh.yaml")
    test_p.add_argument(
        "--bid-wait", type=int, default=240, help="Total wait timeout for test (default: 240)"
    )
    test_p.add_argument("--ssh", action="store_true", help="Verify SSH connectivity")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("AKASH_DEBUG") else logging.INFO,
        format="",
    )

    if args.command == "deploy":
        from .deploy import deploy

        try:
            deploy(
                sdl_path=args.sdl,
                gpu=args.gpu,
                image=args.image,
                bid_wait=args.bid_wait,
                bid_wait_retry=args.bid_wait_retry,
            )
            sys.exit(0)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "api":
        from .api import AkashConsoleAPI, _get_tag, _load_tags, _resolve_dseq, _save_tags

        api_key = os.environ.get("AKASH_API_KEY")
        if not api_key:
            print("Error: AKASH_API_KEY not set.", file=sys.stderr)
            sys.exit(1)

        client = AkashConsoleAPI(api_key)

        from .api import (
            _extract_dseq,
            _extract_lease_provider,
            _extract_ssh_info,
            _interactive_pick,
            format_deployments_table,
        )

        cmd = args.api_command
        if not cmd:
            api_p.print_help()
            sys.exit(0)

        try:
            if cmd == "list":
                print(format_deployments_table(client.list_deployments()))

            elif cmd == "status":
                dseq = _resolve_dseq(args.dseq)
                if not dseq:
                    deployments = client.list_deployments()
                    if not deployments:
                        print("No active deployments.")
                        sys.exit(0)
                    dseq = (
                        _extract_dseq(deployments[0])
                        if len(deployments) == 1
                        else _interactive_pick(deployments, client)
                    )
                deployment = client.get_deployment(dseq)
                dep = deployment.get("deployment", deployment)
                state = dep.get("state", "unknown")
                ssh = _extract_ssh_info(deployment)
                tag = _get_tag(dseq)
                header = f"Deployment {dseq}" + (f"  ({tag})" if tag else "")
                print(f"{header}:")
                print(f"  State:    {state}")
                print(f"  Provider: {_extract_lease_provider(deployment) or 'no lease'}")
                if ssh:
                    print(f"  SSH:      ssh -p {ssh['port']} root@{ssh['host']}")

            elif cmd == "connect":
                dseq = _resolve_dseq(args.dseq)
                if not dseq:
                    deployments = client.list_deployments()
                    if not deployments:
                        print("No active deployments.")
                        sys.exit(1)
                    dseq = (
                        _extract_dseq(deployments[0])
                        if len(deployments) == 1
                        else _interactive_pick(deployments, client)
                    )
                deployment = client.get_deployment(dseq)
                ssh = _extract_ssh_info(deployment)
                if not ssh:
                    print(f"No SSH port on deployment {dseq}.")
                    sys.exit(1)
                key_path = args.key
                if not key_path:
                    for c in [
                        os.path.expanduser(f"~/.ssh/id_ed25519_akash_node{i}") for i in range(1, 4)
                    ] + [os.path.expanduser("~/.ssh/id_ed25519")]:
                        if os.path.exists(c):
                            key_path = c
                            break
                if not key_path:
                    print("No SSH key found. Specify with --key")
                    sys.exit(1)
                print(f"Connecting to {ssh['host']}:{ssh['port']}...")
                os.execvp(
                    "ssh",
                    [
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "UserKnownHostsFile=/dev/null",
                        "-i",
                        key_path,
                        "-p",
                        str(ssh["port"]),
                        f"root@{ssh['host']}",
                    ],
                )

            elif cmd == "close":
                dseq = _resolve_dseq(args.dseq)
                if not dseq:
                    deployments = client.list_deployments()
                    if not deployments:
                        print("No active deployments.")
                        sys.exit(0)
                    dseq = (
                        _extract_dseq(deployments[0])
                        if len(deployments) == 1
                        else _interactive_pick(deployments, client)
                    )
                tag = _get_tag(dseq)
                label = f"{dseq} ({tag})" if tag else dseq
                if args.yes or input(f"Close deployment {label}? (y/N) ").strip().lower() == "y":
                    client.close_deployment(dseq)
                    tags = _load_tags()
                    tags.pop(dseq, None)
                    _save_tags(tags)
                    print(f"Deployment {label} closed.")
                else:
                    print("Cancelled.")

            elif cmd == "close-all":
                deployments = client.list_deployments()
                if not deployments:
                    print("No deployments to close.")
                else:
                    print(format_deployments_table(deployments))
                    if args.yes or input("\nClose all? (y/N) ").strip().lower() == "y":
                        client.close_all_deployments()
                        tags = _load_tags()
                        for d in deployments:
                            dseq_val = _extract_dseq(d)
                            if dseq_val:
                                tags.pop(dseq_val, None)
                        _save_tags(tags)
                        print("All deployments closed.")
                    else:
                        print("Cancelled.")

            elif cmd == "tag":
                if not args.dseq or not args.name:
                    print("Usage: just-akash api tag --dseq DSEQ --name NAME")
                    sys.exit(1)
                tags = _load_tags()
                tags[args.dseq] = args.name
                _save_tags(tags)
                print(f"Tagged {args.dseq} as '{args.name}'")

            else:
                api_p.print_help()

        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "test":
        from .test_lifecycle import main as test_main

        test_main()


if __name__ == "__main__":
    main()
