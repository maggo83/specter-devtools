"""REPL interaction commands."""

import os
import time

from .. import console
import serial as pyserial

from ..serial import SerialDevice
from .. import repl as repl_backend

_ser = SerialDevice()


def repl():
    """MicroPython REPL interaction.

    Execute Python code and manage files on the board.

    \b
    Code execution:
      disco repl exec "print('hello')"
      disco repl exec "help()" --timeout 5
      disco repl info
      disco repl modules
      disco repl reset                      # hard reset, waits for the REPL
      disco repl wait                       # after flashing
      disco repl hello "Hi!"

    \b
    File operations (uses mpremote):
      disco repl ls                         # list /flash
      disco repl cat /flash/main.py         # print file
      disco repl cp local.py :/flash/       # copy to board
      disco repl cp :/flash/file.py ./      # copy from board
      disco repl rm /flash/test.py          # remove file
    """
    pass


def repl_exec(code: str, timeout: int):
    """Execute Python code on REPL.

    \b
    Examples:
      disco repl exec "1 + 1"
      disco repl exec "import gc; gc.collect(); gc.mem_free()"
      disco repl exec "help()"
    """
    dev = _ser.require_device()
    try:
        output = repl_backend.exec_code(dev, code, _ser.baud, timeout)
        if output:
            console.echo(output)
    except pyserial.SerialException as e:
        raise console.CliError(f"Serial error: {e}")


def repl_info():
    """Show board info (sys.implementation, machine.freq, etc)."""
    dev = _ser.require_device()
    try:
        console.secho("=== Board Info ===", fg="blue")

        output = repl_backend.exec_code(dev, "import sys; print(sys.implementation)", _ser.baud, 2)
        console.echo(f"Implementation: {output}")

        output = repl_backend.exec_code(dev, "import machine; print(machine.freq())", _ser.baud, 2)
        console.echo(f"CPU Frequency: {output} Hz")

        output = repl_backend.exec_code(dev, "import gc; gc.collect(); print(gc.mem_free())", _ser.baud, 2)
        console.echo(f"Free Memory: {output} bytes")

        output = repl_backend.exec_code(dev, "import sys; print(sys.platform)", _ser.baud, 2)
        console.echo(f"Platform: {output}")

    except pyserial.SerialException as e:
        raise console.CliError(f"Serial error: {e}")


def repl_modules(timeout: int):
    """List available MicroPython modules."""
    dev = _ser.require_device()
    try:
        console.secho("=== Available Modules ===", fg="blue")
        output = repl_backend.exec_code(dev, "help('modules')", _ser.baud, timeout)
        console.echo(output)
    except pyserial.SerialException as e:
        raise console.CliError(f"Serial error: {e}")


def repl_help():
    """Show MicroPython help."""
    dev = _ser.require_device()
    try:
        output = repl_backend.exec_code(dev, "help()", _ser.baud, 3)
        console.echo(output)
    except pyserial.SerialException as e:
        raise console.CliError(f"Serial error: {e}")


def repl_reset(timeout: int, interrupt_running: bool):
    """Reset the board and wait until its REPL answers again.

    \b
    A hard reset (machine.reset(), like the reset button). There is no soft
    reset: it makes MockUI's display.init() fail.
    """
    dev = _ser.require_device()
    try:
        repl_backend.hard_reset(dev, _ser.baud)
    except TimeoutError as error:
        raise console.CliError(str(error)) from error
    # Wait for this board only; its by-id path (USB serial number) survives the reconnect.
    _wait(
        timeout,
        lambda: dev if os.path.exists(dev) else None,
        interrupt_running=interrupt_running,
    )


def repl_wait(timeout: int, interrupt_running: bool):
    """Wait until the board answers on its REPL.

    \b
    Use after flashing: waits for the USB serial port to come back and for
    the >>> prompt, without interrupting a booting main.py.
      disco flash program firmware.bin && disco repl wait
    """
    _wait(timeout, interrupt_running=interrupt_running)


def _wait(timeout: int, find_device=None, interrupt_running: bool = False):
    try:
        dev = repl_backend.wait_for_prompt(
            find_device or _ser.auto_detect,
            _ser.baud,
            timeout,
            interrupt_running=interrupt_running,
        )
    except TimeoutError as e:
        raise console.CliError(str(e))
    console.secho(f"REPL ready on {dev}", fg="green")


def repl_hello(message: str):
    """Display a message on the screen (large font, centered).

    \b
    Examples:
      disco repl hello
      disco repl hello "Specter DIY"
    """
    dev = _ser.require_device()
    try:
        console.echo("Initializing display...")
        repl_backend.exec_code(
            dev,
            "import display; display.init(True); import time; time.sleep_ms(100)",
            _ser.baud,
            5
        )

        escaped_msg = message.replace("'", "\\'")
        code = (
            f"import lvgl as lv; scr = lv.scr_act(); scr.clean(); "
            f"lbl = lv.label(scr); lbl.set_text('{escaped_msg}'); "
            f"style = lbl.get_style(lv.label.STYLE.MAIN); "
            f"style.text.font = lv.font_roboto_28; "
            f"lbl.refresh_style(); lbl.align(None, lv.ALIGN.CENTER, 0, 0)"
        )

        console.echo(f"Displaying: {message}")
        repl_backend.exec_code(dev, code, _ser.baud, 3)
        console.secho("Done!", fg="green")

    except pyserial.SerialException as e:
        raise console.CliError(f"Serial error: {e}")


