"""REPL communication backend."""

import time
from contextlib import contextmanager

import serial as pyserial

from . import BAUD_RATE


@contextmanager
def mpremote_transport(dev: str, baud: int = BAUD_RATE, soft_reset: bool = True):
    """Context manager for mpremote SerialTransport."""
    from mpremote.transport_serial import SerialTransport
    transport = SerialTransport(dev, baud)
    transport.enter_raw_repl(soft_reset=soft_reset)
    try:
        yield transport
    finally:
        transport.exit_raw_repl()
        transport.close()


def filter_repl_output(text: str, code: str) -> str:
    """Filter REPL output to extract just the result.

    Removes:
      - Command echo (the code we sent)
      - REPL prompts (>>>, ...)
      - Empty lines
      - Carriage returns
    """
    lines = text.split("\n")
    output_lines = []
    for line in lines:
        line = line.rstrip("\r")
        # Skip command echo
        if line.strip() == code.strip():
            continue
        # Skip empty prompts
        if line.strip() in (">>>", "...", ""):
            continue
        # Remove leading >>> if present
        if line.startswith(">>> "):
            line = line[4:]
        elif line.startswith("... "):
            line = line[4:]
        output_lines.append(line)

    return "\n".join(output_lines).strip()


def exec_raw(dev: str, code: str, baud: int = BAUD_RATE, timeout: float = 5.0) -> str:
    """Execute multi-line Python via mpremote raw REPL.

    Unlike exec_code() which uses the friendly REPL (single-line only),
    this uses mpremote's raw REPL protocol to send multi-line scripts.
    """
    with mpremote_transport(dev, baud, soft_reset=False) as transport:
        transport.exec_raw_no_follow(code)
        stdout, stderr = transport.follow(timeout=timeout)
        stdout = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
        if stderr:
            raise RuntimeError(f"MicroPython error:\n{stderr}")
        return stdout.strip()


def exec_code(dev: str, code: str, baud: int = BAUD_RATE, timeout: float = 3.0) -> str:
    """Execute Python code on REPL and return output."""
    with pyserial.Serial(dev, baud, timeout=timeout) as ser:
        # Interrupt any running code and wait for the prompt
        ser.write(b"\x03")
        ser.read_until(b">>> ")

        # Send code; skip stale prompts up to its echo, then read until the next prompt
        ser.write(code.encode() + b"\r\n")
        ser.read_until(code.splitlines()[0].encode() + b"\r\n")
        data = ser.read_until(b"\r\n>>> ")
        text = data.decode("utf-8", errors="replace")

        return filter_repl_output(text, code)


def soft_reset(dev: str, baud: int = BAUD_RATE, timeout: float = 3.0) -> str:
    """Send soft reset (Ctrl-D) and return output."""
    with pyserial.Serial(dev, baud, timeout=timeout) as ser:
        ser.write(b"\x03")  # Ctrl-C first
        time.sleep(0.1)
        ser.write(b"\x04")  # Ctrl-D
        time.sleep(1)
        data = ser.read(4096)
        return data.decode("utf-8", errors="replace")


def wait_for_prompt(find_device, baud: int = BAUD_RATE, timeout: float = 60.0, poll: float = 1.0) -> str:
    """Wait until the serial port exists and the REPL answers with a prompt.

    Returns the device path; raises TimeoutError.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dev = find_device()
        if dev:
            try:
                with pyserial.Serial(dev, baud, timeout=poll) as ser:
                    ser.reset_input_buffer()
                    # Ctrl-B, not Ctrl-C: leaves a raw REPL and never interrupts a booting main.py.
                    ser.write(b"\x02")
                    if ser.read_until(b">>> ").endswith(b">>> "):
                        return dev
            except (pyserial.SerialException, OSError):
                pass  # the port disappears while the board re-enumerates
        time.sleep(poll)
    raise TimeoutError(f"No REPL prompt within {timeout:g} s")
