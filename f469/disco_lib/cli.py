"""Argparse command line for the STM32F469 board utility."""

import argparse
import os
import sys
from pathlib import Path

from . import console
from .commands import (
    cables as cables_commands,
    check as check_commands,
    cpu as cpu_commands,
    doctor as doctor_commands,
    flash as flash_commands,
    flash_fingerprint as fingerprint_commands,
    mem as mem_commands,
    ocd as ocd_commands,
    power as power_commands,
    quickstart as quickstart_commands,
    repl as repl_commands,
    serial as serial_commands,
    ui as ui_commands,
)


COMMAND_PATHS = {}
_FORMATTER = argparse.RawDescriptionHelpFormatter


def _summary(function):
    doc = function.__doc__ or ""
    return doc.strip().splitlines()[0] if doc.strip() else None


def _parser(subparsers, name, function, path):
    description = (function.__doc__ or "").replace("\b", "")
    parser = subparsers.add_parser(
        name,
        help=_summary(function),
        description=description,
        formatter_class=_FORMATTER,
    )
    COMMAND_PATHS[function] = path
    return parser


def _group(subparsers, name, function, path):
    parser = _parser(subparsers, name, function, path)
    commands = parser.add_subparsers(dest=f"{name}_command", required=True)
    return parser, commands


def _bind(parser, function, *arguments):
    parser.set_defaults(_handler=function, _handler_arguments=arguments)


def _existing_path(value):
    if not Path(value).exists():
        raise argparse.ArgumentTypeError(f"path does not exist: {value}")
    return value


def _add_ocd(commands):
    _, subcommands = _group(commands, "ocd", ocd_commands.ocd, ["ocd"])
    for name, function in (
        ("start", ocd_commands.ocd_start),
        ("stop", ocd_commands.ocd_stop),
        ("status", ocd_commands.ocd_status),
    ):
        parser = _parser(subcommands, name, function, ["ocd", name])
        _bind(parser, function)
    parser = _parser(subcommands, "cmd", ocd_commands.ocd_cmd, ["ocd", "cmd"])
    parser.add_argument("command", nargs="+", help="OpenOCD command and arguments")
    _bind(parser, ocd_commands.ocd_cmd, "command")


def _add_cpu(commands):
    _, subcommands = _group(commands, "cpu", cpu_commands.cpu, ["cpu"])
    for name, function in (
        ("halt", cpu_commands.cpu_halt),
        ("resume", cpu_commands.cpu_resume),
        ("reset", cpu_commands.cpu_reset),
        ("step", cpu_commands.cpu_step),
        ("regs", cpu_commands.cpu_regs),
        ("pc", cpu_commands.cpu_pc),
    ):
        parser = _parser(subcommands, name, function, ["cpu", name])
        _bind(parser, function)
    parser = _parser(subcommands, "stack", cpu_commands.cpu_stack, ["cpu", "stack"])
    parser.add_argument("count", nargs="?", default=16, type=int, help="Stack words to show")
    _bind(parser, cpu_commands.cpu_stack, "count")
    parser = _parser(subcommands, "gdb", cpu_commands.cpu_gdb, ["cpu", "gdb"])
    parser.add_argument("elf", nargs="?", type=_existing_path, help="ELF file with symbols")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually launch GDB (default: just print command)",
    )
    _bind(parser, cpu_commands.cpu_gdb, "elf", "run")


def _add_mem(commands):
    _, subcommands = _group(commands, "mem", mem_commands.mem, ["mem"])
    parser = _parser(subcommands, "read", mem_commands.mem_read, ["mem", "read"])
    parser.add_argument("addr", nargs="?", default="0x08000000", help="Start address")
    parser.add_argument("count", nargs="?", default=8, type=int, help="Words to read")
    _bind(parser, mem_commands.mem_read, "addr", "count")
    parser = _parser(subcommands, "vectors", mem_commands.mem_vectors, ["mem", "vectors"])
    parser.add_argument(
        "--fw",
        action="store_true",
        help="Show firmware vectors at 0x08020000 instead",
    )
    _bind(parser, mem_commands.mem_vectors, "fw")
    parser = _parser(subcommands, "dump", mem_commands.mem_dump, ["mem", "dump"])
    parser.add_argument("count", nargs="?", default=32, type=int, help="Words to dump")
    _bind(parser, mem_commands.mem_dump, "count")
    parser = _parser(subcommands, "save", mem_commands.mem_save, ["mem", "save"])
    parser.add_argument("file")
    parser.add_argument("addr")
    parser.add_argument("size")
    _bind(parser, mem_commands.mem_save, "file", "addr", "size")


