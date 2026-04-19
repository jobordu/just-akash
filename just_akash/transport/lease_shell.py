"""
Lease-shell WebSocket transport stub (Phase 6).

Full implementation in Phase 7 after PROTOCOL.md is written.
See docs/PROTOCOL.md for endpoint URL, auth format, and frame schema.
"""

from .base import Transport, TransportConfig


class LeaseShellTransport(Transport):
    """
    WebSocket-based lease-shell transport.

    Phase 6: stub only — all methods raise NotImplementedError.
    Phase 7: implements prepare() + exec() using websockets library.
    Phase 8-9: implements inject() + connect().
    """

    def __init__(self, config: TransportConfig) -> None:
        self._config = config

    def prepare(self) -> None:
        raise NotImplementedError(
            "LeaseShellTransport not yet implemented. "
            "Available in Phase 7. Use --transport ssh for now."
        )

    def exec(self, command: str) -> int:
        raise NotImplementedError(
            "LeaseShellTransport not yet implemented. "
            "Use --transport ssh for now."
        )

    def inject(self, remote_path: str, content: str) -> None:
        raise NotImplementedError(
            "LeaseShellTransport not yet implemented. "
            "Use --transport ssh for now."
        )

    def connect(self) -> None:
        raise NotImplementedError(
            "LeaseShellTransport not yet implemented. "
            "Use --transport ssh for now."
        )

    def validate(self) -> bool:
        # Cannot validate without real implementation
        return False
