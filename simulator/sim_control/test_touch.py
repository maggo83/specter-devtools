import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sim_control import touch


class Clock:
    def __init__(self):
        self.now = 0

    def ticks_ms(self):
        return self.now


class Indev:
    def __init__(self):
        self.read_cb = None

    def set_type(self, kind):
        self.kind = kind

    def set_read_cb(self, callback):
        self.read_cb = callback


class Widget:
    def __init__(self, name, area, clickable=False, children=()):
        self.name = name
        self.area = area
        self.clickable = clickable
        self.children = list(children)
        self.parent = None
        for child in self.children:
            child.parent = self

    def get_parent(self):
        return self.parent

    def get_index(self):
        return self.parent.children.index(self)

    def get_coords(self, area):
        area.x1, area.y1, area.x2, area.y2 = self.area

    def has_flag(self, flag):
        return self.clickable

    def get_text(self):
        raise AttributeError("no text")


def _install(monkeypatch, top_children=()):
    button = Widget("button", (100, 100, 199, 149), clickable=True,
                    children=[Widget("label", (120, 110, 179, 139))])
    screen = Widget("screen", (0, 0, 479, 799), children=[button])
    top = Widget("top", (0, 0, 479, 799), children=list(top_children))
    empty = Widget("empty", (0, 0, 479, 799))

    def search(root, point):
        def walk(widget):
            x1, y1, x2, y2 = widget.area
            if not (x1 <= point.x <= x2 and y1 <= point.y <= y2):
                return None
            for child in reversed(widget.children):
                found = walk(child)
                if found is not None:
                    return found
            return widget if widget.clickable else None
        return walk(root)

    display = types.SimpleNamespace(
        get_layer_sys=lambda: empty, get_layer_top=lambda: top,
        get_layer_bottom=lambda: empty,
    )
    area = lambda: types.SimpleNamespace(x1=0, y1=0, x2=0, y2=0)
    fake_lv = types.SimpleNamespace(
        indev_create=Indev,
        INDEV_TYPE=types.SimpleNamespace(POINTER="pointer"),
        INDEV_STATE=types.SimpleNamespace(PRESSED="pressed", RELEASED="released"),
        obj=types.SimpleNamespace(FLAG=types.SimpleNamespace(CLICKABLE="clickable")),
        display_get_default=lambda: display, screen_active=lambda: screen,
        point_t=lambda: types.SimpleNamespace(x=0, y=0), area_t=area,
        indev_search_obj=search,
    )
    clock = Clock()
    monkeypatch.setattr(touch, "lv", fake_lv)
    monkeypatch.setattr(touch, "utime", types.SimpleNamespace(
        ticks_ms=clock.ticks_ms, ticks_diff=lambda a, b: a - b))
    return clock, button


def _read(pointer):
    data = types.SimpleNamespace(point=types.SimpleNamespace(x=None, y=None), state=None)
    pointer.indev.read_cb(pointer.indev, data)
    return data.point.x, data.point.y, data.state


def test_tap_is_pressed_at_least_once_even_when_read_late(monkeypatch):
    clock, _ = _install(monkeypatch)
    pointer = touch.VirtualPointer()
    pointer.play(touch.tap_points(10, 20))

    clock.now = 500
    assert _read(pointer) == (10, 20, "pressed")
    assert _read(pointer) == (10, 20, "released")
    assert not pointer.busy()


def test_drag_follows_the_clock_and_releases_at_the_end(monkeypatch):
    clock, _ = _install(monkeypatch)
    pointer = touch.VirtualPointer()
    assert pointer.play([[0, 0, 0], [50, 0, 100], [100, 0, 200]]) == 200

    assert _read(pointer) == (0, 0, "pressed")
    clock.now = 60
    assert _read(pointer) == (0, 0, "pressed")
    clock.now = 110
    assert _read(pointer) == (50, 0, "pressed")
    clock.now = 250
    assert _read(pointer) == (100, 0, "pressed")
    assert pointer.busy()
    assert _read(pointer) == (100, 0, "released")
    assert not pointer.busy()


@pytest.mark.parametrize("points", [[], [[0, 0, 100], [0, 0, 50]]])
def test_invalid_gestures_are_rejected(monkeypatch, points):
    _install(monkeypatch)
    with pytest.raises(ValueError):
        touch.VirtualPointer().play(points)


def test_overlapping_gestures_are_rejected(monkeypatch):
    _install(monkeypatch)
    pointer = touch.VirtualPointer()
    pointer.play(touch.tap_points(1, 1))
    with pytest.raises(ValueError, match="still running"):
        pointer.play(touch.tap_points(2, 2))


def test_aim_taps_the_clickable_parent_of_a_label(monkeypatch):
    _, button = _install(monkeypatch)
    x, y, found = touch.aim(button.children[0])

    assert (x, y) == (149, 124)
    assert found is button
    assert touch.describe(found) == {"layer": "screen", "path": [0], "type": "Widget", "text": None}


def test_aim_refuses_a_covered_widget(monkeypatch):
    overlay = Widget("overlay", (0, 0, 479, 799), clickable=True)
    _, button = _install(monkeypatch, top_children=[overlay])

    with pytest.raises(ValueError, match="covered or off-screen"):
        touch.aim(button)
    assert touch.describe(touch.hit(149, 124))["layer"] == "top"
