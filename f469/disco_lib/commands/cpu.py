"""CPU control commands."""

from .. import console

from ..ocd_provider import get_ocd
from .. import cpu as cpu_backend
from .. import memory


def cpu():
    """CPU control commands.

    Control the ARM Cortex-M4 CPU via JTAG/SWD through OpenOCD.
    Commands auto-connect to OpenOCD when needed.

    \b
    WARNING: Halting the CPU disconnects USB CDC (REPL).
    Use 'disco cpu resume' or 'disco ocd cmd reset run' to restore.

    \b
    Typical debug workflow:
      1. disco cpu halt        # Stop execution (USB disconnects!)
      2. disco cpu pc          # See where we are
      3. disco cpu regs        # Check register state
      4. disco cpu step        # Single-step through code
      5. disco cpu resume      # Continue running (USB reconnects)

    \b
    Note: Use 'disco ocd start' to keep OpenOCD running persistently.
    """
    pass


def cpu_halt():
    """Halt the CPU.

    WARNING: This disconnects USB CDC - REPL will be unavailable until resumed.
    """
    with get_ocd().ensure_running():
        cpu_backend.halt(get_ocd())
        console.secho("CPU halted", fg="green")
        console.secho("Note: USB CDC (REPL) disconnected while halted", fg="yellow")
        console.echo(cpu_backend.read_pc_sp(get_ocd()))


def cpu_resume():
    """Resume execution."""
    with get_ocd().ensure_running():
        cpu_backend.resume(get_ocd())
        console.secho("CPU resumed", fg="green")


def cpu_reset():
    """Reset and halt."""
    with get_ocd().ensure_running():
        cpu_backend.reset_halt(get_ocd())
        console.secho("CPU reset and halted", fg="green")
        console.echo(cpu_backend.read_pc_sp(get_ocd()))


def cpu_step():
    """Single step."""
    with get_ocd().ensure_running():
        cpu_backend.step(get_ocd())
        console.echo(cpu_backend.read_reg(get_ocd(), "pc"))


def cpu_regs():
    """Show all CPU registers."""
    with get_ocd().ensure_running():
        console.secho("=== CPU Registers ===", fg="blue")
        with cpu_backend.halted(get_ocd()):
            console.echo(cpu_backend.read_regs(get_ocd()))


def cpu_pc():
    """Show current PC and memory around it."""
    with get_ocd().ensure_running():
        console.secho("=== Current PC ===", fg="blue")
        with cpu_backend.halted(get_ocd()):
            pc_val = cpu_backend.read_pc(get_ocd())
            if pc_val is not None:
                console.echo(f"PC: 0x{pc_val:08x}")
                console.echo()
                console.echo("Memory around PC:")
                pc_aligned = (pc_val & ~0xF) - 0x10
                console.echo(memory.read_words(get_ocd(), pc_aligned, 16))
            else:
                console.echo(cpu_backend.read_reg(get_ocd(), "pc"))


def cpu_stack(count: int):
    """Show stack (N words, default 16)."""
    with get_ocd().ensure_running():
        console.secho(f"=== Stack ({count} words) ===", fg="blue")
        with cpu_backend.halted(get_ocd()):
            sp_val = cpu_backend.read_sp(get_ocd())
            if sp_val is not None:
                console.echo(f"SP: 0x{sp_val:08x}")
                console.echo(memory.read_words(get_ocd(), sp_val, count))
            else:
                console.echo(cpu_backend.read_reg(get_ocd(), "sp"))


def cpu_gdb(elf: str, run: bool):
    """Show or launch GDB command for debugging.

    \b
    With no arguments, prints the GDB command to connect to target.
    With --run, actually launches GDB.

    \b
    Examples:
      disco cpu gdb                           # Print GDB command
      disco cpu gdb firmware.elf              # Print command with ELF
      disco cpu gdb firmware.elf --run        # Launch GDB with ELF
      disco cpu gdb --run                     # Launch GDB without ELF

    \b
    GDB Commands Cheat Sheet:
      target remote :3333    # Connect to OpenOCD (done automatically)
      monitor halt           # Halt CPU via OpenOCD
      monitor reset halt     # Reset and halt
      load                   # Load ELF to target (if ELF provided)
      break main             # Set breakpoint
      continue               # Run
      step / next            # Step into / over
      info registers         # Show registers
      x/10x $sp              # Examine memory at SP
    """
    import os
    import shutil

    # GDB connects to OpenOCD separately, so we just verify it's running
    # (don't auto-start/stop - that would break GDB's connection)
    if not get_ocd().is_running():
        raise console.CliError("OpenOCD not running. Run 'disco ocd start' first.")

    # Find GDB
    gdb_names = ["arm-none-eabi-gdb", "gdb-multiarch", "gdb"]
    gdb_path = None
    for name in gdb_names:
        if shutil.which(name):
            gdb_path = name
            break

    if not gdb_path:
        console.secho("Error: No ARM GDB found. Install arm-none-eabi-gdb", fg="red")
        return

    # Build command
    cmd_parts = [gdb_path]
    if elf:
        cmd_parts.append(os.path.abspath(elf))
    cmd_parts.extend(["-ex", "target remote :3333"])

    cmd_str = " ".join(f'"{p}"' if " " in p else p for p in cmd_parts)

    if run:
        console.secho(f"Launching: {cmd_str}", fg="green")
        os.execvp(gdb_path, cmd_parts)
    else:
        console.secho("=== GDB Command ===", fg="blue")
        console.echo(cmd_str)
        console.echo()
        console.secho("Run with --run flag to launch, or copy/paste the command", fg="yellow")
