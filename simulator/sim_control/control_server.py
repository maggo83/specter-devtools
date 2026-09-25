"""TCP control server for simulator - runs inside MicroPython."""
import socket
import json
import lvgl as lv

from . import simulator_control_runtime as control
from . import touch


class ControlServer:
    """Non-blocking TCP server for remote control of simulator."""

    def __init__(self, nav_controller, port=9876):
        control.bind_application(nav_controller)
        self.port = port
        self.socket = socket.socket()
        ai = socket.getaddrinfo("127.0.0.1", port)
        addr = ai[0][-1]
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(addr)
        self.socket.listen(1)
        self.socket.setblocking(False)
        self.client = None
        self.buf = b""
        self.pending = None
        self.settle = None

        # Create LVGL timer to poll for commands
        self.timer = lv.timer_create(self._poll, 50, None)

    def _poll(self, timer):
        """Called by LVGL timer to check for commands."""
        self._check_connection()
        if self.pending is not None:
            if control.pointer().busy():
                return
            if self.settle is None:
                self.settle = touch.Settle(self.pending.pop("_settle_ms"))
            if not self.settle.done():
                return
            self.pending["settled"] = not self.settle.timed_out
            self._send_response(self.pending)
            self.pending = self.settle = None
        self._process_commands()

    def _check_connection(self):
        """Accept new connections or read from existing."""
        if self.client is not None:
            try:
                b = self.client.recv(4096)
                if len(b) == 0:
                    self.client.close()
                    self.client = None
                else:
                    self.buf += b
            except OSError as e:
                if "EAGAIN" not in str(e) and "ECONNRESET" not in str(e):
                    self.client.close()
                    self.client = None
        else:
            try:
                res = self.socket.accept()
                self.client = res[0]
                self.client.setblocking(False)
            except OSError as e:
                if "EAGAIN" not in str(e):
                    pass  # No connection waiting

    def _process_commands(self):
        """Process any complete commands in buffer."""
        while b"\n" in self.buf and self.pending is None:
            line, self.buf = self.buf.split(b"\n", 1)
            try:
                cmd = json.loads(line.decode())
                response = self._handle_command(cmd)
            except Exception as e:
                response = {"ok": False, "error": str(e)}
            # Changes play out over later LVGL cycles; reply once the UI settles.
            if "_settle_ms" in response:
                self.pending = response
            else:
                self._send_response(response)

    def _send_response(self, response):
        """Send JSON response to client."""
        if self.client:
            try:
                data = json.dumps(response) + "\n"
                self.client.send(data.encode())
            except:
                pass

    def _handle_command(self, cmd):
        """Route a command: the shared control contract, or a raw screenshot."""
        action = cmd.get("action")
        if action == "control":
            return control.handle(cmd.get("request", {}))
        if action == "screenshot":
            return self._cmd_screenshot()
        return {"ok": False, "error": "Unknown action: " + str(action)}

    def _cmd_screenshot(self):
        """Capture a screenshot to a raw RGB565 file and return its path."""
        try:
            import SDL
            # Write screenshot directly to file (bypasses Python heap)
            filename = "/tmp/sim_screenshot.raw"
            w, h, _ = SDL.screenshot(filename)

            return {"ok": True, "width": w, "height": h, "format": "RGB565", "file": filename}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
