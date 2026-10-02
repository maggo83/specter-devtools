"""Tests for repl.py backend.

The repl module handles MicroPython REPL communication:
  - filter_repl_output: Clean up raw serial output to extract results
  - exec_code: Send code and get filtered response
  - hard_reset: machine.reset() over the REPL

The key testable logic is in filter_repl_output, which must handle
the messy reality of serial REPL output (echoes, prompts, \r\n, etc).
"""

import pytest

from disco_lib.repl import filter_repl_output


class TestFilterReplOutput:
    """Tests for filter_repl_output() - cleans raw REPL response.

    MicroPython REPL output includes:
      - Command echo (what we typed)
      - Prompts (>>>, ...)
      - Carriage returns (\r)
      - The actual result we want

    This function strips everything except the result.
    """

    def test_simple_expression(self):
        """Simple expression like '1 + 1' returns just the result."""
        # Raw output: echo, result, prompt
        raw = "1 + 1\r\n2\r\n>>> "
        assert filter_repl_output(raw, "1 + 1") == "2"

    def test_strips_command_echo(self):
        """Command echo (what we sent) is removed."""
        raw = "print('hello')\r\nhello\r\n>>> "
        assert filter_repl_output(raw, "print('hello')") == "hello"

    def test_strips_prompt_prefix(self):
        """Lines starting with >>> have prefix removed."""
        raw = ">>> 42\r\n>>> "
        assert filter_repl_output(raw, "x") == "42"

    def test_strips_continuation_prefix(self):
        """Lines starting with ... (continuation) have prefix removed."""
        raw = "... something\r\n>>> "
        assert filter_repl_output(raw, "x") == "something"

    def test_removes_empty_prompts(self):
        """Standalone >>> or ... lines are removed entirely."""
        raw = ">>>\r\n...\r\n>>> \r\nresult\r\n>>> "
        assert filter_repl_output(raw, "x") == "result"

    def test_strips_carriage_returns(self):
        """Carriage returns are stripped from line endings."""
        raw = "value\r\n"
        assert filter_repl_output(raw, "x") == "value"
        assert "\r" not in filter_repl_output(raw, "x")

    def test_multiline_output(self):
        """Multi-line output is preserved (minus prompts/echo)."""
        raw = "help()\r\nLine 1\r\nLine 2\r\nLine 3\r\n>>> "
        result = filter_repl_output(raw, "help()")
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_empty_output(self):
        """Commands with no output return empty string."""
        raw = "x = 1\r\n>>> "
        assert filter_repl_output(raw, "x = 1") == ""

    def test_whitespace_in_code_matched(self):
        """Code matching ignores leading/trailing whitespace."""
        raw = "  print('hi')  \r\nhi\r\n>>> "
        # Code has extra spaces but should still match
        assert filter_repl_output(raw, "print('hi')") == "hi"

    # Real-world MicroPython output examples

    def test_sys_implementation(self):
        """Real output from 'import sys; print(sys.implementation)'."""
        code = "import sys; print(sys.implementation)"
        raw = (
            "import sys; print(sys.implementation)\r\n"
            "(name='micropython', version=(1, 19, 1))\r\n"
            ">>> "
        )
        result = filter_repl_output(raw, code)
        assert result == "(name='micropython', version=(1, 19, 1))"

    def test_gc_mem_free(self):
        """Real output from gc.mem_free()."""
        code = "import gc; gc.collect(); print(gc.mem_free())"
        raw = (
            "import gc; gc.collect(); print(gc.mem_free())\r\n"
            "123456\r\n"
            ">>> "
        )
        result = filter_repl_output(raw, code)
        assert result == "123456"

    def test_help_modules_multiline(self):
        """Real output from help('modules') - many lines."""
        code = "help('modules')"
        raw = (
            "help('modules')\r\n"
            "__main__          gc                sys               uos\r\n"
            "_thread           machine           time              ustruct\r\n"
            "builtins          micropython       uasyncio          \r\n"
            ">>> "
        )
        result = filter_repl_output(raw, code)
        lines = result.split("\n")
        assert len(lines) == 3
        assert "__main__" in lines[0]
        assert "machine" in lines[1]

    def test_error_traceback(self):
        """Tracebacks are preserved for debugging."""
        code = "1/0"
        raw = (
            "1/0\r\n"
            "Traceback (most recent call last):\r\n"
            "  File \"<stdin>\", line 1, in <module>\r\n"
            "ZeroDivisionError: divide by zero\r\n"
            ">>> "
        )
        result = filter_repl_output(raw, code)
        assert "Traceback" in result
        assert "ZeroDivisionError" in result

    def test_import_no_output(self):
        """Successful import with no print has no output."""
        code = "import machine"
        raw = "import machine\r\n>>> "
        assert filter_repl_output(raw, code) == ""

    def test_multiple_prompts_in_sequence(self):
        """Handle messy output with multiple prompt sequences."""
        raw = ">>> \r\n>>> \r\n>>> result\r\n>>> \r\n"
        assert filter_repl_output(raw, "x") == "result"

    def test_result_on_same_line_as_prompt(self):
        """Result immediately after prompt on same line."""
        raw = ">>> 123"
        assert filter_repl_output(raw, "x") == "123"

    def test_preserves_internal_whitespace(self):
        """Whitespace within output lines is preserved."""
        code = "print('a  b')"
        raw = "print('a  b')\r\na  b\r\n>>> "
        assert filter_repl_output(raw, code) == "a  b"


