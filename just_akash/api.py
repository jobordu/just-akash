#!/usr/bin/env python3
"""
Akash Console API client with CLI dispatch.

Provides:
- AkashConsoleAPI class for interacting with Akash Console API
- CLI subcommands: list, status, close, close-all, logs, shell, tag
"""

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("akash.api")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


TAGS_FILE = Path(__file__).resolve().parent.parent / ".tags.json"


def _load_tags() -> dict[str, str]:
    if TAGS_FILE.exists():
        try:
            return json.loads(TAGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_tags(tags: dict[str, str]):
    TAGS_FILE.write_text(json.dumps(tags, indent=2) + "\n")


def _get_tag(dseq: str) -> str:
    return _load_tags().get(str(dseq), "")


def _resolve_dseq(identifier: str) -> str:
    if not identifier:
        return ""
    if identifier.isdigit():
        return identifier
    tags = _load_tags()
    for dseq, tag in tags.items():
        if tag == identifier:
            return dseq
    print(f"Error: No deployment found with tag '{identifier}'")
    print(f"Active tags: {', '.join(tags.values()) or 'none'}")
    sys.exit(1)


class AkashConsoleAPI:
    """Client for Akash Console API (https://console-api.akash.network)"""

    def __init__(self, api_key: str):
        self.base_url = "https://console-api.akash.network"
        self.api_key = api_key
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "akash-just-targets/1.0",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"

        logger.debug(
            f"[{_ts()}] API {method} {endpoint} data={json.dumps(data) if data else 'none'}"
        )

        request_body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(
            url,
            data=request_body,
            headers=self.headers,
            method=method,
        )

        try:
            t0 = datetime.now(timezone.utc)
            with urllib.request.urlopen(req) as response:
                response_data = response.read().decode("utf-8")
                elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
                result = json.loads(response_data) if response_data else {}
                logger.debug(
                    f"[{_ts()}] API {method} {endpoint} -> "
                    f"{response.status} ({elapsed_ms}ms) keys="
                    f"{list(result.keys()) if isinstance(result, dict) else type(result).__name__}"
                )
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            logger.error(
                f"[{_ts()}] API {method} {endpoint} -> HTTP {e.code} ({elapsed_ms}ms) "
                f"body={error_body[:500]}"
            )
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get("message", error_body)
            except json.JSONDecodeError:
                error_msg = error_body
            raise RuntimeError(f"API Error ({e.code}): {error_msg}") from e
        except urllib.error.URLError as e:
            logger.error(f"[{_ts()}] API {method} {endpoint} -> URLError: {e}")
            raise RuntimeError(f"Connection error: {e}") from e

    def list_deployments(self, active_only: bool = True) -> list[dict[str, Any]]:
        response = self._request("GET", "/v1/deployments")
        data = response.get("data", response)
        deployments = data.get("deployments", [])
        if active_only:
            deployments = [
                d for d in deployments if d.get("deployment", {}).get("state") == "active"
            ]
        return deployments

    def get_deployment(self, dseq: str) -> dict[str, Any]:
        response = self._request("GET", f"/v1/deployments/{dseq}")
        return response.get("data", response)

    def create_deployment(self, sdl_content: str, deposit: float = 5.0) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/v1/deployments",
            {"data": {"sdl": sdl_content, "deposit": deposit}},
        )
        data = response.get("data", response)
        return data

    def close_deployment(self, dseq: str) -> dict[str, Any]:
        response = self._request("DELETE", f"/v1/deployments/{dseq}")
        return response.get("data", response)

    def close_all_deployments(self) -> dict[str, Any]:
        deployments = self.list_deployments()
        results = []
        for deployment in deployments:
            dep_dseq = _extract_dseq(deployment)
            if not dep_dseq:
                continue
            try:
                result = self.close_deployment(dep_dseq)
                results.append(result)
            except RuntimeError as e:
                print(f"Warning: Failed to close deployment {dep_dseq}: {e}")
        return {"closed": results}

    def get_bids(self, dseq: str) -> list[dict[str, Any]]:
        response = self._request("GET", f"/v1/bids?dseq={dseq}")
        data = response.get("data", response)
        if isinstance(data, list):
            return data
        return data.get("bids", [])

    def get_provider(self, owner: str) -> dict[str, Any] | None:
        try:
            response = self._request("GET", "/v1/providers")
            if isinstance(response, list):
                providers = response
            elif isinstance(response, dict):
                data = response.get("data", response)
                providers = data if isinstance(data, list) else data.get("providers", [])
            else:
                providers = []
            for p in providers:
                if isinstance(p, dict) and p.get("owner") == owner:
                    return p
        except RuntimeError:
            pass
        return None

    def create_lease(
        self, dseq: str, provider: str, manifest: str, gseq: int = 1, oseq: int = 1
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/leases",
            {
                "manifest": manifest,
                "leases": [
                    {
                        "dseq": str(dseq),
                        "gseq": gseq,
                        "oseq": oseq,
                        "provider": provider,
                    }
                ],
            },
        )