def _add_fingerprint(commands):
    _, subcommands = _group(
        commands,
        "fingerprint",
        fingerprint_commands.fingerprint,
        ["flash", "fingerprint"],
    )
    for name, function in (
        ("create", fingerprint_commands.fingerprint_create),
        ("update", fingerprint_commands.fingerprint_update),
    ):
        parser = _parser(subcommands, name, function, ["flash", "fingerprint", name])
        parser.add_argument("file", type=_existing_path)
        parser.add_argument(
            "--output",
            "-o",
            help="Output YAML file (default: fingerprint.yaml in same directory)",
        )
        _bind(parser, function, "file", "output")
    parser = _parser(
        subcommands,
        "test",
        fingerprint_commands.fingerprint_test,
        ["flash", "fingerprint", "test"],
    )
    parser.add_argument("fingerprint_file", type=_existing_path)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Only compare file fingerprint (no flash, no hardware)",
    )
    _bind(parser, fingerprint_commands.fingerprint_test, "fingerprint_file", "static_only")


def _add_flash(commands):
    _, subcommands = _group(commands, "flash", flash_commands.flash, ["flash"])
    for name, function in (
        ("info", flash_commands.flash_info),
        ("erase", flash_commands.flash_erase),
        ("rdp", flash_commands.flash_rdp),
        ("unlock", flash_commands.flash_unlock),
        ("lock", flash_commands.flash_lock),
    ):
        parser = _parser(subcommands, name, function, ["flash", name])
        _bind(parser, function)
    parser = _parser(subcommands, "identify", flash_commands.flash_identify, ["flash", "identify"])
    parser.add_argument("file", nargs="?", type=_existing_path)
    _bind(parser, flash_commands.flash_identify, "file")
    parser = _parser(subcommands, "analyze", flash_commands.flash_analyze, ["flash", "analyze"])
    parser.add_argument("file", type=_existing_path)
    _bind(parser, flash_commands.flash_analyze, "file")
    parser = _parser(subcommands, "read", flash_commands.flash_read, ["flash", "read"])
    parser.add_argument("file")
    parser.add_argument(
        "--addr",
        default="0x08000000",
        help="Start address (default: 0x08000000)",
    )
    parser.add_argument(
        "--size",
        default="0x200000",
        help="Size in bytes (default: 0x200000 = 2MB)",
    )
    _bind(parser, flash_commands.flash_read, "file", "addr", "size")
    parser = _parser(subcommands, "verify", flash_commands.flash_verify, ["flash", "verify"])
    parser.add_argument("file", type=_existing_path)
    parser.add_argument(
        "--addr",
        help="Flash address (auto-detected like 'program' if not given)",
    )
    smart = parser.add_mutually_exclusive_group()
    smart.add_argument(
        "--smart",
        dest="smart",
        action="store_true",
        help="Skip internal zeros during verification (default)",
    )
    smart.add_argument(
        "--full",
        dest="smart",
        action="store_false",
        help="Verify every byte",
    )
    parser.set_defaults(smart=True)
    parser.add_argument(
        "--include-fs",
        action="store_true",
        help="Also fail if the internal filesystem changed (smart mode)",
    )
    _bind(parser, flash_commands.flash_verify, "file", "addr", "smart", "include_fs")
    parser = _parser(subcommands, "program", flash_commands.flash_program, ["flash", "program"])
    parser.add_argument("file", type=_existing_path)
    parser.add_argument("--addr", help="Flash address (auto-detected if not specified)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force --addr even if it conflicts with auto-detected",
    )
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify after programming",
    )
    parser.add_argument(
        "--reset",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reset after programming",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        default=0,
        type=int,
        help="Timeout in seconds (0=auto based on size)",
    )
    _bind(
        parser,
        flash_commands.flash_program,
        "file",
        "addr",
        "force",
        "verify",
        "reset",
        "timeout",
    )
    parser = _parser(subcommands, "install", flash_commands.flash_install, ["flash", "install"])
    parser.add_argument("firmware", type=_existing_path)
    parser.add_argument("qspi", type=_existing_path)
    parser.add_argument("--addr", help="Internal flash address (auto-detected if not specified)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force --addr even if it conflicts with auto-detected",
    )
    parser.add_argument(
        "--firmware-timeout",
        default=0,
        type=int,
        help="Internal flash timeout in seconds (0=auto based on size)",
    )
    parser.add_argument(
        "--qspi-timeout",
        default=0,
        type=int,
        help="QSPI timeout in seconds (0=auto based on size)",
    )
    _bind(
        parser,
        flash_commands.flash_install,
        "firmware",
        "qspi",
        "addr",
        "force",
        "firmware_timeout",
        "qspi_timeout",
    )
    _, qspi_commands = _group(
        subcommands,
        "qspi",
        flash_commands.flash_qspi,
        ["flash", "qspi"],
    )
    parser = _parser(
        qspi_commands,
        "info",
        flash_commands.flash_qspi_info,
        ["flash", "qspi", "info"],
    )
    _bind(parser, flash_commands.flash_qspi_info)
    parser = _parser(
        qspi_commands,
        "program",
        flash_commands.flash_qspi_program,
        ["flash", "qspi", "program"],
    )
    parser.add_argument("file", type=_existing_path)
    parser.add_argument(
        "--timeout",
        "-t",
        default=0,
        type=int,
        help="Timeout in seconds (0=auto based on size)",
    )
    _bind(parser, flash_commands.flash_qspi_program, "file", "timeout")
    _add_fingerprint(subcommands)


