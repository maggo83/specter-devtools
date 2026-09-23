import json
from pathlib import Path

import pytest

from specter_devtools import cli
from specter_devtools.artifacts import capture, visible_labels
from specter_devtools.png import save_rgb565_png
from specter_devtools.targets import DEFAULT_F469_DISCO, F469Target, TargetError, make_target


class Result:
    returncode = 0
    stdout = '{"ok": true}\n'
    stderr = ""


def test_save_rgb565_png_writes_a_valid_png(tmp_path):
    output = tmp_path / "image.png"

    save_rgb565_png(b"\x00\xf8", output, 1, 1)

    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_visible_labels_walks_canonical_tree():
    tree = {
        "text": None,
        "children": [
            {"text": "Settings", "children": []},
            {"text": None, "children": [{"text": "Back", "children": []}]},
        ],
    }

    assert visible_labels(tree) == ["Settings", "Back"]


def test_bundled_f469_disco_launcher_exists():
    assert DEFAULT_F469_DISCO == Path(__file__).resolve().parents[1] / "f469" / "disco"
    assert DEFAULT_F469_DISCO.exists()


def test_f469_target_sends_ui_control_through_disco(monkeypatch, tmp_path):
    launcher = tmp_path / "disco"
    launcher.touch()
    commands = []
    monkeypatch.setattr(
        "specter_devtools.targets.subprocess.run",
        lambda command, **kwargs: commands.append(command) or Result(),
    )

    F469Target(launcher).request({"action": "capabilities"})

    assert commands == [[str(launcher.resolve()), "ui", "control", '{"action":"capabilities"}']]


def test_f469_target_rejects_a_missing_launcher(tmp_path):
    with pytest.raises(TargetError, match="not found"):
        F469Target(tmp_path / "missing")


def test_esp32_p4_is_reserved_but_not_implemented():
    with pytest.raises(TargetError, match="not implemented yet"):
        make_target("esp32-p4")


def test_board_command_passes_raw_arguments_to_disco(monkeypatch, tmp_path):
    launcher = tmp_path / "disco"
    launcher.touch()
    commands = []
    monkeypatch.setattr(
        "specter_devtools.targets.subprocess.run",
        lambda command, **kwargs: commands.append(command) or Result(),
    )

    code = cli.main(["--target", "f469", "--disco", str(launcher), "board", "flash", "analyze", "x.bin"])

    assert code == 0
    assert commands == [[str(launcher.resolve()), "flash", "analyze", "x.bin"]]


def test_board_command_is_unavailable_for_the_simulator(capsys):
    assert cli.main(["--target", "simulator", "board", "flash", "info"]) == 1
    assert "unavailable for the simulator" in json.loads(capsys.readouterr().out)["error"]


class FakeTarget:
    def request(self, request):
        assert request == {"action": "tree"}
        return {
            "ok": True,
            "tree": {
                "layer": "screen",
                "root": {"text": None, "children": [{"text": "Settings", "children": []}]},
            },
        }

    def screenshot(self, output):
        output.write_bytes(b"png")
        return {"ok": True, "file": str(output), "width": 480, "height": 800, "format": "PNG"}


def test_capture_writes_the_same_artifacts_for_any_target(tmp_path):
    result = capture(FakeTarget(), tmp_path / "capture")

    assert result["ok"] is True
    assert result["label_count"] == 1
    assert (tmp_path / "capture" / "tree.json").exists()
    assert (tmp_path / "capture" / "labels.txt").read_text() == "Settings\n"
    assert (tmp_path / "capture" / "screenshot.png").read_bytes() == b"png"
