"""OpenOCD communication via telnet."""

import re
import socket
import subprocess
import time
from contextlib import contextmanager
from typing import Generator

import click

from . import OPENOCD_CFG, OPENOCD_LOG, OPENOCD_PORT

STOP_TIMEOUT = 3.0
STOP_POLL_INTERVAL = 0.05


class OpenOCD:
    """Communicate with OpenOCD via telnet."""

    def __init__(self, port: int = OPENOCD_PORT):
        self.port = port
        self._process = None

    def is_running(self) -> bool:
        """Check if OpenOCD is listening."""
        try:
            with socket.create_connection(("localhost", self.port), timeout=1):
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False

    def send(self, cmd: str, timeout: float = 2.0) -> str:
        """Send command to OpenOCD and return response.

        For long-running commands (like flash programming), use a larger timeout.
        The method waits for the connection to close (after 'exit' command completes)
        rather than relying solely on read timeouts.
        """
        try:
            with socket.create_connection(("localhost", self.port), timeout=timeout) as sock:
                # Drain any initial banner (OpenOCD typically sends none)
                sock.setblocking(False)
                try:
                    sock.recv(4096)
                except BlockingIOError:
                    pass  # No data available - expected
                sock.setblocking(True)

                # Send command + exit
                # Note: OpenOCD executes commands sequentially, so 'exit' runs after cmd completes
                sock.sendall(f"{cmd}\nexit\n".encode())

                # Collect response with adaptive timeout
                # Use short timeout for individual reads, but keep reading until connection closes
                response = b""
                sock.settimeout(2.0)  # Short timeout per read
                deadline = time.monotonic() + timeout
                completed = False

                while time.monotonic() < deadline:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            # Connection closed - command completed
                            completed = True
                            break
                        response += chunk
                    except socket.timeout:
                        continue
                if not completed:
                    raise click.ClickException(
                        f"OpenOCD command timed out after {timeout:g} s"
                    )

                # Clean up response
                text = response.decode("utf-8", errors="replace")
                text = text.replace("\r", "")
                # Remove control chars except newlines
                text = re.sub(r"[^\x20-\x7e\n]", "", text)
                # Filter out prompts, OpenOCD banner, and command echo
                lines = []
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith(">"):
                        continue
                    if "Open On-Chip" in line:
                        continue
                    # Filter command echo (starts with command name like "mdw", "reg", etc)
                    if line == cmd or line.startswith(cmd.split()[0] + " "):
                        continue
                    lines.append(line)
                return "\n".join(lines)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            raise click.ClickException(f"OpenOCD connection failed: {e}")

    def start(self) -> bool:
        """Start OpenOCD in background. Returns True if started successfully."""
        if self.is_running():
            click.secho("OpenOCD already running", fg="yellow")
            return True

        click.secho("Starting OpenOCD...", fg="blue")
        with open(OPENOCD_LOG, "w") as log:
            self._process = subprocess.Popen(
                ["openocd", "-f", OPENOCD_CFG],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )

        # Wait for startup
        for _ in range(10):
            time.sleep(0.3)
            if self.is_running():
                click.secho("OpenOCD connected successfully", fg="green")
                # Report without halting: a halted CPU stops the UI and USB CDC.
                click.echo(f"Target info:\n{self.send('targets')}")
                return True

        click.secho(f"Failed to connect. Check {OPENOCD_LOG}", fg="red")
        try:
            with open(OPENOCD_LOG) as f:
                click.echo(f.read())
        except FileNotFoundError:
            click.echo(f"(log file {OPENOCD_LOG} not found)")
        self.stop()
        return False

    def stop(self) -> None:
        """Stop OpenOCD and wait until its command endpoint is gone."""
        if self._process is not None:
            process = self._process
            try:
                process.terminate()
                process.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                click.secho(
                    "OpenOCD did not stop after SIGTERM; killing it",
                    fg="yellow",
                )
                process.kill()
                try:
                    process.wait(timeout=STOP_TIMEOUT)
                except subprocess.TimeoutExpired as error:
                    raise click.ClickException(
                        f"OpenOCD could not be killed within {STOP_TIMEOUT:g} s"
                    ) from error
            finally:
                self._process = None
            click.secho("OpenOCD stopped", fg="green")
            return

        result = subprocess.run(["pkill", "-x", "openocd"], capture_output=True)
        if result.returncode == 0:
            deadline = time.monotonic() + STOP_TIMEOUT
            while self.is_running():
                if time.monotonic() >= deadline:
                    raise click.ClickException(
                        f"OpenOCD did not stop within {STOP_TIMEOUT:g} s"
                    )
                time.sleep(STOP_POLL_INTERVAL)
            click.secho("OpenOCD stopped", fg="green")
        else:
            click.secho("OpenOCD not running", fg="yellow")

    @contextmanager
    def ensure_running(self) -> Generator["OpenOCD", None, None]:
        """Context manager ensuring OpenOCD is running.

        If OpenOCD wasn't running, starts it and stops it on exit.
        If OpenOCD was already running, leaves it running.

        Usage:
            with ocd.ensure_running():
                result = ocd.send("reg pc")
        """
        was_running = self.is_running()
        if not was_running:
            if not self.start():
                raise click.ClickException("Failed to start OpenOCD")
        try:
            yield self
        finally:
            if not was_running:
                self.stop()