def _add_serial(commands):
    _, subcommands = _group(commands, "serial", serial_commands.serial, ["serial"])
    for name, function in (
        ("list", serial_commands.serial_list),
        ("test", serial_commands.serial_test),
        ("console", serial_commands.serial_console),
    ):
        parser = _parser(subcommands, name, function, ["serial", name])
        _bind(parser, function)
    for name, function, default in (
        ("repl", serial_commands.serial_repl, 3),
        ("boot", serial_commands.serial_boot, 5),
    ):
        parser = _parser(subcommands, name, function, ["serial", name])
        parser.add_argument("timeout", nargs="?", default=default, type=int)
        _bind(parser, function, "timeout")


def _add_repl(commands):
    _, subcommands = _group(commands, "repl", repl_commands.repl, ["repl"])
    parser = _parser(subcommands, "exec", repl_commands.repl_exec, ["repl", "exec"])
    parser.add_argument("code")
    parser.add_argument(
        "--timeout",
        "-t",
        default=3,
        type=int,
        help="Response timeout in seconds",
    )
    _bind(parser, repl_commands.repl_exec, "code", "timeout")
    for name, function in (
        ("info", repl_commands.repl_info),
        ("help", repl_commands.repl_help),
    ):
        parser = _parser(subcommands, name, function, ["repl", name])
        _bind(parser, function)
    parser = _parser(subcommands, "modules", repl_commands.repl_modules, ["repl", "modules"])
    parser.add_argument("--timeout", "-t", default=5, type=int, help="Response timeout")
    _bind(parser, repl_commands.repl_modules, "timeout")
    for name, function in (
        ("reset", repl_commands.repl_reset),
        ("wait", repl_commands.repl_wait),
    ):
        parser = _parser(subcommands, name, function, ["repl", name])
        parser.add_argument(
            "--timeout",
            "-t",
            default=60,
            type=int,
            help="Seconds to wait for the REPL",
        )
        parser.add_argument(
            "--interrupt-running",
            action="store_true",
            help="Stop main.py when the board returns",
        )
        _bind(parser, function, "timeout", "interrupt_running")
    parser = _parser(subcommands, "hello", repl_commands.repl_hello, ["repl", "hello"])
    parser.add_argument("message", nargs="?", default="Hello World!")
    _bind(parser, repl_commands.repl_hello, "message")
    parser = _parser(subcommands, "ls", repl_commands.repl_ls, ["repl", "ls"])
    parser.add_argument("path", nargs="?", default="/flash")
    _bind(parser, repl_commands.repl_ls, "path")
    parser = _parser(subcommands, "cat", repl_commands.repl_cat, ["repl", "cat"])
    parser.add_argument("path")
    _bind(parser, repl_commands.repl_cat, "path")
    parser = _parser(subcommands, "cp", repl_commands.repl_cp, ["repl", "cp"])
    parser.add_argument("src")
    parser.add_argument("dest")
    _bind(parser, repl_commands.repl_cp, "src", "dest")
    parser = _parser(subcommands, "import", repl_commands.repl_import, ["repl", "import"])
    parser.add_argument("module", nargs="?", default="hardwaretest")
    parser.add_argument(
        "--timeout",
        "-t",
        default=10,
        type=int,
        help="Response timeout in seconds",
    )
    _bind(parser, repl_commands.repl_import, "module", "timeout")
    parser = _parser(subcommands, "rm", repl_commands.repl_rm, ["repl", "rm"])
    parser.add_argument("path")
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Do not ask for confirmation",
    )
    _bind(parser, repl_commands.repl_rm, "path", "force")


