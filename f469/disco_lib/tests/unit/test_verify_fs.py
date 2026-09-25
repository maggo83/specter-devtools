"""Smart verify judges the internal filesystem separately from firmware code."""

from click.testing import CliRunner

from disco_lib import flash as flash_backend
from disco_lib.commands.flash import flash_verify
from disco_lib.ocd_provider import reset_ocd, set_ocd

KB = 1024


class FlashOCD:
    """Fake OpenOCD whose dump_image reads from an in-memory flash."""

    def __init__(self, flash: bytes, base: int = 0x08000000):
        self.flash = bytearray(flash)
        self.base = base
        self.halted = False
        self.dumps = []

    def is_running(self):
        return True

    def ensure_running(self):
        from contextlib import nullcontext
        return nullcontext(self)

    def send(self, cmd: str, timeout: float = 2.0) -> str:
        if cmd == "halt":
            self.halted = True
        elif cmd == "resume":
            self.halted = False
        elif cmd.startswith("dump_image"):
            _, path, addr, size = cmd.split()
            start, size = int(addr, 16) - self.base, int(size)
            self.dumps.append((int(addr, 16), size))
            with open(path, "wb") as f:
                f.write(self.flash[start:start + size])
        return ""


def _image():
    """A MockUI-like full image: vector table, gap, filesystem data, gap, firmware."""
    image = bytearray(256 * KB)
    image[0:16 * KB] = b"\x11" * (16 * KB)                    # 0x08000000 code
    image[32 * KB:36 * KB] = b"\x22" * (4 * KB)               # 0x08008000 FAT start
    image[48 * KB:256 * KB] = b"\x33" * (208 * KB)            # FS data + firmware
    return bytes(image)


def _verify(tmp_path, flash, *args):
    path = tmp_path / "mockui.bin"
    path.write_bytes(_image())
    ocd = FlashOCD(flash)
    set_ocd(ocd)
    try:
        result = CliRunner().invoke(flash_verify, [str(path), *args])
    finally:
        reset_ocd()
    return result, ocd


def test_code_regions_are_split_at_the_filesystem_window():
    outside, inside = flash_backend._split_at_fs([(0, 16 * KB), (32 * KB, 36 * KB), (48 * KB, 256 * KB)], 0x08000000)

    assert outside == [(0, 16 * KB), (128 * KB, 256 * KB)]
    assert inside == [(32 * KB, 36 * KB), (48 * KB, 128 * KB)]


def test_passes_when_only_the_filesystem_changed(tmp_path):
    flash = bytearray(_image())
    flash[50 * KB] = 0x7F  # firmware wrote a setting into the filesystem

    result, ocd = _verify(tmp_path, flash)

    assert result.exit_code == 0, result.output
    assert "Filesystem: changed since flashing" in result.output
    assert "PASSED" in result.output
    assert "(auto-detected)" in result.output
    assert not ocd.halted


def test_include_fs_fails_on_a_changed_filesystem(tmp_path):
    flash = bytearray(_image())
    flash[50 * KB] = 0x7F

    result, _ = _verify(tmp_path, flash, "--include-fs")

    assert result.exit_code == 1
    assert "only the filesystem differs" in result.output


def test_fails_when_firmware_code_differs(tmp_path):
    flash = bytearray(_image())
    flash[200 * KB] = 0x00

    result, ocd = _verify(tmp_path, flash)

    assert result.exit_code == 1
    assert "FAILED" in result.output
    assert not ocd.halted


def test_unchanged_image_reports_an_unchanged_filesystem(tmp_path):
    result, _ = _verify(tmp_path, _image())

    assert result.exit_code == 0
    assert "Filesystem: unchanged since flashing" in result.output
