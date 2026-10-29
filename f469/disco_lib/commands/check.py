"""Board check command."""

from .. import console

from ..ocd_provider import get_ocd
from .. import cpu as cpu_backend
from .. import memory
from .. import flash as flash_backend
from ..diagnostics import is_rdp_enabled


def check(no_resume: bool):
    """Run full board diagnostics.

    By default, resumes CPU after check to keep USB CDC working.
    Use --no-resume to keep halted for further debugging.
    """
    with get_ocd().ensure_running():
        console.secho("=== Board Diagnostic Check ===", fg="blue")

        cpu_backend.halt(get_ocd())
        try:
            console.secho("\n1. CPU State", fg="yellow")
            console.echo(cpu_backend.read_reg(get_ocd(), "pc"))
            console.echo(cpu_backend.read_reg(get_ocd(), "sp"))
            console.echo(cpu_backend.read_reg(get_ocd(), "lr"))

            console.secho("\n2. Vector Table (0x08000000)", fg="yellow")
            console.echo(memory.read_words(get_ocd(), 0x08000000, 4))

            console.secho("\n3. Firmware Area (0x08020000)", fg="yellow")
            console.echo(memory.read_words(get_ocd(), 0x08020000, 4))

            console.secho("\n4. RAM Check (0x20000000)", fg="yellow")
            console.echo(memory.read_words(get_ocd(), 0x20000000, 4))

            console.secho("\n5. Flash Info", fg="yellow")
            flash_info = flash_backend.read_info(get_ocd())
            if is_rdp_enabled(flash_info):
                console.secho("RDP: enabled (flash locked)", fg="yellow")
            else:
                console.secho("RDP: disabled", fg="green")
            console.echo(flash_info)
        finally:
            if no_resume:
                console.secho("\nCPU left halted (--no-resume). USB CDC disconnected.", fg="yellow")
            else:
                cpu_backend.resume(get_ocd())
                console.secho("\nCPU resumed. USB CDC should reconnect.", fg="green")