def _add_power(commands):
    parser, subcommands = _group(commands, "power", power_commands.power, ["power"])
    parser.add_argument(
        "--serial",
        "-s",
        default=os.environ.get("YKUSH_SERIAL"),
        help="YKUSH device serial number (or set YKUSH_SERIAL)",
    )
    subparser = _parser(subcommands, "status", power_commands.power_status, ["power", "status"])
    _bind(subparser, power_commands.power_status, "serial")
    for name, function in (
        ("on", power_commands.power_on),
        ("off", power_commands.power_off),
    ):
        subparser = _parser(subcommands, name, function, ["power", name])
        subparser.add_argument("port", nargs="?")
        _bind(subparser, function, "serial", "port")
    subparser = _parser(subcommands, "cycle", power_commands.power_cycle, ["power", "cycle"])
    subparser.add_argument("port", nargs="?")
    subparser.add_argument(
        "--delay",
        "-d",
        default=2.0,
        type=float,
        help="Delay in seconds between off/on (default: 2.0)",
    )
    _bind(subparser, power_commands.power_cycle, "serial", "port", "delay")


def _add_ui(commands):
    _, subcommands = _group(commands, "ui", ui_commands.ui, ["ui"])
    parser = _parser(subcommands, "control", ui_commands.ui_control, ["ui", "control"])
    parser.add_argument("request_json")
    parser.add_argument(
        "--timeout",
        "-t",
        default=10,
        type=int,
        help="Response timeout in seconds",
    )
    _bind(parser, ui_commands.ui_control, "request_json", "timeout")
    parser = _parser(subcommands, "screen", ui_commands.ui_screen, ["ui", "screen"])
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON tree")
    parser.add_argument(
        "--layer",
        choices=("screen", "top"),
        default="screen",
        help="Root layer (default: screen)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        default=10,
        type=int,
        help="Response timeout in seconds",
    )
    _bind(parser, ui_commands.ui_screen, "as_json", "layer", "timeout")
    parser = _parser(subcommands, "click", ui_commands.ui_click, ["ui", "click"])
    parser.add_argument("text", nargs="?")
    parser.add_argument(
        "--index",
        "-i",
        help="Dot-separated tree path (for example 1.0.1.5.2)",
    )
    parser.add_argument(
        "--layer",
        choices=("screen", "top"),
        default="screen",
        help="Root layer (default: screen)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        default=10,
        type=int,
        help="Response timeout in seconds",
    )
    _bind(parser, ui_commands.ui_click, "text", "index", "layer", "timeout")
    parser = _parser(subcommands, "write", ui_commands.ui_write, ["ui", "write"])
    parser.add_argument("text")
    parser.add_argument(
        "--target",
        "-n",
        default=0,
        type=int,
        help="Index of textarea to target (default: 0)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        default=10,
        type=int,
        help="Response timeout in seconds",
    )
    _bind(parser, ui_commands.ui_write, "text", "target", "timeout")
    parser = _parser(subcommands, "screenshot", ui_commands.ui_screenshot, ["ui", "screenshot"])
    parser.add_argument("output", nargs="?", default="/tmp/screenshot.png")
    parser.add_argument(
        "--timeout",
        "-t",
        default=30,
        type=int,
        help="OpenOCD dump timeout in seconds",
    )
    _bind(parser, ui_commands.ui_screenshot, "output", "timeout")


def build_parser():
    COMMAND_PATHS.clear()
    parser = argparse.ArgumentParser(
        prog="disco",
        description="STM32F469 Discovery board debugging utility.",
        formatter_class=_FORMATTER,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    _add_ocd(commands)
    _add_cpu(commands)
    _add_mem(commands)
    _add_flash(commands)
    _add_serial(commands)
    _add_repl(commands)
    _add_power(commands)
    _add_ui(commands)
    for name, function, arguments in (
        ("doctor", doctor_commands.doctor, ("verbose", "no_log")),
        ("quickstart", quickstart_commands.quickstart, ("raw",)),
        ("cables", cables_commands.cables, ()),
        ("check", check_commands.check, ("no_resume",)),
    ):
        command = _parser(commands, name, function, [name])
        if name == "doctor":
            command.add_argument(
                "--verbose",
                "-v",
                action="store_true",
                help="Show all check details",
            )
            command.add_argument("--no-log", action="store_true", help="Skip writing log file")
        elif name == "quickstart":
            command.add_argument("--raw", action="store_true", help="Output without formatting")
        elif name == "check":
            command.add_argument(
                "--no-resume",
                action="store_true",
                help="Keep CPU halted after check (disconnects USB)",
            )
        _bind(command, function, *arguments)
    return parser


def run(args):
    values = [getattr(args, name) for name in args._handler_arguments]
    result = args._handler(*values)
    return result if isinstance(result, int) else 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except console.CliError as error:
        console.secho(f"Error: {error}", fg="red", err=True)
        return 1


def cli(argv=None):
    sys.exit(main(argv))