class TestExecCode:
    """exec_code must return as soon as the REPL prompt comes back."""

    @pytest.mark.parametrize("after_interrupt", [b"\r\n>>> ", b"old\r\n>>> \r\n>>> "])
    def test_returns_output_without_waiting_for_timeout(self, monkeypatch, after_interrupt):
        from disco_lib import repl

        class FakeSerial:
            def __init__(self, dev, baud, timeout):
                self.pending = b""
                self.written = []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, data):
                self.written.append(data)
                if data == b"\x03":
                    self.pending += after_interrupt
                else:
                    self.pending += data + b"42\r\n>>> "

            def read_until(self, expected):
                end = self.pending.index(expected) + len(expected)
                data, self.pending = self.pending[:end], self.pending[end:]
                return data

            def read(self, size):
                raise AssertionError("fixed-size reads wait for the full timeout")

        monkeypatch.setattr(repl.pyserial, "Serial", FakeSerial)
        assert repl.exec_code("/dev/fake", "print(6*7)") == "42"


class TestWaitForPrompt:
    """wait_for_prompt waits for the port to return and the REPL to answer."""

    @staticmethod
    def _serial(monkeypatch, replies):
        from disco_lib import repl

        written = []

        class FakeSerial:
            def __init__(self, dev, baud, timeout):
                reply = replies.pop(0) if len(replies) > 1 else replies[0]
                if isinstance(reply, Exception):
                    raise reply
                self.reply = reply

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def reset_input_buffer(self):
                pass

            def write(self, data):
                written.append(data)

            def read_until(self, expected):
                return self.reply

        monkeypatch.setattr(repl.pyserial, "Serial", FakeSerial)
        monkeypatch.setattr(repl.time, "sleep", lambda s: None)
        return repl, written

    def test_waits_for_the_port_and_the_prompt_without_interrupting(self, monkeypatch):
        import serial

        repl, written = self._serial(monkeypatch, [
            serial.SerialException("port is re-enumerating"),
            b"",
            b"\r\nMicroPython v1.25\r\n>>> ",
        ])
        devices = iter([None, "/dev/fake", "/dev/fake", "/dev/fake"])

        assert repl.wait_for_prompt(lambda: next(devices), timeout=5, poll=0) == "/dev/fake"
        assert written == [b"\x02", b"\x02"]

    def test_times_out_when_the_prompt_never_comes(self, monkeypatch):
        repl, _ = self._serial(monkeypatch, [b""])

        with pytest.raises(TimeoutError, match="No REPL prompt within 0.05 s"):
            repl.wait_for_prompt(lambda: "/dev/fake", timeout=0.05, poll=0)

    def test_cli_fails_on_timeout(self, monkeypatch):
        import importlib

        from click.testing import CliRunner

        repl_commands = importlib.import_module("disco_lib.commands.repl")

        def timeout(*args):
            raise TimeoutError("No REPL prompt within 1 s")

        monkeypatch.setattr(repl_commands.repl_backend, "wait_for_prompt", timeout)
        result = CliRunner().invoke(repl_commands.repl, ["wait", "--timeout", "1"])

        assert result.exit_code == 1
        assert "No REPL prompt within 1 s" in result.output


class TestNoSoftReset:
    """The board is never soft-reset: MockUI's display.init() fails after one."""

    def test_hard_reset_runs_machine_reset_and_survives_the_disconnect(self, monkeypatch):
        import serial

        from disco_lib import repl

        written = []

        class DisconnectingSerial:
            def __init__(self, dev, baud, timeout):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, data):
                written.append(data)

            def read_until(self, expected):
                if expected != b">>> ":
                    raise serial.SerialException("device disconnected")
                return b"\r\n>>> "

        monkeypatch.setattr(repl.pyserial, "Serial", DisconnectingSerial)
        monkeypatch.setattr(repl.time, "sleep", lambda s: None)

        repl.hard_reset("/dev/fake")

        assert written == [b"\x03\x02", b"import machine; machine.reset()\r\n"]
        assert b"\x04" not in b"".join(written)

    def test_file_commands_enter_the_raw_repl_without_a_soft_reset(self, monkeypatch):
        import mpremote.transport_serial

        from disco_lib import repl

        calls = []

        class FakeTransport:
            def __init__(self, dev, baud):
                pass

            def enter_raw_repl(self, soft_reset=True):
                calls.append(soft_reset)

            def exit_raw_repl(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(mpremote.transport_serial, "SerialTransport", FakeTransport)
        with repl.mpremote_transport("/dev/fake"):
            pass

        assert calls == [False]

    def test_reset_command_resets_then_waits(self, monkeypatch):
        import importlib

        from click.testing import CliRunner

        commands = importlib.import_module("disco_lib.commands.repl")
        steps = []
        monkeypatch.setattr(commands._ser, "require_device", lambda: "/dev/fake")
        monkeypatch.setattr(commands.repl_backend, "hard_reset", lambda dev, baud: steps.append("reset"))

        def wait(find, baud, timeout):
            steps.append(("wait", timeout))
            raise TimeoutError(f"No REPL prompt within {timeout} s")

        monkeypatch.setattr(commands.repl_backend, "wait_for_prompt", wait)
        result = CliRunner().invoke(commands.repl, ["reset", "--timeout", "5"])

        assert steps == ["reset", ("wait", 5)]
        assert result.exit_code == 1 and "No REPL prompt within 5 s" in result.output
