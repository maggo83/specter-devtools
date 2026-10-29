"""Test support for invoking individual argparse-backed disco commands."""

import contextlib
import io
import sys
from dataclasses import dataclass
from unittest.mock import patch

from . import cli


@dataclass
class CliResult:
    exit_code: int
    output: str
    exception: BaseException | None = None


class CliRunner:
    def invoke(self, command, args=None, input=None):
        cli.build_parser()
        path = cli.COMMAND_PATHS[command]
        argv = [*path, *(args or [])]
        output = io.StringIO()
        exception = None
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
            patch.object(sys, "stdin", io.StringIO(input or "")),
        ):
            try:
                exit_code = cli.main(argv)
            except SystemExit as error:
                exit_code = error.code if isinstance(error.code, int) else 1
                exception = error
        return CliResult(exit_code, output.getvalue(), exception)
