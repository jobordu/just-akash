"""
just_akash.transport — transport abstraction for shell commands.

Public API:
    Transport           — abstract base class
    TransportConfig     — configuration dataclass
    SSHTransport        — SSH subprocess transport (v1.4 behavior)
    LeaseShellTransport — WebSocket transport (stub in Phase 6)
    make_transport()    — factory function
"""

from .base import Transport, TransportConfig
from .lease_shell import LeaseShellTransport
from .ssh import SSHTransport

__all__ = [
    "Transport",
    "TransportConfig",
    "SSHTransport",
    "LeaseShellTransport",
    "make_transport",
]


def make_transport(transport_name: str, **kwargs: object) -> Transport:
    """
    Factory: create and return a Transport for the given name.

    Args:
        transport_name: 'ssh' or 'lease-shell'
        **kwargs: passed to TransportConfig (dseq, api_key, deployment, ...)

    Raises:
        ValueError: if transport_name is not 'ssh' or 'lease-shell'
    """
    config = TransportConfig(**kwargs)  # type: ignore[arg-type]
    if transport_name == "ssh":
        return SSHTransport(config)
    elif transport_name == "lease-shell":
        return LeaseShellTransport(config)
    raise ValueError(f"Unknown transport: {transport_name!r} (expected 'ssh' or 'lease-shell')")
