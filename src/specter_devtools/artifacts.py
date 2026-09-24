"""Target-independent artifact capture."""

import json
import time
from pathlib import Path

from .contract import ControlResponse, ControlTarget, TargetError

_EXPLORE_SKIP = ("eng", "OK", "Cancel", "Back")


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


def capture(target: ControlTarget, folder: Path) -> ControlResponse:
    """Save a screenshot, canonical tree, and labels from any target."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tree_result = target.request({"action": "tree"})
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


def explore(target: ControlTarget, folder: Path, max_depth: int = 5, settle: float = 1.0) -> ControlResponse:
    """Click through every menu reachable from main and capture each screen."""
    folder = Path(folder)
    visited = []

    def call(request):
        result = target.request(request)
        if not result.get("ok"):
            raise TargetError(result.get("error", request["action"] + " failed"))
        return result

    def current_menu():
        return call({"action": "get_state"})["ui"]["current_menu_id"]

    def visit(depth):
        menu_id = current_menu()
        if depth > max_depth or menu_id in visited:
            return
        visited.append(menu_id)
        time.sleep(settle)
        result = capture(target, folder / menu_id)
        if not result.get("ok"):
            raise TargetError(result.get("error", "capture failed"))
        tree = json.loads(Path(result["files"]["tree"]).read_text())
        for text in visible_labels(tree["root"]):
            if len(text) <= 2 or text.isdigit() or text in _EXPLORE_SKIP or text.endswith(":"):
                continue
            if not target.request({"action": "click", "text": text}).get("ok"):
                continue
            if current_menu() not in visited:
                visit(depth + 1)
            call({"action": "navigate", "target": "back"})
            if current_menu() != menu_id:
                call({"action": "navigate", "target": menu_id})

    call({"action": "navigate", "target": "main"})
    visit(0)
    return {"ok": True, "folder": str(folder.resolve()), "screens": visited}
