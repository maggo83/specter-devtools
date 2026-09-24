"""Board-first command line for simulator and hardware targets."""

import argparse
import json
import sys

from .artifacts import capture, explore, visible_labels
from .contract import TargetError
from .targets import SIMULATOR_HOST, SIMULATOR_PORT, TARGETS, make_target

LAYERS = ("screen", "top")
TAP_MS = 50
DRAG_STEP_MS = 25


def _parse_request(value: str) -> dict:
    request = json.loads(value)
    if not isinstance(request, dict):
        raise argparse.ArgumentTypeError("request JSON must be an object")
    return request


def _parse_value(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specter-devtools",
        description="Control Specter simulators and boards through one command structure.",
        epilog="esp32-p4 is reserved for the upcoming board port and is not implemented yet.",
    )
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--disco", help="F469 disco launcher (default: bundled f469/disco)")
    parser.add_argument("--host", default=SIMULATOR_HOST)
    parser.add_argument("--port", type=int, default=SIMULATOR_PORT)
    commands = parser.add_subparsers(dest="command", required=True)

    request = commands.add_parser("request", help="Send one canonical UI-control request")
    request.add_argument("request", type=_parse_request)
    click = commands.add_parser("click", help="Click the widget showing TEXT")
    click.add_argument("text")
    click.add_argument("--layer", choices=LAYERS, default="screen")
    tap = commands.add_parser("tap", help="Tap the screen at X Y")
    tap.add_argument("x", type=int)
    tap.add_argument("y", type=int)
    long_press = commands.add_parser("long-press", help="Press and hold at X Y")
    long_press.add_argument("x", type=int)
    long_press.add_argument("y", type=int)
    long_press.add_argument("--ms", type=int, default=1000)
    drag = commands.add_parser("drag", help="Press at X1 Y1, move to X2 Y2, release")
    for name in ("x1", "y1", "x2", "y2"):
        drag.add_argument(name, type=int)
    drag.add_argument("--ms", type=int, default=600)
    for name, help_text in (("tree", "Print the widget tree"), ("labels", "List visible texts")):
        layer_command = commands.add_parser(name, help=help_text)
        layer_command.add_argument("--layer", choices=LAYERS, default="screen")
    commands.add_parser("state", help="Show application state (simulator only)")
    goto = commands.add_parser("goto", help="Open a menu by id (simulator only)")
    goto.add_argument("menu_id")
    commands.add_parser("back", help="Go back one menu (simulator only)")
    set_state = commands.add_parser("set", help="Set a device state attribute (simulator only)")
    set_state.add_argument("attr")
    set_state.add_argument("value", type=_parse_value, help="JSON value such as true or 3; other text is a string")
    explore_parser = commands.add_parser(
        "explore", help="Click through all menus and capture each screen (simulator only)"
    )
    explore_parser.add_argument("folder")
    explore_parser.add_argument("--max-depth", type=int, default=5)
    explore_parser.add_argument("--settle", type=float, default=1.0, help="Seconds to wait before each capture")
    screenshot = commands.add_parser("screenshot", help="Save the visible framebuffer as PNG")
    screenshot.add_argument("output")
    capture_parser = commands.add_parser("capture", help="Save screenshot, tree, and labels")
    capture_parser.add_argument("folder")
    board = commands.add_parser("board", help="Run a raw board command, e.g. 'board flash analyze x.bin'")
    board.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def _drag_points(x1, y1, x2, y2, ms):
    steps = max(1, ms // DRAG_STEP_MS)
    return [[x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps, ms * i // steps]
            for i in range(steps + 1)]


def _shortcut_request(args: argparse.Namespace) -> dict:
    if args.command == "click":
        return {"action": "click", "text": args.text, "layer": args.layer}
    if args.command == "tap":
        return {"action": "touch", "points": [[args.x, args.y, 0], [args.x, args.y, TAP_MS]]}
    if args.command == "long-press":
        return {"action": "touch", "points": [[args.x, args.y, 0], [args.x, args.y, args.ms]]}
    if args.command == "drag":
        return {"action": "touch", "points": _drag_points(args.x1, args.y1, args.x2, args.y2, args.ms)}
    if args.command == "tree":
        return {"action": "tree", "layer": args.layer}
    if args.command == "state":
        return {"action": "get_state"}
    if args.command == "goto":
        return {"action": "navigate", "target": args.menu_id}
    if args.command == "back":
        return {"action": "navigate", "target": "back"}
    return {"action": "set_state", "attr": args.attr, "value": args.value}


def run(args: argparse.Namespace) -> int:
    target = make_target(args.target, host=args.host, port=args.port, disco=args.disco)
    if args.command == "board":
        if not hasattr(target, "board"):
            raise TargetError("Board commands are unavailable for the {} target".format(args.target))
        return target.board(args.arguments)

    if args.command == "request":
        result = target.request(args.request)
    elif args.command == "screenshot":
        result = target.screenshot(args.output)
    elif args.command == "capture":
        result = capture(target, args.folder)
    elif args.command == "explore":
        result = explore(target, args.folder, args.max_depth, args.settle)
    elif args.command == "labels":
        result = target.request({"action": "tree", "layer": args.layer})
        if result.get("ok"):
            result = {"ok": True, "labels": visible_labels(result["tree"]["root"])}
    else:
        result = target.request(_shortcut_request(args))
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (OSError, TargetError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
