"""Board-first command line for simulator and hardware targets."""

import argparse
import json
import sys

from .artifacts import capture
from .contract import TargetError
from .targets import SIMULATOR_HOST, SIMULATOR_PORT, TARGETS, make_target


def _parse_request(value: str) -> dict:
    request = json.loads(value)
    if not isinstance(request, dict):
        raise argparse.ArgumentTypeError("request JSON must be an object")
    return request


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
    screenshot = commands.add_parser("screenshot", help="Save the visible framebuffer as PNG")
    screenshot.add_argument("output")
    capture_parser = commands.add_parser("capture", help="Save screenshot, tree, and labels")
    capture_parser.add_argument("folder")
    board = commands.add_parser("board", help="Run a raw board command, e.g. 'board flash analyze x.bin'")
    board.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


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
    else:
        result = capture(target, args.folder)
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
