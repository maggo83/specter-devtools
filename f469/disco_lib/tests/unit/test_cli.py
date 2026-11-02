"""Contract tests for the argparse-backed ``disco`` command line."""

import argparse
import ast
import re
from pathlib import Path

import pytest

from disco_lib import cli, console


EXPECTED_COMMAND_TREE = {
    "ocd": {"start": None, "stop": None, "status": None, "cmd": None},
    "cpu": {
        "halt": None,
        "resume": None,
        "reset": None,
        "step": None,
        "regs": None,
        "pc": None,
        "stack": None,
        "gdb": None,
    },
    "mem": {"read": None, "vectors": None, "dump": None, "save": None},
    "flash": {
        "info": None,
        "erase": None,
        "rdp": None,
        "unlock": None,
        "lock": None,
        "identify": None,
        "analyze": None,
        "read": None,
        "verify": None,
        "program": None,
        "install": None,
        "qspi": {"info": None, "program": None},
        "fingerprint": {"create": None, "update": None, "test": None},
    },
    "serial": {
        "list": None,
        "test": None,
        "console": None,
        "repl": None,
        "boot": None,
    },
    "repl": {
        "exec": None,
        "info": None,
        "help": None,
        "modules": None,
        "reset": None,
        "wait": None,
        "hello": None,
        "ls": None,
        "cat": None,
        "cp": None,
        "import": None,
        "rm": None,
    },
    "power": {"status": None, "on": None, "off": None, "cycle": None},
    "ui": {
        "control": None,
        "screen": None,
        "click": None,
        "write": None,
        "screenshot": None,
    },
    "doctor": None,
    "quickstart": None,
    "cables": None,
    "check": None,
}


def _command_tree(parser):
    subparsers = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if not subparsers:
        return None
    assert len(subparsers) == 1
    return {
        name: _command_tree(command_parser)
        for name, command_parser in subparsers[0].choices.items()
    }


def _assert_parses(parser, argv, **expected):
    values = vars(parser.parse_args(argv))
    assert {name: values[name] for name in expected} == expected


def test_complete_command_tree_is_registered():
    assert _command_tree(cli.build_parser()) == EXPECTED_COMMAND_TREE


def test_important_command_defaults_are_preserved(tmp_path, monkeypatch):
    monkeypatch.delenv("YKUSH_SERIAL", raising=False)
    firmware = tmp_path / "firmware.bin"
    firmware.write_bytes(b"\x01")
    parser = cli.build_parser()

    cases = [
        (["cpu", "stack"], {"count": 16}),
        (["mem", "read"], {"addr": "0x08000000", "count": 8}),
        (
            ["flash", "read", "dump.bin"],
            {"addr": "0x08000000", "size": "0x200000"},
        ),
        (
            ["flash", "verify", str(firmware)],
            {"addr": None, "smart": True, "include_fs": False},
        ),
        (
            ["flash", "program", str(firmware)],
            {
                "addr": None,
                "force": False,
                "verify": True,
                "reset": True,
                "timeout": 0,
            },
        ),
        (
            ["flash", "qspi", "program", str(firmware)],
            {"timeout": 0},
        ),
        (
            ["flash", "install", str(firmware), str(firmware)],
            {
                "addr": None,
                "force": False,
                "firmware_timeout": 0,
                "qspi_timeout": 0,
            },
        ),
        (["serial", "repl"], {"timeout": 3}),
        (["serial", "boot"], {"timeout": 5}),
        (["repl", "exec", "pass"], {"timeout": 3}),
        (["repl", "modules"], {"timeout": 5}),
        (
            ["repl", "reset"],
            {"timeout": 60, "interrupt_running": False},
        ),
        (
            ["repl", "import"],
            {"module": "hardwaretest", "timeout": 10},
        ),
        (
            ["power", "cycle"],
            {"serial": None, "port": None, "delay": 2.0},
        ),
        (
            ["ui", "screen"],
            {"as_json": False, "layer": "screen", "timeout": 10},
        ),
        (
            ["ui", "screenshot"],
            {"output": "/tmp/screenshot.png", "timeout": 30},
        ),
    ]

    for argv, expected in cases:
        _assert_parses(parser, argv, **expected)


def test_inverse_flash_flags_override_the_enabled_defaults(tmp_path):
    firmware = tmp_path / "firmware.bin"
    firmware.write_bytes(b"\x01")
    parser = cli.build_parser()

    _assert_parses(
        parser,
        ["flash", "verify", str(firmware), "--full", "--include-fs"],
        smart=False,
        include_fs=True,
    )
    _assert_parses(
        parser,
        ["flash", "verify", str(firmware), "--smart"],
        smart=True,
    )
    _assert_parses(
        parser,
        ["flash", "program", str(firmware), "--no-verify", "--no-reset"],
        verify=False,
        reset=False,
    )


def test_power_serial_uses_environment_and_explicit_option_precedence(monkeypatch):
    monkeypatch.delenv("YKUSH_SERIAL", raising=False)
    assert cli.build_parser().parse_args(["power", "status"]).serial is None

    monkeypatch.setenv("YKUSH_SERIAL", "YK-ENV")
    parser = cli.build_parser()
    assert parser.parse_args(["power", "status"]).serial == "YK-ENV"
    assert (
        parser.parse_args(["power", "--serial", "YK-CLI", "status"]).serial
        == "YK-CLI"
    )


def test_argparse_errors_use_standard_format_and_exit_status(tmp_path, capsys):
    missing = tmp_path / "missing.bin"

    with pytest.raises(SystemExit) as error:
        cli.main(["flash", "program", str(missing)])

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("usage: disco flash program ")
    assert (
        f"disco flash program: error: argument file: path does not exist: {missing}"
        in captured.err
    )


def test_cli_errors_are_concise_on_stderr_and_exit_one(capsys):
    with pytest.raises(SystemExit) as error:
        cli.cli(["ui", "click"])

    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: Provide TEXT or --index\n"


def test_console_preserves_bold_colored_warnings(monkeypatch, capsys):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)

    console.secho("danger", fg="red", bold=True, err=True)

    assert capsys.readouterr().err == "\033[1;31mdanger\033[0m\n"


def test_f469_tool_has_no_click_import_or_dependency():
    f469_dir = Path(__file__).parents[3]
    click_imports = []
    for source_path in f469_dir.rglob("*.py"):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "click" or name.startswith("click.") for name in names):
                click_imports.append(f"{source_path.relative_to(f469_dir)}:{node.lineno}")

    dependency_files = [
        f469_dir / "requirements.in",
        f469_dir / "requirements.txt",
    ]
    click_dependencies = []
    for dependency_file in dependency_files:
        for line_number, line in enumerate(
            dependency_file.read_text().splitlines(), start=1
        ):
            match = re.match(r"^([A-Za-z0-9_.-]+)", line)
            if match and match.group(1).lower().replace("_", "-") == "click":
                click_dependencies.append(f"{dependency_file.name}:{line_number}")

    assert click_imports == []
    assert click_dependencies == []
