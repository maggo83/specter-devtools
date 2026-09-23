"""Simulator-only MockUI control primitives.

This module is frozen into the Unix simulator, never into STM32 firmware.
Hardware UI inspection is implemented by transient scripts sent over REPL.
"""
import lvgl as lv


_application = None


def bind_application(application):
    """Register the running SpecterGui instance for simulator-only operations."""
    global _application
    _application = application


def has_application():
    """Return whether simulator application operations are available."""
    return _application is not None


def _root_for_layer(layer):
    if layer == "screen":
        return lv.screen_active()
    if layer == "top":
        return lv.display_get_default().get_layer_top()
    raise ValueError("Unknown layer: " + str(layer))


def _safe_value(obj, name, default=None):
    try:
        return getattr(obj, name)()
    except:
        return default


def _widget_info(obj, path):
    info = {
        "path": list(path),
        "type": type(obj).__name__,
        "x": _safe_value(obj, "get_x", 0),
        "y": _safe_value(obj, "get_y", 0),
        "width": _safe_value(obj, "get_width", 0),
        "height": _safe_value(obj, "get_height", 0),
        "text": _safe_value(obj, "get_text"),
        "children": [],
    }
    for index in range(obj.get_child_count()):
        info["children"].append(_widget_info(obj.get_child(index), path + [index]))
    return info


def get_tree(layer="screen"):
    """Return a canonical widget tree rooted at the selected LVGL layer."""
    return {"layer": layer, "root": _widget_info(_root_for_layer(layer), [])}


def _find_text(obj, target, path, parent=None):
    try:
        if obj.get_text() == target:
            if type(obj).__name__.lower() == "label" and parent is not None:
                return parent, path[:-1]
            return obj, path
    except:
        pass

    for index in range(obj.get_child_count()):
        result = _find_text(obj.get_child(index), target, path + [index], obj)
        if result[0] is not None:
            return result
    return None, None


def _find_path(obj, path):
    current = obj
    for index in path:
        if not isinstance(index, int) or index < 0 or index >= current.get_child_count():
            return None
        current = current.get_child(index)
    return current


def _find_at(obj, x, y, abs_x=0, abs_y=0, path=None):
    if path is None:
        path = []

    try:
        if obj.has_flag(lv.obj.FLAG.HIDDEN):
            return None, None
    except:
        pass

    current_x = abs_x + obj.get_x()
    current_y = abs_y + obj.get_y()
    width = obj.get_width()
    height = obj.get_height()
    if not (current_x <= x <= current_x + width and current_y <= y <= current_y + height):
        return None, None

    for index in range(obj.get_child_count() - 1, -1, -1):
        result, result_path = _find_at(
            obj.get_child(index), x, y, current_x, current_y, path + [index]
        )
        if result is not None:
            return result, result_path

    return obj, path


def _click_target(widget, path):
    current = widget
    current_path = path
    while current is not None:
        if "button" in type(current).__name__.lower():
            return current, current_path
        try:
            parent = current.get_parent()
            if parent is None or parent == current:
                break
            current = parent
            current_path = current_path[:-1]
        except:
            break
    return widget, path


def _widget_summary(widget, path):
    return {
        "path": list(path),
        "type": type(widget).__name__,
        "x": _safe_value(widget, "get_x", 0),
        "y": _safe_value(widget, "get_y", 0),
        "text": _safe_value(widget, "get_text"),
    }


def find(text=None, path=None, x=None, y=None, layer="screen"):
    """Find a widget by exact text, tree path, or screen coordinates."""
    selectors = int(text is not None) + int(path is not None) + int(x is not None or y is not None)
    if selectors != 1:
        return {"ok": False, "error": "Provide exactly one selector: text, path, or x+y"}
    if (x is None) != (y is None):
        return {"ok": False, "error": "Provide both x and y"}

    root = _root_for_layer(layer)
    if text is not None:
        widget, widget_path = _find_text(root, text, [])
    elif path is not None:
        widget = _find_path(root, path)
        widget_path = path if widget is not None else None
    else:
        widget, widget_path = _find_at(root, x, y)

    if widget is None:
        return {"ok": False, "error": "Widget not found"}
    return {"ok": True, "layer": layer, "widget": _widget_summary(widget, widget_path)}


def click(text=None, path=None, x=None, y=None, layer="screen"):
    """Dispatch a click event to a widget selected by text, path, or coordinates."""
    result = find(text=text, path=path, x=x, y=y, layer=layer)
    if not result["ok"]:
        return result

    root = _root_for_layer(layer)
    widget_path = result["widget"]["path"]
    widget = _find_path(root, widget_path)
    target, target_path = _click_target(widget, widget_path)
    target.send_event(lv.EVENT.CLICKED, None)
    result["clicked"] = _widget_summary(target, target_path)
    return result


def write_text(text, path=None, target=0, layer="screen"):
    """Set a textarea's contents by canonical path or textarea index."""
    root = _root_for_layer(layer)
    if path is not None:
        textarea = _find_path(root, path)
        if textarea is None:
            return {"ok": False, "error": "Widget not found"}
        if "textarea" not in type(textarea).__name__.lower():
            return {"ok": False, "error": "Widget at path is not a textarea"}
        textarea_path = path
    else:
        textareas = []

        def collect(widget, widget_path):
            if "textarea" in type(widget).__name__.lower():
                textareas.append((widget, widget_path))
            for index in range(widget.get_child_count()):
                collect(widget.get_child(index), widget_path + [index])

        collect(root, [])
        if target < 0 or target >= len(textareas):
            return {"ok": False, "error": "Textarea index out of range"}
        textarea, textarea_path = textareas[target]

    textarea.set_text(text)
    return {
        "ok": True,
        "layer": layer,
        "widget": _widget_summary(textarea, textarea_path),
    }


