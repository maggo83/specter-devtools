import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sim_control import app_control


class DeviceState:
    is_locked = True
    pin = "21"
    loaded_seeds = ["seed"]
    registered_wallets = []
    hasQR = True
    enabledSD = False

    def USB_enabled(self):
        return True


class UIState:
    current_menu_id = "main"
    history = []
    modal = None


class Application:
    def __init__(self, timers):
        self.device_state = DeviceState()
        self.ui_state = UIState()
        self.timers = timers
        self.calls = []

    def navigate_to(self, target):
        self.calls.append(("navigate_to", target, list(self.timers)))
        self.ui_state.current_menu_id = target or "previous"

    def rebuild_slot(self, name):
        self.calls.append(("rebuild_slot", name, list(self.timers)))

    def refresh_ui(self):
        self.calls.append(("refresh_ui", None, list(self.timers)))


@pytest.fixture
def app(monkeypatch):
    timers = []
    monkeypatch.setattr(app_control, "lv", types.SimpleNamespace(timer_enable=timers.append))
    return Application(timers)


def test_get_state_reads_flags_from_methods_and_attributes(app):
    state = app_control.get_state(app)

    assert state["ok"] is True
    assert state["specter"]["enabledUSB"] is True
    assert state["specter"]["hasQR"] is True
    assert state["specter"]["enabledSD"] is False
    assert state["specter"]["loaded_seed_count"] == 1
    assert state["ui"]["current_menu_id"] == "main"


def test_navigate_runs_with_timers_paused(app):
    result = app_control.navigate(app, "manage_device")

    assert app.calls == [("navigate_to", "manage_device", [False])]
    assert app.timers == [False, True]
    assert result["navigated"] == "manage_device"
    assert result["ui"]["current_menu_id"] == "manage_device"


def test_back_navigates_to_none(app):
    assert app_control.navigate(app, "back")["navigated"] == "back"
    assert app.calls[0][1] is None


def test_set_state_rebuilds_with_timers_paused(app):
    assert app_control.set_state(app, "is_locked", False) == {"ok": True, "set": {"is_locked": False}}
    assert app.device_state.is_locked is False
    assert [call[:2] for call in app.calls] == [("rebuild_slot", "app_screen"), ("refresh_ui", None)]
    assert all(call[2] == [False] for call in app.calls)
    assert app.timers == [False, True]


@pytest.mark.parametrize("attr", ["_hidden", "missing", "", 3, None])
def test_set_state_rejects_private_or_unknown_attributes(app, attr):
    assert app_control.set_state(app, attr, 1)["ok"] is False
    assert app.calls == [] and app.timers == []


def test_timers_are_reenabled_when_navigation_fails(app):
    def broken(target):
        raise RuntimeError("rebuild failed")

    app.navigate_to = broken
    with pytest.raises(RuntimeError, match="rebuild failed"):
        app_control.navigate(app, "main")
    assert app.timers == [False, True]
