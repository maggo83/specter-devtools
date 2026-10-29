"""Power control commands using YKUSH USB hub."""

import os

from .. import console

from ..ykush import (
    Ykush,
    YkushError,
    YkushInvalidPortError,
    YkushNoDevicesError,
    YkushNotFoundError,
)
from ..ykush_provider import get_ykush


def _get_ykush_instance(serial: str | None) -> Ykush:
    """Get YKUSH instance with optional serial selection."""
    return get_ykush(serial=serial)


def _parse_port(port_str: str | None) -> int | str:
    """Parse port argument to int or 'all'.

    Args:
        port_str: Port string from CLI (None, '1', '2', '3', 'all', 'a').

    Returns:
        Port number (1, 2, 3) or 'all'.

    Raises:
        BadParameter: If port is invalid.
    """
    if port_str is None or port_str.lower() in ("all", "a"):
        return "all"
    try:
        port = int(port_str)
        if port not in (1, 2, 3):
            raise console.BadParameter("Port must be 1, 2, 3, or 'all'")
        return port
    except ValueError:
        raise console.BadParameter("Port must be 1, 2, 3, or 'all'")


def _print_ykush_unavailable():
    """Print helpful message when YKUSH is not available."""
    console.secho("YKUSH not available.", fg="red")
    console.echo()
    console.echo("To power cycle the board manually:")
    console.echo("  1. Unplug the USB cables from the board")
    console.echo("  2. Wait 2-3 seconds")
    console.echo("  3. Reconnect the cables")
    console.echo()
    console.echo("For automated power control, install a YKUSH USB hub:")
    console.echo("  https://www.yepkit.com/")


def _print_no_devices():
    """Print message when no YKUSH devices found."""
    console.secho("No YKUSH devices found.", fg="yellow")
    console.echo()
    console.echo("Check that:")
    console.echo("  - YKUSH hub is connected via USB")
    console.echo("  - USB cable is working")
    console.echo("  - ykushcmd can see the device: ykushcmd -l")


def power():
    """USB power control via YKUSH hub.

    Control power to USB devices connected through a YKUSH USB hub.
    Useful for power cycling the STM32F469 Discovery board to recover
    from hangs or reset USB enumeration.

    \b
    Examples:
      disco power status              # Show all devices and port states
      disco power cycle               # Power cycle all ports (default)
      disco power off 1               # Power down port 1 only
      disco power on                  # Power up all ports
      disco power --serial YK123 off  # Target specific device
    """
    pass


def power_status(serial):
    """Show YKUSH devices and port states."""
    try:
        ykush = _get_ykush_instance(serial)

        # First list all devices
        devices = ykush.list_devices()
        if not devices:
            _print_no_devices()
            return

        console.secho("=== YKUSH Status ===", fg="blue")
        console.echo(f"Devices found: {len(devices)}")
        console.echo()

        for dev_serial in devices:
            console.echo(f"Device: {dev_serial}")
            # Get status for each port
            for port in (1, 2, 3):
                try:
                    # Create instance for this specific device to get port status
                    dev_ykush = get_ykush(serial=dev_serial)
                    is_on = dev_ykush.get_port_status(port)
                    status_icon = console.style("ON", fg="green") if is_on else console.style("OFF", fg="red")
                    console.echo(f"  Port {port}: {status_icon}")
                except YkushError:
                    console.echo(f"  Port {port}: " + console.style("?", fg="yellow"))
            console.echo()

    except YkushNotFoundError:
        _print_ykush_unavailable()
    except YkushNoDevicesError:
        _print_no_devices()
    except YkushError as e:
        raise console.CliError(str(e))


def power_on(serial, port):
    """Power up port(s).

    PORT can be 1, 2, 3, or 'all' (default: all).
    """
    port_val = _parse_port(port)

    try:
        ykush = _get_ykush_instance(serial)
        ykush.select_device()  # Validate device exists

        port_desc = "all ports" if port_val == "all" else f"port {port_val}"
        console.echo(f"Powering on {port_desc}...")
        result = ykush.power_up(port_val)
        if result:
            console.echo(result)
        console.secho(f"Power ON: {port_desc}", fg="green")

    except YkushNotFoundError:
        _print_ykush_unavailable()
    except YkushNoDevicesError:
        _print_no_devices()
    except YkushInvalidPortError as e:
        raise console.BadParameter(str(e))
    except YkushError as e:
        raise console.CliError(str(e))


def power_off(serial, port):
    """Power down port(s).

    PORT can be 1, 2, 3, or 'all' (default: all).
    """
    port_val = _parse_port(port)

    try:
        ykush = _get_ykush_instance(serial)
        ykush.select_device()  # Validate device exists

        port_desc = "all ports" if port_val == "all" else f"port {port_val}"
        console.echo(f"Powering off {port_desc}...")
        result = ykush.power_down(port_val)
        if result:
            console.echo(result)
        console.secho(f"Power OFF: {port_desc}", fg="yellow")

    except YkushNotFoundError:
        _print_ykush_unavailable()
    except YkushNoDevicesError:
        _print_no_devices()
    except YkushInvalidPortError as e:
        raise console.BadParameter(str(e))
    except YkushError as e:
        raise console.CliError(str(e))


def power_cycle(serial, port, delay):
    """Power cycle port(s) with delay.

    PORT can be 1, 2, 3, or 'all' (default: all).

    \b
    Example workflow:
      disco power cycle && sleep 3 && disco ocd start
    """
    port_val = _parse_port(port)

    try:
        ykush = _get_ykush_instance(serial)
        ykush.select_device()  # Validate device exists

        port_desc = "all ports" if port_val == "all" else f"port {port_val}"
        console.echo(f"Power cycling {port_desc} (delay: {delay}s)...")
        console.echo("  Power OFF...")
        ykush.power_down(port_val)
        console.echo(f"  Waiting {delay}s...")
        # Note: actual sleep happens in power_cycle, but we call power_down/up
        # separately to show progress
        import time

        time.sleep(delay)
        console.echo("  Power ON...")
        ykush.power_up(port_val)
        console.secho(f"Power cycle complete: {port_desc}", fg="green")

    except YkushNotFoundError:
        _print_ykush_unavailable()
    except YkushNoDevicesError:
        _print_no_devices()
    except YkushInvalidPortError as e:
        raise console.BadParameter(str(e))
    except YkushError as e:
        raise console.CliError(str(e))