def _extract_dseq(deployment: dict[str, Any]) -> str | None:
    if "dseq" in deployment:
        return str(deployment["dseq"])
    dep = deployment.get("deployment", {})
    dep_id = dep.get("id", {})
    if "dseq" in dep_id:
        return str(dep_id["dseq"])
    return None


def _extract_provider(bid: dict[str, Any]) -> str | None:
    bid_id = bid.get("id", bid.get("bid", {}).get("id", {}))
    if "provider" in bid_id:
        return bid_id["provider"]
    return bid.get("provider")


def _extract_bid_price(bid: dict[str, Any]) -> tuple:
    price = bid.get("price", bid.get("bid", {}).get("price", {}))
    if isinstance(price, dict):
        amount = float(price.get("amount", float("inf")))
        denom = price.get("denom", "uakt")
        return (amount, denom)
    return (float(price) if price else float("inf"), "uakt")


def _extract_ssh_info(deployment: dict[str, Any]) -> dict[str, Any] | None:
    for lease in deployment.get("leases", []):
        status = lease.get("status") or {}
        fwd_ports = status.get("forwarded_ports") or {}
        for svc_name, ports in fwd_ports.items():
            for p in ports:
                if p.get("port") == 22:
                    return {
                        "host": p["host"],
                        "port": p["externalPort"],
                        "service": svc_name,
                    }
    return None


def _extract_lease_provider(deployment: dict[str, Any]) -> str | None:
    for lease in deployment.get("leases", []):
        lease_id = lease.get("id", {})
        if "provider" in lease_id:
            return lease_id["provider"]
    return None


def format_deployments_table(deployments: list[dict[str, Any]]) -> str:
    if not deployments:
        return "No active deployments."

    tags = _load_tags()
    rows = []
    for d in deployments:
        dseq = _extract_dseq(d) or "?"
        tag = tags.get(dseq, "")
        dep = d.get("deployment", d)
        state = dep.get("state", "unknown")
        provider = _extract_lease_provider(d) or "no lease"
        ssh = _extract_ssh_info(d)
        ssh_col = f"{ssh['host']}:{ssh['port']}" if ssh else "-"
        rows.append((dseq, tag, state, provider[:20], ssh_col))

    headers = ("DSEQ", "Tag", "State", "Provider", "SSH")
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=False))]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append("  ".join(v.ljust(w) for v, w in zip(row, widths, strict=False)))

    return "\n".join(lines)


