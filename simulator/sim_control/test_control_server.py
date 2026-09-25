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

class FakeDevice:
    """Fake clock, animation count, and pointer for settle tests."""

    def __init__(self, monkeypatch):
        from sim_control import control_server, touch

        self.now, self.anims, self.finger_down = 0, 0, True
        monkeypatch.setattr(touch, "utime", types.SimpleNamespace(
            ticks_ms=lambda: self.now, ticks_diff=lambda a, b: a - b))
        monkeypatch.setattr(touch, "lv", types.SimpleNamespace(anim_count_running=lambda: self.anims))
        monkeypatch.setattr(control_server.control, "pointer", lambda: types.SimpleNamespace(
            busy=lambda: self.finger_down))
        monkeypatch.setattr(control_server.control, "handle", lambda request: (
            {"ok": True, "_settle_ms": 1000} if request["action"] == "touch" else {"ok": True, "tree": {}}))
        self.server = ControlServer.__new__(ControlServer)
        self.server.client, self.server.pending, self.server.settle = None, None, None
        self.server._check_connection = lambda: None
        self.sent = []
        self.server._send_response = self.sent.append
        self.server.buf = (b'{"action":"control","request":{"action":"touch"}}\n'
                           b'{"action":"control","request":{"action":"tree"}}\n')

    def poll(self, advance_ms=0):
        self.now += advance_ms
        self.server._poll(None)


def test_reply_waits_for_the_finger_and_the_animations(monkeypatch):
    device = FakeDevice(monkeypatch)

    device.poll()
    assert device.sent == []          # finger still down

    device.finger_down, device.anims = False, 1
    device.poll(50)
    device.poll(200)
    assert device.sent == []          # transition animating

    device.anims = 0
    device.poll(10)
    device.poll(40)
    assert device.sent == []          # not quiet for long enough yet
    device.poll(40)
    assert device.sent == [{"ok": True, "settled": True}, {"ok": True, "tree": {}}]


def test_reply_reports_a_settle_timeout(monkeypatch):
    device = FakeDevice(monkeypatch)
    device.finger_down, device.anims = False, 1

    device.poll()
    device.poll()                     # finger lifted: the settle timeout starts here
    device.poll(999)
    assert device.sent == []
    device.poll(1)

    assert device.sent == [{"ok": True, "settled": False}, {"ok": True, "tree": {}}]
