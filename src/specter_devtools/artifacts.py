"""Target-independent artifact capture."""

import json
from pathlib import Path

from .contract import ControlResponse, ControlTarget


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