def _interactive_pick(deployments: list[dict[str, Any]], client: "AkashConsoleAPI") -> str:
    import termios
    import tty

    if not sys.stdin.isatty():
        dseq = _extract_dseq(deployments[0])
        if not dseq:
            raise RuntimeError("Could not extract dseq from deployment")
        return dseq

    tags = _load_tags()
    items = []
    for d in deployments:
        dseq = _extract_dseq(d) or "?"
        tag = tags.get(dseq, "")
        provider = (_extract_lease_provider(d) or "no lease")[:24]
        ssh = _extract_ssh_info(d)
        ssh_str = f"{ssh['host']}:{ssh['port']}" if ssh else "no SSH"
        label = f"{dseq}  {tag}" if tag else dseq
        items.append((dseq, label, provider, ssh_str))

    selected = 0
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    def render():
        out = []
        if render.drawn:
            out.append(f"\033[{len(items) + 1}A")
        out.append(
            "\r\033[K\033[1mSelect deployment:\033[0m  ↑↓ navigate  Enter select  q cancel\r\n"
        )
        for i, (_, label, prov, ssh_str) in enumerate(items):
            marker = "\033[92m▸\033[0m" if i == selected else " "
            highlight = "\033[1m" if i == selected else ""
            reset = "\033[0m"
            out.append(f"\r\033[K  {marker} {highlight}{label}  {prov}  {ssh_str}{reset}\r\n")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        render.drawn = True

    render.drawn = False

    try:
        tty.setraw(fd)
        render()
        while True:
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                break
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    selected = (selected - 1) % len(items)
                elif seq == "[B":
                    selected = (selected + 1) % len(items)
                render()
            elif ch == "q" or ch == "\x03":
                sys.stdout.write("\r\nCancelled.\r\n")
                sys.stdout.flush()
                sys.exit(0)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    sys.stdout.write("\r\n")
    dseq = items[selected][0]
    print(f"Selected: {dseq}")
    return dseq