def repl_ls(path: str):
    """List files on the board.

    \b
    Examples:
      disco repl ls
      disco repl ls /flash
      disco repl ls /sd
    """
    dev = _ser.require_device()
    with repl_backend.mpremote_transport(dev, _ser.baud) as transport:
        try:
            files = transport.fs_listdir(path)
            console.secho(f"=== {path} ===", fg="blue")
            for f in files:
                if f.st_mode & 0x4000:  # directory
                    console.secho(f"  {f.name}/", fg="cyan")
                else:
                    console.echo(f"  {f.name} ({f.st_size} bytes)")
        except Exception as e:
            raise console.CliError(f"Error listing {path}: {e}")


def repl_cat(path: str):
    """Print file contents from board.

    \b
    Examples:
      disco repl cat /flash/main.py
      disco repl cat /flash/boot.py
    """
    dev = _ser.require_device()
    with repl_backend.mpremote_transport(dev, _ser.baud) as transport:
        try:
            data = transport.fs_readfile(path)
            console.echo(data.decode("utf-8", errors="replace"))
        except Exception as e:
            raise console.CliError(f"Error reading {path}: {e}")


def repl_cp(src: str, dest: str):
    """Copy file to/from board.

    Use : prefix for board paths.

    \b
    Examples:
      disco repl cp local.py :/flash/local.py    # local -> board
      disco repl cp :/flash/main.py ./main.py    # board -> local
    """
    dev = _ser.require_device()

    if src.startswith(":") and not dest.startswith(":"):
        # Board -> local
        board_path = src[1:]
        local_path = dest
        with repl_backend.mpremote_transport(dev, _ser.baud) as transport:
            try:
                data = transport.fs_readfile(board_path)
                with open(local_path, "wb") as f:
                    f.write(data)
                console.secho(f"Copied {board_path} -> {local_path} ({len(data)} bytes)", fg="green")
            except Exception as e:
                raise console.CliError(f"Error copying: {e}")

    elif not src.startswith(":") and dest.startswith(":"):
        # Local -> board
        local_path = src
        board_path = dest[1:]
        if not os.path.exists(local_path):
            raise console.CliError(f"Local file not found: {local_path}")
        with open(local_path, "rb") as f:
            data = f.read()
        with repl_backend.mpremote_transport(dev, _ser.baud) as transport:
            try:
                transport.fs_writefile(board_path, data)
                console.secho(f"Copied {local_path} -> {board_path} ({len(data)} bytes)", fg="green")
            except Exception as e:
                raise console.CliError(f"Error copying: {e}")

    else:
        raise console.CliError("Use : prefix for board paths (e.g., :/flash/file.py)")


def repl_import(module: str, timeout: int):
    """Import a module and show output/errors.

    Useful for testing boot sequence - imports the module that boot.py
    would normally run via pyb.main(). Shows any import errors or
    stacktraces that occur during module initialization.

    \b
    This is the recommended way to debug boot failures:
      1. Flash debug firmware
      2. Run: disco repl import
      3. See any stacktraces from failed imports

    \b
    Examples:
      disco repl import                    # import hardwaretest (default)
      disco repl import gui                # test GUI module only
      disco repl import gui.components     # test specific submodule
    """
    from ..openocd import OpenOCD

    ocd = OpenOCD()

    # Stop OpenOCD if running (it blocks USB CDC)
    if ocd.is_running():
        console.echo("Stopping OpenOCD...")
        ocd.stop()
        time.sleep(1)

    # Wait for USB CDC device
    console.echo("Waiting for USB CDC device...")
    for _ in range(10):
        dev = _ser.auto_detect()
        if dev:
            break
        time.sleep(1)
    else:
        raise console.CliError("USB CDC device not found. Is miniUSB connected?")

    console.echo(f"Device: {dev}")
    console.echo(f"Importing '{module}'...")
    console.echo()

    try:
        output = repl_backend.exec_code(dev, f"import {module}", _ser.baud, timeout)
        if output:
            console.echo(output)
        else:
            console.secho(f"Module '{module}' imported successfully (no output)", fg="green")
    except pyserial.SerialException as e:
        raise console.CliError(f"Serial error: {e}")


def repl_rm(path: str, force: bool):
    """Remove file from board.

    \b
    Examples:
      disco repl rm /flash/test.py
      disco repl rm /flash/test.py -f
    """
    dev = _ser.require_device()
    if not force:
        if not console.confirm(f"Delete {path}?"):
            console.echo("Aborted")
            return

    with repl_backend.mpremote_transport(dev, _ser.baud) as transport:
        try:
            transport.fs_rmfile(path)
            console.secho(f"Removed {path}", fg="green")
        except Exception as e:
            raise console.CliError(f"Error removing {path}: {e}")
