"""Serial/REPL communication commands."""

import re
import time

from .. import console

from ..ocd_provider import get_ocd
from ..serial import SerialDevice
from .. import cpu as cpu_backend

_ser = SerialDevice()


def _check_usb_otg_connected() -> bool:
    """Check if USB OTG serial (REPL) is available."""
    for path, blacklisted in _ser.list_devices():
        if blacklisted:
            continue
        # MacOS
        match = re.search(r'usbmodem(\w+)', path)
        if match and len(match.group(1)) > 6:
            return True
        # Linux
        match = re.search(r'serial/by-id/(.+)', path)
        if match:
            dev_name = match.group(1).lower()
            if "MicroPython".lower() in dev_name:
                return True
    return False


def serial():
    """Serial/REPL communication.

    Communicate with the MicroPython REPL via USB CDC serial. The REPL
    is available on the USB OTG port (microUSB connector, CN13 bottom), not the ST-LINK
    port (miniUSB, CN1 top).

    \b
    USB Connections (STM32F469-Discovery):
      MiniUSB  (CN1)  - ST-LINK: JTAG/SWD + Virtual COM Port (VCP)  [top of board]
      MicroUSB (CN13) - USB OTG: MicroPython REPL (CDC serial)         [bottom of board]

    \b
    Device Detection:
      - Only /dev/tty.* devices are used (not /dev/cu.*)
      - ST-LINK VCP has short ID (e.g., "21403")
      - USB OTG CDC has long ID (e.g., "335D375F33382")
      - USB OTG is preferred for REPL access

    \b
    REPL Wake Sequence:
      The 'repl' command sends Ctrl-C + multiple newlines to wake the
      REPL from any state. Connection is kept open during wake to avoid
      missing the response.

    \b
    Troubleshooting:
      - Run 'disco cables' to check USB connections
      - Ensure microUSB cable is connected for REPL (CN13, bottom of board)
      - USB CDC only appears after firmware enables USB communication
      - If no response, try 'disco serial console' for interactive debug

    \b
    Examples:
      disco serial list           # See available devices
      disco serial repl           # Quick REPL test (3s)
      disco serial repl 10        # Longer timeout
      disco serial console        # Interactive session (Ctrl-A K to exit)
    """
    pass


def serial_list():
    """List available serial devices."""
    _ser.show_devices()


def serial_test():
    """Quick test for serial output (2 sec)."""
    console.secho("=== Serial Port Test ===", fg="blue")
    dev = _ser.require_device()
    console.echo(f"Testing: {dev} @ {_ser.baud}")
    console.echo("Waiting 2 seconds for output...")
    output = _ser.read_timeout(dev, 2.0)
    if output:
        console.echo(output)
    else:
        console.echo("(no output received)")


def serial_repl(timeout: int):
    """Test REPL connection (default 3s timeout)."""
    console.secho(f"=== REPL Test ({timeout}s timeout) ===", fg="blue")

    if not _check_usb_otg_connected():
        console.secho("Warning: USB OTG (microUSB) not detected!", fg="red")
        console.secho("REPL requires microUSB cable connected to USB OTG port (CN13, bottom of board)", fg="yellow")
        console.echo()

    dev = _ser.require_device()
    console.echo(f"Device: {dev}")
    console.echo("Sending wake-up sequence...")

    output = _ser.repl_test(dev, timeout)
    if output:
        console.secho("Response received:", fg="green")
        console.echo(output)
        if ">>>" in output:
            console.secho("REPL prompt detected!", fg="green")
    else:
        console.secho("(no response)", fg="yellow")


def serial_boot(timeout: int):
    """Reset board and capture boot output (default 5s)."""
    console.secho(f"=== Boot Capture ({timeout}s timeout) ===", fg="blue")
    dev = _ser.require_device()

    console.echo(f"Device: {dev}")
    console.echo("Resetting board and capturing output...")

    with get_ocd().ensure_running():
        cpu_backend.reset_run(get_ocd())

    time.sleep(0.3)
    output = _ser.read_timeout(dev, timeout)

    if output:
        console.echo(output)
    console.secho("\nCapture complete", fg="green")


def serial_console():
    """Open interactive serial console (screen)."""
    dev = _ser.require_device()
    _ser.exec_console(dev)
