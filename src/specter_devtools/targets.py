"""Host-side adapters for simulator and board targets."""

import json
from pathlib import Path
import socket
import subprocess

from .contract import ControlRequest, ControlResponse, TargetError
from .png import save_rgb565_png

TARGETS = ("simulator", "f469", "esp32-p4")
SIMULATOR_HOST = "127.0.0.1"
SIMULATOR_PORT = 9876
DEFAULT_F469_DISCO = Path(__file__).resolve().parents[2] / "f469" / "disco"
F469_DISPLAY = {"width": 480, "height": 800}
RESPONSE_TIMEOUT = 5.0


def gesture_seconds(request: ControlRequest) -> float:
    """Return how long a touch request keeps the finger down."""
    points = request.get("points") if request.get("action") == "touch" else None
    try:
        return max(0.0, float(points[-1][2]) / 1000)
    except (TypeError, ValueError, IndexError, KeyError):
        return 0.0


class SimulatorTarget:
    """Talks to the controllable Unix simulator over its NDJSON TCP endpoint."""

    def __init__(self, host: str = SIMULATOR_HOST, port: int = SIMULATOR_PORT):
        self.host = host
        self.port = port

    def _send(self, command: dict, timeout: float = RESPONSE_TIMEOUT) -> ControlResponse:
        with socket.create_connection((self.host, self.port), timeout=timeout) as connection:
            connection.sendall((json.dumps(command) + "\n").encode())
            response = b""
            while b"\n" not in response:
                chunk = connection.recv(65536)
                if not chunk:
                    raise TargetError("Simulator closed the control connection")
                response += chunk
        return json.loads(response.split(b"\n", 1)[0].decode())

    def request(self, request: ControlRequest) -> ControlResponse:
        return self._send({"action": "control", "request": request},
                          RESPONSE_TIMEOUT + gesture_seconds(request))

    def screenshot(self, output: Path) -> ControlResponse:
        result = self._send({"action": "screenshot"})
        if not result.get("ok"):
            return result
        raw = Path(result["file"]).read_bytes()
        output = Path(output)
        save_rgb565_png(raw, output, result["width"], result["height"])
        return {
            "ok": True,
            "file": str(output.resolve()),
            "width": result["width"],
            "height": result["height"],
            "format": "PNG",
        }


class F469Target:
    """Drives an STM32F469 Discovery board through the bundled disco tool."""

    def __init__(self, disco: Path | str | None = None):
        path = Path(disco) if disco else DEFAULT_F469_DISCO
        if not path.exists():
            raise TargetError("F469 disco tool not found at {}".format(path))
        self.disco = str(path.resolve())

    def _run(self, *arguments: str) -> str:
        result = subprocess.run([self.disco, *arguments], capture_output=True, text=True)
        if result.returncode != 0:
            raise TargetError(result.stderr.strip() or result.stdout.strip() or "disco command failed")
        return result.stdout.strip()

    def request(self, request: ControlRequest) -> ControlResponse:
        timeout = 10 + int(gesture_seconds(request) + 1)
        output = self._run("ui", "control", "--timeout", str(timeout),
                           json.dumps(request, separators=(",", ":")))
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            raise TargetError("disco ui control returned no response")
        return json.loads(lines[-1])

    def screenshot(self, output: Path) -> ControlResponse:
        output = Path(output).resolve()
        self._run("ui", "screenshot", str(output))
        return {"ok": True, "file": str(output), "format": "PNG", **F469_DISPLAY}

    def board(self, arguments: list[str]) -> int:
        """Run a raw board command (flash, cpu, repl, ...) with inherited output."""
        return subprocess.run([self.disco, *arguments]).returncode


def make_target(name: str, *, host: str = SIMULATOR_HOST, port: int = SIMULATOR_PORT,
                disco: Path | str | None = None):
    if name == "simulator":
        return SimulatorTarget(host, port)
    if name == "f469":
        return F469Target(disco)
    if name == "esp32-p4":
        raise TargetError("esp32-p4 support is planned but not implemented yet")
    raise TargetError("Unknown target: {}".format(name))
