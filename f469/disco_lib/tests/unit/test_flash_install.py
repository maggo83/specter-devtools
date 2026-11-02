"""Tests for the combined internal-flash and QSPI installation command."""

import pytest

from disco_lib import console
from disco_lib.commands import flash


def test_qspi_preflight_leaves_board_halted_for_programming(
    tmp_path,
    monkeypatch,
):
    qspi = tmp_path / "qspi.img"
    qspi.write_bytes(b"qspi")
    events = []

    class FakeOCD:
        def ensure_running(self):
            class Context:
                def __enter__(self):
                    events.append("connect")

                def __exit__(self, *_args):
                    events.append("disconnect")

            return Context()

    ocd = FakeOCD()
    monkeypatch.setattr(flash, "get_ocd", lambda: ocd)
    monkeypatch.setattr(
        flash.flash_backend,
        "probe_qspi",
        lambda received: events.append(("probe", received))
        or {"name": "qspi", "size": 4},
    )
    monkeypatch.setattr(
        flash.cpu_backend,
        "reset_run",
        lambda _ocd: events.append("reset"),
    )

    assert flash._preflight_qspi_image(str(qspi)) == {
        "name": "qspi",
        "size": 4,
    }
    assert events == ["connect", ("probe", ocd), "disconnect"]


def test_install_preflights_before_programming_and_resets_only_after_qspi(
    tmp_path,
    monkeypatch,
):
    firmware = tmp_path / "firmware.bin"
    qspi = tmp_path / "qspi.img"
    firmware.write_bytes(b"firmware")
    qspi.write_bytes(b"qspi")
    events = []

    monkeypatch.setattr(
        flash,
        "_preflight_qspi_image",
        lambda path: events.append(("preflight", path)),
    )

    def program_firmware(file, addr, force, verify, reset, timeout):
        events.append(
            ("firmware", file, addr, force, verify, reset, timeout)
        )

    monkeypatch.setattr(flash, "flash_program", program_firmware)
    monkeypatch.setattr(
        flash,
        "flash_qspi_program",
        lambda file, timeout, reset: events.append(
            ("qspi", file, timeout, reset)
        ),
    )
    monkeypatch.setattr(
        flash,
        "_reset_board",
        lambda: events.append(("reset",)),
    )

    flash.flash_install(
        str(firmware),
        str(qspi),
        None,
        False,
        11,
        22,
    )

    assert events == [
        ("preflight", str(qspi)),
        ("firmware", str(firmware), None, False, True, False, 11),
        ("qspi", str(qspi), 22, False),
        ("reset",),
    ]


def test_install_does_not_program_internal_flash_when_preflight_fails(
    tmp_path,
    monkeypatch,
):
    firmware = tmp_path / "firmware.bin"
    qspi = tmp_path / "qspi.img"
    firmware.write_bytes(b"firmware")
    qspi.write_bytes(b"qspi")
    programmed = []

    def reject_qspi(_path):
        raise console.CliError("QSPI image size mismatch")

    monkeypatch.setattr(flash, "_preflight_qspi_image", reject_qspi)
    monkeypatch.setattr(
        flash,
        "flash_program",
        lambda *_args, **_kwargs: programmed.append(True),
    )

    with pytest.raises(console.CliError, match="size mismatch"):
        flash.flash_install(
            str(firmware),
            str(qspi),
            None,
            False,
            0,
            0,
        )

    assert programmed == []


def test_install_reports_partial_state_when_qspi_programming_fails(
    tmp_path,
    monkeypatch,
):
    firmware = tmp_path / "firmware.bin"
    qspi = tmp_path / "qspi.img"
    firmware.write_bytes(b"firmware")
    qspi.write_bytes(b"qspi")

    monkeypatch.setattr(flash, "_preflight_qspi_image", lambda _path: None)
    monkeypatch.setattr(flash, "flash_program", lambda *_args, **_kwargs: True)

    def fail_qspi(_file, _timeout, reset):
        assert reset is False
        raise console.CliError("verification failed")

    monkeypatch.setattr(flash, "flash_qspi_program", fail_qspi)
    reset = []
    monkeypatch.setattr(flash, "_reset_board", lambda: reset.append(True))

    with pytest.raises(
        console.CliError,
        match="Internal firmware was programmed, but QSPI installation failed",
    ):
        flash.flash_install(
            str(firmware),
            str(qspi),
            None,
            False,
            0,
            0,
        )
    assert reset == []


def test_flash_program_uses_smart_verification_for_sparse_image(
    tmp_path,
    monkeypatch,
):
    firmware = tmp_path / "firmware.bin"
    firmware.write_bytes(
        b"c" * 4096 + b"\x00" * 4096 + b"d" * 4096
    )
    events = []

    class FakeOCD:
        def ensure_running(self):
            class Context:
                def __enter__(self):
                    return None

                def __exit__(self, *_args):
                    return None

            return Context()

    monkeypatch.setattr(flash, "get_ocd", lambda: FakeOCD())
    monkeypatch.setattr(
        flash.flash_backend,
        "program_firmware",
        lambda _ocd, file, addr, verify, reset, timeout: events.append(
            ("program", file, addr, verify, reset, timeout)
        ) or True,
    )
    monkeypatch.setattr(
        flash.flash_backend,
        "verify_regions",
        lambda _ocd, file, addr, resume: events.append(
            ("verify", file, addr, resume)
        ) or {"code": True, "fs": None},
    )
    monkeypatch.setattr(
        flash.cpu_backend,
        "reset_run",
        lambda _ocd: events.append(("reset",)),
    )

    result = flash.flash_program(
        str(firmware),
        "0x08000000",
        False,
        verify=True,
        reset=False,
        timeout=17,
    )

    assert result is None
    assert events == [
        (
            "program",
            str(firmware),
            0x08000000,
            False,
            False,
            17,
        ),
        ("verify", str(firmware), 0x08000000, False),
    ]


def test_flash_program_resets_after_smart_verification_error(
    tmp_path,
    monkeypatch,
):
    firmware = tmp_path / "firmware.bin"
    firmware.write_bytes(
        b"c" * 4096 + b"\x00" * 4096 + b"d" * 4096
    )
    reset = []

    class FakeOCD:
        def ensure_running(self):
            class Context:
                def __enter__(self):
                    return None

                def __exit__(self, *_args):
                    return None

            return Context()

    monkeypatch.setattr(flash, "get_ocd", lambda: FakeOCD())
    monkeypatch.setattr(
        flash.flash_backend,
        "program_firmware",
        lambda *_args, **_kwargs: True,
    )

    def fail_verification(*_args, **_kwargs):
        raise console.CliError("OpenOCD connection failed")

    monkeypatch.setattr(
        flash.flash_backend,
        "verify_regions",
        fail_verification,
    )
    monkeypatch.setattr(
        flash.cpu_backend,
        "reset_run",
        lambda _ocd: reset.append(True),
    )

    with pytest.raises(console.CliError, match="connection failed"):
        flash.flash_program(
            str(firmware),
            "0x08000000",
            False,
            verify=True,
            reset=True,
            timeout=17,
        )

    assert reset == [True]
