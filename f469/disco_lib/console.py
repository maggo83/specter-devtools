"""Terminal output and user-input helpers for the disco CLI."""

import sys


_COLORS = {
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "cyan": 36,
}


class CliError(Exception):
    """Error that should be reported without a traceback."""


class BadParameter(CliError):
    """Invalid command argument discovered after parsing."""

def style(message, fg=None, bold=False):
    text = str(message)
    color = _COLORS.get(fg)
    if (color is None and not bold) or not sys.stdout.isatty():
        return text
    codes = [str(code) for code in (1 if bold else None, color) if code is not None]
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def echo(message="", err=False, nl=True):
    stream = sys.stderr if err else sys.stdout
    end = "\n" if nl else ""
    print("" if message is None else message, file=stream, end=end)


def secho(message="", fg=None, bold=False, err=False, nl=True):
    stream = sys.stderr if err else sys.stdout
    text = str(message)
    color = _COLORS.get(fg)
    if (color is not None or bold) and stream.isatty():
        codes = [str(code) for code in (1 if bold else None, color) if code is not None]
        text = f"\033[{';'.join(codes)}m{text}\033[0m"
    echo(text, err=err, nl=nl)


def confirm(prompt):
    answer = input(f"{prompt} [y/N]: ")
    return answer.strip().lower() in ("y", "yes")
