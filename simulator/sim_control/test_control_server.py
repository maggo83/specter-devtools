import sys
import types
from pathlib import Path


sys.modules.setdefault("lvgl", types.SimpleNamespace())
sys.path.insert(0, str(Path(__file__).parent.parent))

from sim_control.control_server import ControlServer


class DeviceStateWithoutActiveWallet:
    loaded_seeds = []
    is_locked = False
    pin = None
    registered_wallets = []


class UIState:
    current_menu_id = "main"
    history = []
    modal = None


class NavigationController:
    device_state = DeviceStateWithoutActiveWallet()
    ui_state = UIState()


def test_get_state_handles_device_state_without_active_wallet(monkeypatch):
    from sim_control import control_server

    monkeypatch.setattr(control_server.control, "_application", NavigationController())
    server = ControlServer.__new__(ControlServer)

    result = server._handle_command({"action": "control", "request": {"action": "get_state"}})

    assert result["ok"] is True
    assert result["specter"]["active_wallet"] is None
    assert result["ui"]["current_menu_id"] == "main"


def test_only_the_contract_and_screenshots_are_served():
    server = ControlServer.__new__(ControlServer)

    for legacy in ("ping", "widget_tree", "click", "get_state", "dropup"):
        assert server._handle_command({"action": legacy}) == {"ok": False, "error": "Unknown action: " + legacy}

def test_gesture_reply_waits_until_the_finger_lifts(monkeypatch):
    from sim_control import control_server

    class Pointer:
        running = True

        def busy(self):
            return self.running

    pointer = Pointer()
    monkeypatch.setattr(control_server.control, "pointer", lambda: pointer)
    monkeypatch.setattr(control_server.control, "handle", lambda request: (
        {"ok": True, "duration_ms": 50} if request["action"] == "touch" else {"ok": True, "tree": {}}))
    server = ControlServer.__new__(ControlServer)
    server.client, server.pending = None, None
    server._check_connection = lambda: None
    sent = []
    server._send_response = sent.append
    server.buf = (b'{"action":"control","request":{"action":"touch"}}\n'
                  b'{"action":"control","request":{"action":"tree"}}\n')

    server._poll(None)
    assert sent == []

    pointer.running = False
    server._poll(None)
    assert sent == [{"ok": True, "duration_ms": 50}, {"ok": True, "tree": {}}]
