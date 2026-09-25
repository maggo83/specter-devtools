"""Target-independent artifact capture."""

import json
from pathlib import Path

from .contract import ControlResponse, ControlTarget, TargetError

_EXPLORE_SKIP = ("eng", "Back")
# MockUI translation keys, resolved in the device's current language.
_SKIP_KEYS = ("COMMON_OK", "COMMON_CANCEL")
_DISMISS_KEYS = ("MODAL_CLOSE_BTN", "COMMON_CANCEL", "TOUR_SKIP_BTN")


def visible_labels(node: dict) -> list[str]:
    """Return all non-empty text values in a canonical widget tree."""
    labels = []

    def walk(current):
        text = current.get("text")
        if text:
            labels.append(text)
        for child in current.get("children", []):
            walk(child)

    walk(node)
    return labels


def capture(target: ControlTarget, folder: Path, layer: str = "screen") -> ControlResponse:
    """Save a screenshot, canonical tree, and labels from any target."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tree_result = target.request({"action": "tree"} if layer == "screen" else {"action": "tree", "layer": layer})
    if not tree_result.get("ok"):
        return tree_result

    tree_file = folder / "tree.json"
    tree_file.write_text(json.dumps(tree_result["tree"], indent=2) + "\n")
    labels = visible_labels(tree_result["tree"]["root"])
    labels_file = folder / "labels.txt"
    labels_file.write_text("".join(label + "\n" for label in labels))
    screenshot_result = target.screenshot(folder / "screenshot.png")
    if not screenshot_result.get("ok"):
        return screenshot_result

    return {
        "ok": True,
        "files": {
            "screenshot": screenshot_result["file"],
            "tree": str(tree_file.resolve()),
            "labels": str(labels_file.resolve()),
        },
        "label_count": len(labels),
    }


def _top_layer(target: ControlTarget) -> dict:
    result = target.request({"action": "tree", "layer": "top"})
    if not result.get("ok"):
        raise TargetError(result.get("error", "tree failed"))
    return result["tree"]["root"]


def _buttons(node: dict) -> list[dict]:
    if "button" in node.get("type", "").lower():
        return [node]
    return [button for child in node.get("children", []) for button in _buttons(child)]


def _close_dialog(target: ControlTarget, top: dict, dismiss_labels: set[str]) -> bool:
    """Close stacked dialogs from the topmost down, each by its only button or
    its button with a dismiss label."""
    for _ in range(5):
        if not top.get("children"):
            return True
        buttons = _buttons(top["children"][-1])
        if len(buttons) != 1:
            buttons = [b for b in buttons if set(visible_labels(b)) & dismiss_labels]
        if len(buttons) != 1:
            return False
        target.request({"action": "click", "path": buttons[0]["path"], "layer": "top"})
        top = _top_layer(target)
    return not top.get("children")


def explore(target: ControlTarget, folder: Path, max_depth: int = 5) -> ControlResponse:
    """Click through every menu reachable from main and capture each screen.

    A click that opens a dialog captures it as "<menu>__<item>" and closes it.
    Exploring stops with an error when a dialog cannot be closed safely.
    """
    folder = Path(folder)
    visited, dialogs = [], []

    def call(request):
        result = target.request(request)
        if not result.get("ok"):
            raise TargetError(result.get("error", request["action"] + " failed"))
        return result

    def current_menu():
        return call({"action": "get_state"})["ui"]["current_menu_id"]

    def snapshot(name, layer="screen"):
        call({"action": "wait"})
        result = capture(target, folder / name, layer)
        if not result.get("ok"):
            raise TargetError(result.get("error", "capture failed"))
        return json.loads(Path(result["files"]["tree"]).read_text())

    def dismiss(name):
        top = _top_layer(target)
        if not top.get("children"):
            return
        snapshot(name, "top")
        dialogs.append(name)
        if not _close_dialog(target, top, dismiss_labels):
            raise TargetError("Cannot close the dialog captured in " + str(folder / name))

    def visit(depth):
        menu_id = current_menu()
        if depth > max_depth or menu_id in visited:
            return
        visited.append(menu_id)
        tree = snapshot(menu_id)
        for text in visible_labels(tree["root"]):
            if len(text) <= 2 or text.isdigit() or text in skip_labels or text.endswith(":"):
                continue
            if not target.request({"action": "click", "text": text}).get("ok"):
                continue
            dismiss(menu_id + "__" + text.replace("/", "_"))
            if current_menu() == menu_id:
                continue
            visit(depth + 1)
            call({"action": "navigate", "target": "back"})
            if current_menu() != menu_id:
                call({"action": "navigate", "target": menu_id})

    texts = call({"action": "translate", "keys": sorted(set(_SKIP_KEYS + _DISMISS_KEYS))})["texts"]
    skip_labels = set(_EXPLORE_SKIP) | {texts[key] for key in _SKIP_KEYS}
    dismiss_labels = {texts[key] for key in _DISMISS_KEYS}
    call({"action": "navigate", "target": "main"})
    dismiss("startup")
    visit(0)
    return {"ok": True, "folder": str(folder.resolve()), "screens": visited, "dialogs": dialogs}
