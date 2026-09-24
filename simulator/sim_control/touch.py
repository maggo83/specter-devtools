"""Virtual touch input for LVGL, shared by the simulator and boards.

Runs on the device. Gestures go through a virtual LVGL pointer, so LVGL does
its own hit-testing and runs handlers inside its update, like a real finger.
Boards receive this file's source over the REPL; the simulator freezes it.
"""
import lvgl as lv
import utime

TAP_MS = 50


class VirtualPointer:
    """Replays timed samples [x, y, ms]: pressed from the first to the last."""

    def __init__(self):
        self._samples = []
        self._start = 0
        self._x = 0
        self._y = 0
        self._pressed = False
        self.indev = lv.indev_create()
        self.indev.set_type(lv.INDEV_TYPE.POINTER)
        self.indev.set_read_cb(self._read)

    def play(self, points):
        """Start a gesture; returns its duration in ms."""
        if self.busy():
            raise ValueError("A gesture is still running")
        if not points:
            raise ValueError("A gesture needs at least one point")
        samples = []
        for point in points:
            x, y, ms = int(point[0]), int(point[1]), int(point[2])
            if samples and ms < samples[-1][2]:
                raise ValueError("Gesture times must not decrease")
            samples.append((x, y, ms))
        # Start first: on boards a scheduled read can run between these lines.
        self._start = utime.ticks_ms()
        self._samples = samples
        return samples[-1][2]

    def busy(self):
        return bool(self._samples) or self._pressed

    def _read(self, indev, data):
        if self._samples:
            elapsed = utime.ticks_diff(utime.ticks_ms(), self._start)
            if not self._pressed:
                self._x, self._y, _ = self._samples.pop(0)
            while self._samples and self._samples[0][2] <= elapsed:
                self._x, self._y, _ = self._samples.pop(0)
            self._pressed = True
        else:
            self._pressed = False
        data.point.x = self._x
        data.point.y = self._y
        data.state = lv.INDEV_STATE.PRESSED if self._pressed else lv.INDEV_STATE.RELEASED


def _layers():
    display = lv.display_get_default()
    return (("sys", display.get_layer_sys()), ("top", display.get_layer_top()),
            ("screen", lv.screen_active()), ("bottom", display.get_layer_bottom()))


def hit(x, y):
    """Return the widget a finger at (x, y) would press, in LVGL's layer order."""
    point = lv.point_t()
    point.x = int(x)
    point.y = int(y)
    for _, layer in _layers():
        found = lv.indev_search_obj(layer, point)
        if found is not None:
            return found
    return None


def centre(widget):
    """Return the screen coordinates of a widget's centre."""
    area = lv.area_t()
    widget.get_coords(area)
    return (area.x1 + area.x2) // 2, (area.y1 + area.y2) // 2


def contains(ancestor, widget):
    """Return whether widget is ancestor or one of its descendants."""
    while widget is not None:
        if widget == ancestor:
            return True
        widget = widget.get_parent()
    return False


def press_target(widget):
    """Return the widget or its nearest ancestor that accepts presses."""
    while widget is not None and not widget.has_flag(lv.obj.FLAG.CLICKABLE):
        widget = widget.get_parent()
    return widget


def aim(widget):
    """Return (x, y, hit) to tap widget like a finger; ValueError if unreachable."""
    target = press_target(widget)
    if target is None:
        raise ValueError("Widget does not accept presses")
    x, y = centre(target)
    found = hit(x, y)
    if found is None or not contains(target, found):
        raise ValueError("Widget is covered or off-screen at (%d, %d)" % (x, y))
    return x, y, found


def tap_points(x, y, ms=TAP_MS):
    return [[x, y, 0], [x, y, ms]]


def describe(widget):
    """Return the layer, tree path, type, and text of a widget, or None."""
    if widget is None:
        return None
    path = []
    current = widget
    parent = current.get_parent()
    while parent is not None:
        path.insert(0, current.get_index())
        current = parent
        parent = current.get_parent()
    layer = None
    for name, root in _layers():
        if root == current:
            layer = name
    try:
        text = widget.get_text()
    except Exception:
        text = None
    return {"layer": layer, "path": path, "type": type(widget).__name__, "text": text}
