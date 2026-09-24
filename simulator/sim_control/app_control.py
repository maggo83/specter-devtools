"""MockUI application control, shared by the simulator and boards.

Runs on the device against the running SpecterGui. Boards receive this file's
source over the REPL; the simulator freezes it.
"""
import lvgl as lv

_FLAGS = (
    ("hasUSB", "hasUSB"), ("enabledUSB", "USB_enabled"),
    ("hasQR", "hasQR"), ("enabledQR", "QR_enabled"),
    ("hasSD", "hasSD"), ("enabledSD", "SD_enabled"), ("detectedSD", "SD_detected"),
    ("hasSmartCard", "hasSmartCard"), ("enabledSmartCard", "SmartCard_enabled"),
    ("detectedSmartCard", "SmartCard_detected"),
)


def _flag(device_state, method, attr):
    value = getattr(device_state, method, None)
    return value() if callable(value) else getattr(device_state, attr, False)


def _wallet_info(wallet):
    return {
        "name": getattr(wallet, "label", getattr(wallet, "name", None)),
        "descriptor": getattr(wallet, "descriptor", getattr(wallet, "xpub", None)),
        "isMultiSig": getattr(wallet, "isMultiSig", False),
        "net": getattr(wallet, "net", "mainnet"),
    }


def get_state(application):
    """Return MockUI device and navigation state."""
    device_state = application.device_state
    ui_state = application.ui_state
    active_wallet = getattr(device_state, "active_wallet", None)
    if active_wallet is None:
        active_wallet = getattr(ui_state, "active_wallet", None)
    loaded_seeds = getattr(device_state, "loaded_seeds", [])
    specter = {
        "seed_loaded": bool(loaded_seeds),
        "loaded_seed_count": len(loaded_seeds),
        "is_locked": getattr(device_state, "is_locked", False),
        "pin": getattr(device_state, "pin", None),
        "active_wallet": _wallet_info(active_wallet) if active_wallet else None,
        "registered_wallets": [_wallet_info(w) for w in getattr(device_state, "registered_wallets", [])],
    }
    for attr, method in _FLAGS:
        specter[attr] = _flag(device_state, method, attr)
    return {
        "ok": True,
        "specter": specter,
        "ui": {
            "current_menu_id": ui_state.current_menu_id,
            "history": [s.menu_id if hasattr(s, "menu_id") else s for s in getattr(ui_state, "history", [])],
            "modal": getattr(ui_state, "modal", None),
        },
    }


def _paused(action):
    # Boards call this outside LVGL's update; paused timers keep app timers off half-built screens.
    lv.timer_enable(False)
    try:
        action()
    finally:
        lv.timer_enable(True)


def navigate(application, target="back"):
    """Open a menu by id, or go back; return the new state."""
    back = target in (None, "back")
    _paused(lambda: application.navigate_to(None if back else target))
    result = get_state(application)
    result["navigated"] = "back" if back else target
    return result


def set_state(application, attr, value):
    """Set a public DeviceState attribute and rebuild the visible screen."""
    device_state = application.device_state
    if not isinstance(attr, str) or not attr or attr.startswith("_") or not hasattr(device_state, attr):
        return {"ok": False, "error": "Unknown or private state attribute: " + str(attr)}

    def apply():
        setattr(device_state, attr, value)
        application.rebuild_slot("app_screen")
        application.refresh_ui()

    _paused(apply)
    return {"ok": True, "set": {attr: value}}
