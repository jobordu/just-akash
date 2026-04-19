"""
Abstract transport interface for just-akash shell commands.

All transports implement: prepare(), exec(), inject(), connect(), validate().
SSHTransport: wraps existing SSH subprocess logic (v1.4 behavior).
LeaseShellTransport: WebSocket-based (stub in Phase 6; implemented in Phase 7).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransportConfig:
    """Configuration for a transport instance."""
    dseq: str
    api_key: str
    deployment: dict[str, Any] = field(default_factory=dict)
    console_url: str = "https://console-api.akash.network"
    service_name: str | None = None
    ssh_key_path: str | None = None


class Transport(ABC):
    """
    Abstract base for shell transport mechanisms.

    Phase 6: SSHTransport (full) + LeaseShellTransport (stub).
    Phase 7+: LeaseShellTransport fully implemented.
    """

    @abstractmethod
    def prepare(self) -> None:
        """Validate transport can be used; raise RuntimeError if not."""
        ...

    @abstractmethod
    def exec(self, command: str) -> int:
        """Execute command remotely; return exit code (0 = success)."""
        ...

    @abstractmethod
    def inject(self, remote_path: str, content: str) -> None:
        """Write content to remote_path on the container."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Open interactive shell session (replaces current process via execvp)."""
        ...

    @abstractmethod
    def validate(self) -> bool:
        """Return True if transport can be used with current deployment."""
        ...
