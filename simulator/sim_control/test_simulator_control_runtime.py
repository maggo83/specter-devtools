import sys
import types
from pathlib import Path


sys.modules.setdefault("lvgl", types.SimpleNamespace())
sys.path.insert(0, str(Path(__file__).parent.parent))

from sim_control import simulator_control_runtime as control


class FakeEvent:
    CLICKED = "clicked"


class FakeHidden:
    HIDDEN = "hidden"


class FakeObjectType:
    FLAG = FakeHidden()


class FakeLv:
    EVENT = FakeEvent()
    obj = FakeObjectType()


class Widget:
    def __init__(self, name, text=None, x=0, y=0, width=100, height=40, children=None):
        self.name = name
        self._text = text
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.children = children or []
        self.parent = None
        self.events = []
        for child in self.children:
            child.parent = self

    def get_child_count(self):
        return len(self.children)

    def get_child(self, index):
        return self.children[index]

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def get_text(self):
        if self._text is None:
            raise AttributeError("no text")
        return self._text

    def set_text(self, text):
        self._text = text

    def get_parent(self):
        return self.parent

    def send_event(self, event, data):
        self.events.append((event, data))

    def has_flag(self, flag):
        return False


class button(Widget):
    pass


class label(Widget):
    pass


class textarea(Widget):
    pass


def _install_screen(monkeypatch):
    name = textarea("textarea", text="old", x=10, y=70)
    start = label("label", text="Start", x=5, y=5)
    start_button = button("button", x=10, y=10, children=[start])
    screen = Widget("screen", width=480, height=800, children=[start_button, name])
    top = Widget("top", width=480, height=800)

    class Display:
        def get_layer_top(self):
            return top

    fake_lv = FakeLv()
    fake_lv.screen_active = lambda: screen
    fake_lv.display_get_default = lambda: Display()
    monkeypatch.setattr(control, "lv", fake_lv)
    return screen, start_button, name


def test_tree_includes_canonical_paths_and_geometry(monkeypatch):
    screen, _, _ = _install_screen(monkeypatch)

    result = control.get_tree()

    assert result["layer"] == "screen"
    assert result["root"]["path"] == []
    assert result["root"]["children"][0]["path"] == [0]
    assert result["root"]["children"][0]["children"][0]["path"] == [0, 0]
    assert result["root"]["width"] == screen.width


class RecordingPointer:
    def __init__(self):
        self.gestures = []

    def play(self, points):
        self.gestures.append(points)
        return points[-1][2]


def _install_touch(monkeypatch, hit_widget):
    pointer = RecordingPointer()
    monkeypatch.setattr(control, "_pointer", pointer)
    monkeypatch.setattr(control.touch, "hit", lambda x, y: hit_widget)
    monkeypatch.setattr(control.touch, "describe", lambda widget: widget and {
        "layer": "screen", "path": [0], "type": type(widget).__name__, "text": None})
    return pointer


def test_click_by_text_taps_the_widget_centre(monkeypatch):
    _, start_button, _ = _install_screen(monkeypatch)
    pointer = _install_touch(monkeypatch, start_button)
    aimed = []
    monkeypatch.setattr(control.touch, "aim", lambda widget: aimed.append(widget) or (60, 30, start_button))

    result = control.click(text="Start")

    assert result["ok"] is True
    assert aimed == [start_button]
    assert pointer.gestures == [[[60, 30, 0], [60, 30, 50]]]
    assert result["duration_ms"] == 50
    assert result["tapped"]["hit"]["type"] == "button"
    assert start_button.events == []


def test_click_refuses_a_widget_a_finger_cannot_reach(monkeypatch):
    _install_screen(monkeypatch)
    pointer = _install_touch(monkeypatch, None)

    def covered(widget):
        raise ValueError("Widget is covered or off-screen at (60, 30)")

    monkeypatch.setattr(control.touch, "aim", covered)

    assert control.click(text="Start") == {"ok": False, "error": "Widget is covered or off-screen at (60, 30)"}
    assert pointer.gestures == []


def test_click_by_coordinates_taps_there(monkeypatch):
    _, start_button, _ = _install_screen(monkeypatch)
    pointer = _install_touch(monkeypatch, start_button)

    result = control.click(x=16, y=16)

    assert result["ok"] is True
    assert pointer.gestures == [[[16, 16, 0], [16, 16, 50]]]
    assert result["tapped"]["hit"]["path"] == [0]


def test_touch_request_plays_the_given_points(monkeypatch):
    _install_screen(monkeypatch)
    pointer = _install_touch(monkeypatch, None)
    points = [[10, 10, 0], [90, 10, 300]]

    assert control.handle({"action": "touch", "points": points}) == {"ok": True, "duration_ms": 300}
    assert pointer.gestures == [points]


def test_write_text_by_path_updates_textarea(monkeypatch):
    _, _, textarea_widget = _install_screen(monkeypatch)

    result = control.write_text("new", path=[1])

    assert result["ok"] is True
    assert textarea_widget.get_text() == "new"
    assert result["widget"]["path"] == [1]


def test_find_text_keeps_textareas_directly_addressable(monkeypatch):
    _install_screen(monkeypatch)

    result = control.find(text="old")

    assert result["ok"] is True
    assert result["widget"]["type"] == "textarea"
    assert result["widget"]["path"] == [1]


def test_handle_uses_one_json_compatible_request_and_response(monkeypatch):
    _install_screen(monkeypatch)

    result = control.handle({"action": "find", "text": "Start"})

    assert result == {
        "ok": True,
        "layer": "screen",
        "widget": {
            "path": [0],
            "type": "button",
            "x": 10,
            "y": 10,
            "text": None,
        },
    }