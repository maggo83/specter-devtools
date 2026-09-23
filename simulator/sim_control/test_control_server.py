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


def test_get_state_handles_device_state_without_active_wallet():
    server = ControlServer.__new__(ControlServer)
    server.nav = NavigationController()

    result = server._cmd_get_state()

    assert result["ok"] is True
    assert result["specter"]["active_wallet"] is None
    assert result["ui"]["current_menu_id"] == "main"