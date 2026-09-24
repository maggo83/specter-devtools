"""Tests for disco ui commands (screen, click, write, screenshot)."""

import json
import os
import struct
import tempfile
import zlib

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from disco_lib.commands.ui import (
    ui_screen, ui_click, ui_write, ui_screenshot, ui_control,
    _raw_to_png, _FB_SIZE, _FB_WIDTH, _FB_HEIGHT, _FB_BPP,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repl():
    """Mock serial device + REPL backend so ui commands don't need hardware.

    Patches _ser.require_device() and repl_backend.exec_raw().
    The first exec_raw call returns '9' (LVGL version check), subsequent
    calls return whatever mock_exec.return_value is set to.
    """
    with patch("disco_lib.commands.ui._ser") as ser_mock, \
         patch("disco_lib.commands.ui.repl_backend") as repl_mock:
        ser_mock.require_device.return_value = "/dev/ttyACM0"
        ser_mock.baud = 115200

        # Default: version check returns '9', command returns 'OK'
        repl_mock.exec_raw.side_effect = None
        repl_mock.exec_raw.return_value = "OK"

        def _version_then(command_output):
            """Helper: return '9' for version check, then command_output."""
            call_count = [0]
            def _side_effect(dev, script, baud, timeout=10):
                call_count[0] += 1
                if call_count[0] == 1:
                    return "9"
                return command_output
            repl_mock.exec_raw.side_effect = _side_effect

        repl_mock._version_then = _version_then
        yield repl_mock


# ---------------------------------------------------------------------------
# Helpers for PNG tests
# ---------------------------------------------------------------------------

def _write_raw_file(data):
    """Write raw data to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".bin")
    os.write(fd, data)
    os.close(fd)
    return path


def _fake_dump(ocd, filepath, addr, size, timeout=60):
    """Fake memory.dump_to_file that writes zeroed data."""
    with open(filepath, "wb") as f:
        f.write(b"\x00" * size)
    return True


def _parse_png(path):
    """Minimal PNG parser — returns (width, height, bit_depth, color_type, pixel_data)."""
    with open(path, "rb") as f:
        sig = f.read(8)
        assert sig == b"\x89PNG\r\n\x1a\n", "bad PNG signature"

        chunks = {}
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            length, = struct.unpack(">I", hdr[:4])
            tag = hdr[4:8]
            data = f.read(length)
            f.read(4)  # CRC
            chunks[tag] = data

    ihdr = chunks[b"IHDR"]
    width, height = struct.unpack(">II", ihdr[:8])
    bit_depth, color_type = ihdr[8], ihdr[9]

    raw_scanlines = zlib.decompress(chunks[b"IDAT"])
    return width, height, bit_depth, color_type, raw_scanlines


# ===========================================================================
# ui screen tests
# ===========================================================================

class TestUIScreen:
    """Tests for the 'disco ui screen' command."""

    def test_screen_text_output(self, mock_repl):
        """Should print widget tree in text mode."""
        tree_text = '[0] obj cc=3\n  [0] label "Hello"'
        mock_repl._version_then(tree_text)

        runner = CliRunner()
        result = runner.invoke(ui_screen, [])
        assert result.exit_code == 0
        assert "label" in result.output
        assert "Hello" in result.output

    def test_screen_json_output(self, mock_repl):
        """--json flag should output formatted JSON."""
        tree_json = json.dumps([{"type": "obj", "children": [
            {"type": "label", "text": "Hi", "children": []}
        ]}])
        mock_repl._version_then(tree_json)

        runner = CliRunner()
        result = runner.invoke(ui_screen, ["--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["children"][0]["text"] == "Hi"

    def test_screen_json_fallback_on_bad_json(self, mock_repl):
        """If device returns invalid JSON, should print raw output."""
        mock_repl._version_then("not valid json {{{")

        runner = CliRunner()
        result = runner.invoke(ui_screen, ["--json"])
        assert result.exit_code == 0
        assert "not valid json" in result.output

    def test_screen_lvgl8_rejected(self, mock_repl):
        """Should fail if LVGL 8 is detected."""
        mock_repl.exec_raw.side_effect = None
        mock_repl.exec_raw.return_value = "8"

        runner = CliRunner()
        result = runner.invoke(ui_screen, [])
        assert result.exit_code != 0
        assert "Unsupported LVGL version" in result.output

    def test_screen_repl_error(self, mock_repl):
        """Should report error if REPL exec fails."""
        call_count = [0]
        def _fail_on_tree(dev, script, baud, timeout=10):
            call_count[0] += 1
            if call_count[0] == 1:
                return "9"
            raise RuntimeError("device disconnected")
        mock_repl.exec_raw.side_effect = _fail_on_tree

        runner = CliRunner()
        result = runner.invoke(ui_screen, [])
        assert result.exit_code != 0
        assert "device disconnected" in result.output

    def test_screen_version_check_error(self, mock_repl):
        """Should report error if version check itself fails."""
        mock_repl.exec_raw.side_effect = RuntimeError("no response")

        runner = CliRunner()
        result = runner.invoke(ui_screen, [])
        assert result.exit_code != 0
        assert "Cannot detect LVGL" in result.output


class TestGenericControl:
    """Tests for the generic JSON UI-control adapter."""

    def test_forwards_json_request_without_firmware_module(self, mock_repl):
        mock_repl._version_then('{"path":[],"type":"screen"}')

        runner = CliRunner()
        result = runner.invoke(ui_control, ['{"action":"tree"}'])

        assert result.exit_code == 0
        assert json.loads(result.output)["ok"] is True
        script = mock_repl.exec_raw.call_args_list[-1].args[1]
        assert "import lvgl as lv" in script
        assert "MockUI" not in script

    def test_hardware_capabilities_advertise_touch_and_coordinate_clicks(self, mock_repl):
        mock_repl._version_then("unused")

        runner = CliRunner()
        result = runner.invoke(ui_control, ['{"action":"capabilities"}'])

        assert result.exit_code == 0
        ui = json.loads(result.output)["ui"]
        assert ui["click"] == ["text", "path", "coordinates"]
        assert ui["touch"] is True

    def test_application_action_returns_hardware_unsupported_response(self, mock_repl):
        mock_repl._version_then("unused")

        runner = CliRunner()
        result = runner.invoke(ui_control, ['{"action":"get_state"}'])

        assert result.exit_code == 0
        assert json.loads(result.output) == {
            "ok": False,
            "error": "Unsupported action on hardware: get_state",
        }

    def test_rejects_invalid_request_json(self):
        runner = CliRunner()

        result = runner.invoke(ui_control, ["not-json"])

        assert result.exit_code != 0
        assert "Invalid request JSON" in result.output


# ===========================================================================
# ui click tests
# ===========================================================================

class TestUIClick:
    """Tests for the 'disco ui click' command."""

    def test_click_by_text_ok(self, mock_repl):
        """Clicking by label text should report success."""
        mock_repl._version_then("OK")

        runner = CliRunner()
        result = runner.invoke(ui_click, ["Start"])
        assert result.exit_code == 0
        assert "Clicked widget" in result.output
        assert 'text "Start"' in result.output

    def test_click_by_index_ok(self, mock_repl):
        """Clicking by tree index should report success."""
        mock_repl._version_then("OK")

        runner = CliRunner()
        result = runner.invoke(ui_click, ["--index", "1.0.2"])
        assert result.exit_code == 0
        assert "Clicked widget" in result.output
        assert "index 1.0.2" in result.output

    def test_click_not_found(self, mock_repl):
        """Should fail if widget text not found."""
        mock_repl._version_then("NOT_FOUND")

        runner = CliRunner()
        result = runner.invoke(ui_click, ["Missing"])
        assert result.exit_code != 0
        assert "No widget found" in result.output

    def test_click_index_error(self, mock_repl):
        """Should report index out of range."""
        mock_repl._version_then("INDEX_ERROR:5:3")

        runner = CliRunner()
        result = runner.invoke(ui_click, ["-i", "0.5"])
        assert result.exit_code != 0
        assert "out of range" in result.output
        assert "5" in result.output
        assert "3" in result.output

    def test_click_no_args_fails(self):
        """Should fail if neither text nor --index is provided."""
        runner = CliRunner()
        result = runner.invoke(ui_click, [])
        assert result.exit_code != 0
        assert "Provide TEXT or --index" in result.output

    def test_click_both_args_fails(self):
        """Should fail if both text and --index are provided."""
        runner = CliRunner()
        result = runner.invoke(ui_click, ["Hello", "-i", "0.1"])
        assert result.exit_code != 0
        assert "not both" in result.output

    def test_click_unexpected_response(self, mock_repl):
        """Should fail on unexpected device response."""
        mock_repl._version_then("SOMETHING_WEIRD")

        runner = CliRunner()
        result = runner.invoke(ui_click, ["btn"])
        assert result.exit_code != 0
        assert "Unexpected response" in result.output

    def test_click_repl_error(self, mock_repl):
        """Should report error if REPL exec fails."""
        call_count = [0]
        def _fail(dev, script, baud, timeout=10):
            call_count[0] += 1
            if call_count[0] == 1:
                return "9"
            raise RuntimeError("timeout")
        mock_repl.exec_raw.side_effect = _fail

        runner = CliRunner()
        result = runner.invoke(ui_click, ["btn"])
        assert result.exit_code != 0
        assert "timeout" in result.output


# ===========================================================================
# ui write tests
# ===========================================================================

class TestUIWrite:
    """Tests for the 'disco ui write' command."""

    def test_write_ok(self, mock_repl):
        """Should report success when textarea is set."""
        mock_repl._version_then("OK")

        runner = CliRunner()
        result = runner.invoke(ui_write, ["hello world"])
        assert result.exit_code == 0
        assert "Set textarea[0]" in result.output
        assert "hello world" in result.output

    def test_write_target_index(self, mock_repl):
        """Should use the --target index."""
        mock_repl._version_then("OK")

        runner = CliRunner()
        result = runner.invoke(ui_write, ["text", "--target", "2"])
        assert result.exit_code == 0
        assert "textarea[2]" in result.output

    def test_write_no_textarea(self, mock_repl):
        """Should fail if no textarea found."""
        mock_repl._version_then("NO_TEXTAREA")

        runner = CliRunner()
        result = runner.invoke(ui_write, ["text"])
        assert result.exit_code != 0
        assert "No textarea" in result.output

    def test_write_index_out_of_range(self, mock_repl):
        """Should fail if textarea index is out of range."""
        mock_repl._version_then("INDEX_OUT_OF_RANGE:2")

        runner = CliRunner()
        result = runner.invoke(ui_write, ["text", "-n", "5"])
        assert result.exit_code != 0
        assert "out of range" in result.output

    def test_write_unexpected_response(self, mock_repl):
        """Should fail on unexpected device response."""
        mock_repl._version_then("GARBAGE")

        runner = CliRunner()
        result = runner.invoke(ui_write, ["text"])
        assert result.exit_code != 0
        assert "Unexpected response" in result.output

    def test_write_repl_error(self, mock_repl):
        """Should report error if REPL exec fails."""
        call_count = [0]
        def _fail(dev, script, baud, timeout=10):
            call_count[0] += 1
            if call_count[0] == 1:
                return "9"
            raise RuntimeError("serial error")
        mock_repl.exec_raw.side_effect = _fail

        runner = CliRunner()
        result = runner.invoke(ui_write, ["text"])
        assert result.exit_code != 0
        assert "serial error" in result.output


# ===========================================================================
# _raw_to_png encoder tests
# ===========================================================================

class TestRawToPng:
    """Tests for the pure-Python PNG encoder."""

    def test_produces_valid_png_signature(self):
        """Output file must start with the 8-byte PNG magic."""
        raw_path = _write_raw_file(b"\x00" * _FB_SIZE)
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _raw_to_png(raw_path, png_path)
            with open(png_path, "rb") as f:
                assert f.read(8) == b"\x89PNG\r\n\x1a\n"
        finally:
            os.unlink(raw_path)
            os.unlink(png_path)

    def test_ihdr_dimensions(self):
        """IHDR chunk must contain correct width and height."""
        raw_path = _write_raw_file(b"\x00" * _FB_SIZE)
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _raw_to_png(raw_path, png_path)
            w, h, depth, ctype, _ = _parse_png(png_path)
            assert w == _FB_WIDTH
            assert h == _FB_HEIGHT
            assert depth == 8
            assert ctype == 6  # RGBA
        finally:
            os.unlink(raw_path)
            os.unlink(png_path)

    def test_pixel_channel_swap(self):
        """B and R channels must be swapped (BGRA in memory -> RGBA in PNG)."""
        # Single 1x1 pixel: memory [B=0x11, G=0x22, R=0x33, A=0xFF]
        raw_path = _write_raw_file(b"\x11\x22\x33\xFF")
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _raw_to_png(raw_path, png_path, width=1, height=1)
            _, _, _, _, scanlines = _parse_png(png_path)
            # scanline = filter_byte(0) + R G B A
            assert scanlines == b"\x00\x33\x22\x11\xFF"
        finally:
            os.unlink(raw_path)
            os.unlink(png_path)

    def test_small_image_roundtrip(self):
        """A 2x2 image should encode all pixels correctly."""
        # 2x2 pixels in BGRA order
        pixels = (
            b"\xFF\x00\x00\xFF"  # pixel(0,0): B=FF G=00 R=00 A=FF
            b"\x00\xFF\x00\xFF"  # pixel(1,0): B=00 G=FF R=00 A=FF
            b"\x00\x00\xFF\xFF"  # pixel(0,1): B=00 G=00 R=FF A=FF
            b"\x80\x80\x80\xFF"  # pixel(1,1): B=80 G=80 R=80 A=FF
        )
        raw_path = _write_raw_file(pixels)
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _raw_to_png(raw_path, png_path, width=2, height=2)
            _, _, _, _, scanlines = _parse_png(png_path)
            # Row 0: filter(0) + [R=00 G=00 B=FF A=FF] [R=00 G=FF B=00 A=FF]
            # Row 1: filter(0) + [R=FF G=00 B=00 A=FF] [R=80 G=80 B=80 A=FF]
            expected = (
                b"\x00" + b"\x00\x00\xFF\xFF" + b"\x00\xFF\x00\xFF"
                + b"\x00" + b"\xFF\x00\x00\xFF" + b"\x80\x80\x80\xFF"
            )
            assert scanlines == expected
        finally:
            os.unlink(raw_path)
            os.unlink(png_path)

    def test_custom_dimensions(self):
        """Encoder should respect custom width/height parameters."""
        w, h = 3, 2
        raw_path = _write_raw_file(b"\x00" * (w * h * 4))
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _raw_to_png(raw_path, png_path, width=w, height=h)
            pw, ph, _, _, _ = _parse_png(png_path)
            assert pw == w
            assert ph == h
        finally:
            os.unlink(raw_path)
            os.unlink(png_path)

    def test_png_has_iend_chunk(self):
        """Output must end with an IEND chunk."""
        raw_path = _write_raw_file(b"\x00" * 16)
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _raw_to_png(raw_path, png_path, width=2, height=2)
            with open(png_path, "rb") as f:
                data = f.read()
            # IEND chunk: length(0) + "IEND" + CRC
            iend_length = struct.unpack(">I", data[-12:-8])[0]
            iend_tag = data[-8:-4]
            assert iend_length == 0
            assert iend_tag == b"IEND"
        finally:
            os.unlink(raw_path)
            os.unlink(png_path)


# ===========================================================================
# Screenshot command halt/resume tests
# ===========================================================================

class TestScreenshotResumeCPU:
    """ui screenshot must always resume the CPU."""

    def test_screenshot_resumes_cpu(self, ocd_mock, tmp_path):
        """CPU must be resumed after a successful screenshot."""
        out = str(tmp_path / "shot.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_fake_dump):
            runner = CliRunner()
            result = runner.invoke(ui_screenshot, [out])
        assert result.exit_code == 0
        # ocd_mock fixture auto-asserts resumed at teardown

    def test_screenshot_resumes_on_dump_failure(self, ocd_mock):
        """CPU must be resumed even when dump_to_file fails."""
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   return_value=False):
            runner = CliRunner()
            result = runner.invoke(ui_screenshot, ["/tmp/_test_fail.png"])
        assert result.exit_code != 0
        assert "Failed to dump framebuffer" in result.output
        # ocd_mock fixture auto-asserts resumed at teardown

    def test_screenshot_resumes_on_exception(self, ocd_mock):
        """CPU must be resumed even when dump_to_file raises."""
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=Exception("connection lost")):
            runner = CliRunner()
            runner.invoke(ui_screenshot, ["/tmp/_test_exc.png"])
        # ocd_mock fixture auto-asserts resumed at teardown


# ===========================================================================
# Screenshot command functional tests
# ===========================================================================

class TestScreenshotCommand:
    """Functional tests for the screenshot command."""

    def test_creates_png_file(self, ocd_mock, tmp_path):
        """Command should create a valid PNG file."""
        out = str(tmp_path / "test.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_fake_dump):
            runner = CliRunner()
            result = runner.invoke(ui_screenshot, [out])
        assert result.exit_code == 0
        assert os.path.exists(out)
        with open(out, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"

    def test_default_output_path(self, ocd_mock):
        """Default output should be /tmp/screenshot.png."""
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   return_value=True), \
             patch("disco_lib.commands.ui._raw_to_png"), \
             patch("disco_lib.commands.ui.os.path.getsize",
                   return_value=_FB_SIZE):
            runner = CliRunner()
            result = runner.invoke(ui_screenshot, [])
        assert result.exit_code == 0
        assert "/tmp/screenshot.png" in result.output

    def test_sends_correct_dump_command(self, ocd_mock, tmp_path):
        """Should dump from framebuffer address with correct size."""
        out = str(tmp_path / "test.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_fake_dump) as mock_dump:
            runner = CliRunner()
            runner.invoke(ui_screenshot, [out])
        mock_dump.assert_called_once()
        args = mock_dump.call_args
        assert args[0][2] == 0xC0000000  # addr
        assert args[0][3] == _FB_SIZE    # size

    def test_custom_timeout(self, ocd_mock, tmp_path):
        """--timeout flag should be passed to dump_to_file."""
        out = str(tmp_path / "test.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_fake_dump) as mock_dump:
            runner = CliRunner()
            runner.invoke(ui_screenshot, [out, "--timeout", "60"])
        assert mock_dump.call_args[1]["timeout"] == 60

    def test_wrong_dump_size_fails(self, ocd_mock, tmp_path):
        """Should fail if dump file is the wrong size."""
        out = str(tmp_path / "test.png")

        def _bad_dump(ocd, filepath, addr, size, timeout=60):
            with open(filepath, "wb") as f:
                f.write(b"\x00" * 100)  # wrong size
            return True

        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_bad_dump):
            runner = CliRunner()
            result = runner.invoke(ui_screenshot, [out])
        assert result.exit_code != 0
        assert "Unexpected dump size" in result.output

    def test_cleans_up_temp_file(self, ocd_mock, tmp_path):
        """Temp .bin file should be cleaned up even on failure."""
        created_temps = []
        original_mkstemp = tempfile.mkstemp

        def _tracking_mkstemp(**kwargs):
            fd, path = original_mkstemp(**kwargs)
            created_temps.append(path)
            return fd, path

        out = str(tmp_path / "test.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   return_value=False), \
             patch("disco_lib.commands.ui.tempfile.mkstemp",
                   side_effect=_tracking_mkstemp):
            runner = CliRunner()
            runner.invoke(ui_screenshot, [out])

        for tmp in created_temps:
            assert not os.path.exists(tmp), f"temp file not cleaned up: {tmp}"

    def test_success_message(self, ocd_mock, tmp_path):
        """Should print success message with output path."""
        out = str(tmp_path / "shot.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_fake_dump):
            runner = CliRunner()
            result = runner.invoke(ui_screenshot, [out])
        assert "Screenshot saved to" in result.output
        assert out in result.output

    def test_halts_cpu_during_dump(self, ocd_mock_raw, tmp_path):
        """CPU should be halted when dump_to_file is called."""
        halted_during_dump = []

        def _check_halted(ocd, filepath, addr, size, timeout=60):
            halted_during_dump.append(ocd_mock_raw.halted)
            with open(filepath, "wb") as f:
                f.write(b"\x00" * size)
            return True

        out = str(tmp_path / "test.png")
        with patch("disco_lib.commands.ui.memory.dump_to_file",
                   side_effect=_check_halted):
            runner = CliRunner()
            runner.invoke(ui_screenshot, [out])

        assert halted_during_dump == [True], "CPU should be halted during dump"
        assert not ocd_mock_raw.halted, "CPU should be resumed after command"


class TestTransientActionScripts:
    """The text-entry script must pause LVGL timers and surface redraw errors."""

    @staticmethod
    def _install_fakes(monkeypatch, udisplay_module):
        import sys
        import types

        lvgl = types.ModuleType("lvgl")
        lvgl.EVENT = types.SimpleNamespace(CLICKED=7)
        lvgl.timer_states = []
        lvgl.timer_enable = lvgl.timer_states.append
        monkeypatch.setitem(sys.modules, "lvgl", lvgl)
        monkeypatch.setitem(sys.modules, "udisplay", udisplay_module)
        return lvgl

    @staticmethod
    def _exec_click_path(widget):
        from disco_lib.commands.ui import _WRITE_PATH_SCRIPT

        widget.get_child.return_value = widget
        script = (_WRITE_PATH_SCRIPT.replace("$ROOT", "_root")
                  .replace("$PATH", "[0]").replace("$TEXT", "'x'"))
        exec(script, {"_root": widget})

    def test_missing_udisplay_is_tolerated(self, monkeypatch, capsys):
        self._install_fakes(monkeypatch, None)
        widget = MagicMock()
        self._exec_click_path(widget)
        widget.set_text.assert_called_once_with("x")
        assert capsys.readouterr().out.strip() == "OK"

    def test_redraw_error_is_not_swallowed(self, monkeypatch, capsys):
        import types

        udisplay = types.ModuleType("udisplay")

        def update(_dt):
            raise RuntimeError("redraw failed")

        udisplay.update = update
        self._install_fakes(monkeypatch, udisplay)
        with pytest.raises(RuntimeError, match="redraw failed"):
            self._exec_click_path(MagicMock())
        assert "OK" not in capsys.readouterr().out

    def test_timers_paused_while_click_handler_runs(self, monkeypatch):
        lvgl = self._install_fakes(monkeypatch, None)
        widget = MagicMock()
        seen = []
        widget.set_text.side_effect = lambda *_: seen.append(list(lvgl.timer_states))
        self._exec_click_path(widget)
        assert seen == [[False]]
        assert lvgl.timer_states == [False, True]

    def test_timers_reenabled_when_click_handler_fails(self, monkeypatch):
        lvgl = self._install_fakes(monkeypatch, None)
        widget = MagicMock()
        widget.set_text.side_effect = RuntimeError("handler failed")
        with pytest.raises(RuntimeError, match="handler failed"):
            self._exec_click_path(widget)
        assert lvgl.timer_states == [False, True]


class TestBoardTouch:
    """Board touch goes through the shared virtual pointer, installed once per boot."""

    @staticmethod
    def _fake_board(mock_repl, results, tree=None):
        state = {"installed": False, "scripts": []}

        def exec_raw(dev, script, baud, timeout=10):
            state["scripts"].append(script)
            if "screen_active') else '8'" in script:
                return "9"
            if "_devtools_touch = type(" in script:
                state["installed"] = True
                return "OK"
            if "_devtools_ns" in script:
                return "OK"
            if "_devtools_run" in script:
                if not state["installed"]:
                    return json.dumps({"install": True})
                return json.dumps(results.pop(0))
            return tree
        mock_repl.exec_raw.side_effect = exec_raw
        return state

    def test_first_touch_installs_the_module_then_retries(self, mock_repl):
        state = self._fake_board(mock_repl, [{"ok": True, "duration_ms": 300}])

        result = CliRunner().invoke(ui_control, ['{"action":"touch","points":[[1,2,0],[3,4,300]]}'])

        assert result.exit_code == 0
        assert json.loads(result.output) == {"duration_ms": 300, "ok": True}
        requests = [s for s in state["scripts"] if "_devtools_run" in s]
        assert len(requests) == 2
        assert "[[1, 2, 0], [3, 4, 300]]" in requests[-1]

    def test_install_chunks_stay_small(self):
        from disco_lib.commands.ui import _TOUCH_CHUNK_LIMIT, _touch_chunks

        chunks = _touch_chunks()
        assert "class VirtualPointer" in "".join(chunks)
        assert '"""' not in "".join(chunks)
        assert max(len(chunk) for chunk in chunks) < 2 * _TOUCH_CHUNK_LIMIT

    @pytest.mark.parametrize("points", ["[]", "[[1,2]]", '[[1,2,"0"]]', "[[1,2,true]]", '"x"'])
    def test_invalid_points_are_rejected_before_reaching_the_board(self, mock_repl, points):
        state = self._fake_board(mock_repl, [])

        result = CliRunner().invoke(ui_control, ['{"action":"touch","points":%s}' % points])

        assert json.loads(result.output)["ok"] is False
        assert not [s for s in state["scripts"] if "_devtools" in s]

    def test_coordinate_click_taps_without_reading_the_tree(self, mock_repl):
        state = self._fake_board(mock_repl, [{"ok": True, "duration_ms": 50}])
        state["installed"] = True

        result = CliRunner().invoke(ui_control, ['{"action":"click","x":145,"y":760}'])

        assert json.loads(result.output)["ok"] is True
        assert [s for s in state["scripts"] if "_devtools_run" in s][-1].count("tap_points(145, 760)") == 1
        assert not [s for s in state["scripts"] if "_emit(" in s]

    def test_click_by_text_aims_at_the_selected_widget(self, mock_repl):
        tree = "\n".join([
            '{"path": [], "type": "obj"}',
            '{"path": [0], "type": "button"}',
            '{"path": [0, 0], "type": "label", "text": "Start"}',
        ])
        state = self._fake_board(mock_repl, [{"ok": True, "duration_ms": 50,
                                              "tapped": {"x": 60, "y": 30, "hit": {"path": [0]}}}], tree)
        state["installed"] = True

        result = CliRunner().invoke(ui_control, ['{"action":"click","text":"Start"}'])

        response = json.loads(result.output)
        assert response["ok"] is True
        assert response["widget"]["path"] == [0]
        aim_script = [s for s in state["scripts"] if "_devtools_run" in s][-1]
        assert "touch.aim(widget)" in aim_script and "for index in [0]:" in aim_script
