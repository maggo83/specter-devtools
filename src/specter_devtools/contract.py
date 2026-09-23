"""Target-independent control types."""

from pathlib import Path
from typing import Protocol, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
ControlRequest: TypeAlias = dict[str, JSONValue]
ControlResponse: TypeAlias = dict[str, JSONValue]


class TargetError(RuntimeError):
    """Raised when a target transport cannot complete an operation."""


class ControlTarget(Protocol):
    """Host-side adapter for a controllable development target."""

    def request(self, request: ControlRequest) -> ControlResponse:
        """Send one canonical UI-control request."""

    def screenshot(self, output: Path) -> ControlResponse:
        """Capture the visible framebuffer as a PNG."""