def get_state():
    """Return simulator MockUI application state."""
    if _application is None:
        return {"ok": False, "error": "Application control is unavailable"}

    device_state = _application.device_state
    ui_state = _application.ui_state
    active_wallet = getattr(device_state, "active_wallet", None)
    if active_wallet is None:
        active_wallet = getattr(ui_state, "active_wallet", None)

    def wallet_info(wallet):
        return {
            "name": getattr(wallet, "label", getattr(wallet, "name", None)),
            "descriptor": getattr(wallet, "descriptor", getattr(wallet, "xpub", None)),
            "isMultiSig": getattr(wallet, "isMultiSig", False),
            "net": getattr(wallet, "net", "mainnet"),
        }

    return {
        "ok": True,
        "specter": {
            "seed_loaded": bool(getattr(device_state, "loaded_seeds", [])),
            "loaded_seed_count": len(getattr(device_state, "loaded_seeds", [])),
            "is_locked": getattr(device_state, "is_locked", False),
            "pin": getattr(device_state, "pin", None),
            "active_wallet": wallet_info(active_wallet) if active_wallet else None,
            "registered_wallets": [wallet_info(wallet) for wallet in getattr(device_state, "registered_wallets", [])],
            "hasUSB": device_state.hasUSB() if callable(getattr(device_state, "hasUSB", None)) else getattr(device_state, "hasUSB", False),
            "enabledUSB": device_state.USB_enabled() if callable(getattr(device_state, "USB_enabled", None)) else getattr(device_state, "enabledUSB", False),
            "hasQR": device_state.hasQR() if callable(getattr(device_state, "hasQR", None)) else getattr(device_state, "hasQR", False),
            "enabledQR": device_state.QR_enabled() if callable(getattr(device_state, "QR_enabled", None)) else getattr(device_state, "enabledQR", False),
            "hasSD": device_state.hasSD() if callable(getattr(device_state, "hasSD", None)) else getattr(device_state, "hasSD", False),
            "enabledSD": device_state.SD_enabled() if callable(getattr(device_state, "SD_enabled", None)) else getattr(device_state, "enabledSD", False),
            "detectedSD": device_state.SD_detected() if callable(getattr(device_state, "SD_detected", None)) else getattr(device_state, "detectedSD", False),
            "hasSmartCard": device_state.hasSmartCard() if callable(getattr(device_state, "hasSmartCard", None)) else getattr(device_state, "hasSmartCard", False),
            "enabledSmartCard": device_state.SmartCard_enabled() if callable(getattr(device_state, "SmartCard_enabled", None)) else getattr(device_state, "enabledSmartCard", False),
            "detectedSmartCard": device_state.SmartCard_detected() if callable(getattr(device_state, "SmartCard_detected", None)) else getattr(device_state, "detectedSmartCard", False),
        },
        "ui": {
            "current_menu_id": ui_state.current_menu_id,
            "history": [snapshot.menu_id if hasattr(snapshot, "menu_id") else snapshot for snapshot in getattr(ui_state, "history", [])],
            "modal": getattr(ui_state, "modal", None),
        },
    }


def navigate(target="back"):
    """Navigate the simulator MockUI application by menu id or back."""
    if _application is None:
        return {"ok": False, "error": "Application control is unavailable"}
    _application.navigate_to(None if target in (None, "back") else target)
    result = get_state()
    result["navigated"] = "back" if target in (None, "back") else target
    return result


def set_state(attr, value):
    """Set a public simulator DeviceState attribute and rebuild the visible screen."""
    if _application is None:
        return {"ok": False, "error": "Application control is unavailable"}
    if not attr or attr.startswith("_") or not hasattr(_application.device_state, attr):
        return {"ok": False, "error": "Unknown or private state attribute: " + str(attr)}

    setattr(_application.device_state, attr, value)
    _application.rebuild_slot("app_screen")
    _application.refresh_ui()
    return {"ok": True, "set": {attr: value}}


def capabilities():
    """Describe simulator and application control capabilities."""
    return {
        "ok": True,
        "ui": {
            "tree": True,
            "find": True,
            "click": ["text", "path", "coordinates"],
            "write_text": ["path", "textarea_index"],
            "layers": ["screen", "top"],
        },
        "application": has_application(),
    }


def handle(request):
    """Handle a simulator JSON-compatible control request."""
    action = request.get("action")
    layer = request.get("layer", "screen")

    if action == "tree":
        return {"ok": True, "tree": get_tree(layer)}
    if action == "find":
        return find(
            text=request.get("text"),
            path=request.get("path"),
            x=request.get("x"),
            y=request.get("y"),
            layer=layer,
        )
    if action == "click":
        return click(
            text=request.get("text"),
            path=request.get("path"),
            x=request.get("x"),
            y=request.get("y"),
            layer=layer,
        )
    if action == "write_text":
        return write_text(
            request.get("text", ""),
            path=request.get("path"),
            target=request.get("target", 0),
            layer=layer,
        )
    if action == "get_state":
        return get_state()
    if action == "navigate":
        return navigate(request.get("target"))
    if action == "set_state":
        return set_state(request.get("attr"), request.get("value"))
    if action == "capabilities":
        return capabilities()
    return {"ok": False, "error": "Unknown action: " + str(action)}