def api_main():
    api_key = os.environ.get("AKASH_API_KEY")
    if not api_key:
        print("Error: AKASH_API_KEY environment variable not set.")
        print("Please set your API key: export AKASH_API_KEY='your-key'")
        sys.exit(1)

    client = AkashConsoleAPI(api_key)

    import argparse

    parser = argparse.ArgumentParser(
        description="Akash Console API CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("list", help="List all active deployments")

    status_p = subparsers.add_parser("status", help="Show deployment details")
    status_p.add_argument("--dseq", default="")

    connect_p = subparsers.add_parser("connect", help="SSH into a running deployment")
    connect_p.add_argument("--dseq", default="")
    connect_p.add_argument("--key", default="")

    close_p = subparsers.add_parser("close", help="Close a deployment")
    close_p.add_argument("--dseq", default="")

    subparsers.add_parser("close-all", help="Close all deployments")

    tag_p = subparsers.add_parser("tag", help="Tag a deployment with a name")
    tag_p.add_argument("--dseq", required=True)
    tag_p.add_argument("--name", required=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "list":
            deployments = client.list_deployments()
            print(format_deployments_table(deployments))

        elif args.command == "status":
            dseq = _resolve_dseq(args.dseq)
            if not dseq:
                deployments = client.list_deployments()
                if not deployments:
                    if not sys.stdout.isatty():
                        print(json.dumps({"status": "down"}))
                    else:
                        print("No active deployments.")
                    sys.exit(0)
                if len(deployments) == 1:
                    dseq = _extract_dseq(deployments[0])
                    if sys.stdout.isatty():
                        print(f"Auto-selected deployment {dseq}\n")
                else:
                    dseq = _interactive_pick(deployments, client)
            deployment = client.get_deployment(dseq)
            dep = deployment.get("deployment", deployment)
            state = dep.get("state", "unknown")

            ssh = _extract_ssh_info(deployment)

            if not sys.stdout.isatty():
                canopy_status = (
                    "ready"
                    if state == "active"
                    else "down"
                    if state in ("closed", "failed")
                    else "unknown"
                )
                result: dict[str, Any] = {"status": canopy_status}
                if ssh:
                    result["endpoint"] = f"ssh -p {ssh['port']} root@{ssh['host']}"
                print(json.dumps(result))
            else:
                tag = _get_tag(dseq)
                header = f"Deployment {dseq}"
                if tag:
                    header += f"  ({tag})"
                print(f"{header}:")
                print(f"  State:    {state}")
                print(f"  Provider: {_extract_lease_provider(deployment) or 'no lease'}")

                if ssh:
                    print(f"  SSH:      ssh -p {ssh['port']} root@{ssh['host']}")

                for lease in deployment.get("leases", []):
                    lease_status = lease.get("status") or {}
                    fwd = lease_status.get("forwarded_ports") or {}
                    for svc, ports in fwd.items():
                        for p in ports:
                            if p.get("port") != 22:
                                print(
                                    f"  Port:     {p['host']}:{p['externalPort']} "
                                    f"→ {p['port']}/{p.get('proto', 'TCP')} ({svc})"
                                )

                    services = lease_status.get("services") or {}
                    for svc, info in services.items():
                        ready = info.get("ready_replicas", 0)
                        total = info.get("total", 0)
                        print(f"  Service:  {svc} ({ready}/{total} ready)")

                escrow = deployment.get("escrow_account", {}).get("state", {})
                funds = escrow.get("funds", [])
                for f in funds:
                    print(f"  Escrow:   {f.get('amount', '?')} {f.get('denom', '?')}")

        elif args.command == "connect":
            dseq = _resolve_dseq(args.dseq)
            if not dseq:
                deployments = client.list_deployments()
                if not deployments:
                    print("No active deployments.")
                    sys.exit(1)
                if len(deployments) == 1:
                    dseq = _extract_dseq(deployments[0])
                    print(f"Auto-selected deployment {dseq}")
                else:
                    dseq = _interactive_pick(deployments, client)

            deployment = client.get_deployment(dseq)
            ssh = _extract_ssh_info(deployment)
            if not ssh:
                print(f"No SSH port (22) found on deployment {dseq}.")
                print("Deploy with SSH SDL: just up")
                sys.exit(1)

            key_path = args.key
            if not key_path:
                for candidate in [
                    os.path.expanduser("~/.ssh/id_ed25519_akash_node1"),
                    os.path.expanduser("~/.ssh/id_ed25519_akash_node2"),
                    os.path.expanduser("~/.ssh/id_ed25519_akash_node3"),
                    os.path.expanduser("~/.ssh/id_ed25519"),
                    os.path.expanduser("~/.ssh/id_rsa"),
                ]:
                    if os.path.exists(candidate):
                        key_path = candidate
                        break

            if not key_path:
                print("No SSH key found. Specify with --key")
                sys.exit(1)

            cmd = [
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
            ]
            print(f"Connecting to {ssh['host']}:{ssh['port']}...")
            os.execvp("ssh", cmd)

        elif args.command == "close":
            dseq = _resolve_dseq(args.dseq)
            if not dseq:
                deployments = client.list_deployments()
                if not deployments:
                    print("No active deployments.")
                    sys.exit(0)
                if len(deployments) == 1:
                    dseq = _extract_dseq(deployments[0])
                    print(f"Auto-selected deployment {dseq}")
                else:
                    dseq = _interactive_pick(deployments, client)

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

        elif args.command == "close-all":
            deployments = client.list_deployments()
            if not deployments:
                print("No deployments to close.")
            else:
                print(f"Found {len(deployments)} active deployment(s):")
                print(format_deployments_table(deployments))
                if args.yes or input("\nClose all? (y/N) ").strip().lower() == "y":
                    client.close_all_deployments()
                    tags = _load_tags()
                    for d in deployments:
                        dseq = _extract_dseq(d)
                        if dseq:
                            tags.pop(dseq, None)
                    _save_tags(tags)
                    print("All deployments closed.")
                else:
                    print("Cancelled.")

        elif args.command == "tag":
            tags = _load_tags()
            tags[args.dseq] = args.name
            _save_tags(tags)
            print(f"Tagged {args.dseq} as '{args.name}'")

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
