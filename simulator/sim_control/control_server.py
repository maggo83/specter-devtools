"""TCP control server for simulator - runs inside MicroPython."""
import socket
import json
import lvgl as lv

from . import simulator_control_runtime as control


class ControlServer:
    """Non-blocking TCP server for remote control of simulator."""

    def __init__(self, nav_controller, port=9876):
        self.nav = nav_controller
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

        # Create LVGL timer to poll for commands
        self.timer = lv.timer_create(self._poll, 50, None)

    def _poll(self, timer):
        """Called by LVGL timer to check for commands."""
        self._check_connection()
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
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            try:
                cmd = json.loads(line.decode())
                response = self._handle_command(cmd)
            except Exception as e:
                response = {"ok": False, "error": str(e)}
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
        """Route command to handler."""
        action = cmd.get("action")

        if action == "widget_tree":
            return self._cmd_widget_tree()
        elif action == "click":
            return self._cmd_click(cmd)
        elif action == "get_state":
            return self._cmd_get_state()
        elif action == "set_state":
            return self._cmd_set_state(cmd)
        elif action == "ping":
            return {"ok": True, "pong": True}
        elif action == "screenshot":
            return self._cmd_screenshot()
        elif action == "navigate":
            return self._cmd_navigate(cmd)
        elif action == "dropup":
            return self._cmd_dropup(cmd)
        elif action == "write_text":
            return control.write_text(
                cmd.get("text", ""),
                path=cmd.get("path"),
                target=cmd.get("target", 0),
                layer=cmd.get("layer", "screen"),
            )
        elif action == "capabilities":
            return control.capabilities()
        elif action == "control":
            return control.handle(cmd.get("request", {}))
        else:
            return {"ok": False, "error": "Unknown action: " + str(action)}

    def _cmd_dropup(self, cmd):
        """Directly toggle / open / close a drop-up panel."""
        which = cmd.get("which", "seed")   # "seed" or "wallet"
        op = cmd.get("op", "toggle")        # "toggle", "open", "close"
        nav = self.nav
        dropup = getattr(nav, "_seed_dropup" if which == "seed" else "_wallet_dropup", None)
        if dropup is None:
            return {"ok": False, "error": "dropup not registered: " + which}
        try:
            if op == "open":
                dropup.open()
            elif op == "close":
                dropup.close()
            else:
                dropup.toggle()
            return {"ok": True, "op": op, "which": which, "is_open": dropup.is_open()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _cmd_navigate(self, cmd):
        """Navigate to a menu or back."""
        return control.navigate(cmd.get("target"))

    def _cmd_widget_tree(self):
        """Return full widget tree (screen + layer_top)."""
        tree = control.get_tree()["root"]
        # Also include layer_top (where modals/overlays live)
        try:
            top = control.get_tree("top")["root"]
            if top["children"]:
                tree["layer_top"] = top
        except:
            pass
        return {"ok": True, "tree": tree}

    def _cmd_click(self, cmd):
        """Click widget by text or screen coordinates."""
        return control.click(
            text=cmd.get("text"),
            path=cmd.get("path"),
            x=cmd.get("x"),
            y=cmd.get("y"),
            layer=cmd.get("layer", "screen"),
        )

    def _cmd_get_state(self):
        """Return DeviceState and UIState."""
        if not control.has_application():
            control.bind_application(self.nav)
        return control.get_state()

    def _cmd_set_state(self, cmd):
        """Set attribute on DeviceState."""
        return control.set_state(cmd.get("attr"), cmd.get("value"))

    def _cmd_screenshot(self):
        """Capture screenshot - writes to file, returns path for MCP to read."""
        try:
            import SDL
            # Write screenshot directly to file (bypasses Python heap)
            filename = "/tmp/sim_screenshot.raw"
            w, h, _ = SDL.screenshot(filename)

            return {"ok": True, "width": w, "height": h, "format": "RGB565", "file": filename}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
