"""LVGL remote-control commands."""

import json as json_mod
import os
import struct
import tempfile

import click

from ..ocd_provider import get_ocd
from .. import cpu as cpu_backend
from .. import memory
from ..serial import SerialDevice
from .. import repl as repl_backend

_ser = SerialDevice()

# MicroPython script: check LVGL version (runs on device)
_LVGL_VERSION_CHECK = "import lvgl as lv; print('9' if hasattr(lv,'screen_active') else '8')"

# MicroPython script: walk widget tree and print it (runs on device)
_TREE_SCRIPT = """\
import lvgl as lv
import json

def _clsname(obj):
    c = obj.__class__.__name__
    return c if c != 'lv_obj' else 'obj'

def _text(obj):
    try:
        return obj.get_text()
    except Exception:
        return None

def _walk(obj, depth, idx, out, as_dict):
    cls = _clsname(obj)
    cc = obj.get_child_count()
    txt = _text(obj)
    if as_dict:
        node = {'type': cls, 'children': []}
        if txt is not None:
            node['text'] = txt
        for i in range(cc):
            _walk(obj.get_child(i), depth + 1, i, node['children'], True)
        out.append(node)
    else:
        indent = '  ' * depth
        if txt is not None:
            print('%s[%d] %s "%s"' % (indent, idx, cls, txt))
        else:
            print('%s[%d] %s cc=%d' % (indent, idx, cls, cc))
        for i in range(cc):
            _walk(obj.get_child(i), depth + 1, i, out, False)

scr = $ROOT
cc = scr.get_child_count()
AS_JSON = $AS_JSON
if AS_JSON:
    tree = []
    for i in range(cc):
        _walk(scr.get_child(i), 0, i, tree, True)
    print(json.dumps(tree))
else:
    for i in range(cc):
        _walk(scr.get_child(i), 0, i, [], False)
"""

# MicroPython script: find widget by label text and click it (runs on device)
_CLICK_SCRIPT = """\
import lvgl as lv

def _find_by_text(obj, target):
    try:
        if obj.get_text() == target:
            return obj
    except Exception:
        pass
    for i in range(obj.get_child_count()):
        r = _find_by_text(obj.get_child(i), target)
        if r is not None:
            return r
    return None

def _clickable(w):
    p = w.get_parent()
    while p is not None:
        if 'button' in p.__class__.__name__:
            return p
        p = p.get_parent()
    return w

scr = $ROOT
w = _find_by_text(scr, $TEXT)
if w is None:
    print('NOT_FOUND')
else:
    target = _clickable(w)
    target.send_event(lv.EVENT.CLICKED, None)
    print('OK')
    try:
        import udisplay
        udisplay.update(30)
    except Exception:
        pass
"""

# MicroPython script: click widget by tree index path (runs on device)
_CLICK_INDEX_SCRIPT = """\
import lvgl as lv
scr = $ROOT
path = $PATH
w = scr
for i in path:
    if i >= w.get_child_count():
        print('INDEX_ERROR:%d:%d' % (i, w.get_child_count()))
        w = None
        break
    w = w.get_child(i)
if w is not None:
    w.send_event(lv.EVENT.CLICKED, None)
    print('OK')
    try:
        import udisplay
        udisplay.update(30)
    except Exception:
        pass
"""

# MicroPython script: find textarea and set text (runs on device)
_WRITE_SCRIPT = """\
import lvgl as lv

def _find_textareas(obj, result):
    if 'textarea' in obj.__class__.__name__:
        result.append(obj)
    for i in range(obj.get_child_count()):
        _find_textareas(obj.get_child(i), result)

scr = lv.screen_active()
tas = []
_find_textareas(scr, tas)
idx = $TARGET
if not tas:
    print('NO_TEXTAREA')
elif idx >= len(tas):
    print('INDEX_OUT_OF_RANGE:%d' % len(tas))
else:
    tas[idx].set_text($TEXT)
    try:
        import udisplay
        udisplay.update(30)
    except Exception:
        pass
    print('OK')
"""


def _root_expr(layer: str) -> str:
    """Return the MicroPython expression for the root widget of *layer*.

    ``screen`` (default) → ``lv.screen_active()``
    ``top``              → ``lv.display_get_default().get_layer_top()``
    """
    if layer == "top":
        return "lv.display_get_default().get_layer_top()"
    return "lv.screen_active()"


def _check_lvgl_version(dev, baud):
    """Verify LVGL 9+ is available on the board."""
    try:
        ver = repl_backend.exec_raw(dev, _LVGL_VERSION_CHECK, baud)
    except RuntimeError as e:
        raise click.ClickException(f"Cannot detect LVGL: {e}")
    ver = ver.strip()
    if ver != "9":
        raise click.ClickException(
            f"Unsupported LVGL version {ver!r} \u2014 disco ui requires LVGL 9+")


# These scripts are injected through raw REPL and are never frozen into
# firmware. They use only generic LVGL APIs and MicroPython's json module.
# Tree nodes are emitted individually so large menus do not exhaust board RAM.
_STREAMED_TREE_SCRIPT = """\
import lvgl as lv
import json

def _text(obj):
    try:
        return obj.get_text()
    except Exception:
        return None

def _emit(obj, path):
    node = {'path': path, 'type': obj.__class__.__name__}
    text = _text(obj)
    if text is not None:
        node['text'] = text
    print(json.dumps(node))
    for i in range(obj.get_child_count()):
        _emit(obj.get_child(i), path + [i])

_emit($ROOT, [])
"""

_CLICK_PATH_SCRIPT = """\
import lvgl as lv
root = $ROOT
widget = root
for index in $PATH:
    widget = widget.get_child(index)
widget.send_event(lv.EVENT.CLICKED, None)
try:
    import udisplay
    for _ in range(12):
        udisplay.update(30)
except Exception:
    pass
print('OK')
"""

_WRITE_PATH_SCRIPT = """\
import lvgl as lv
root = $ROOT
widget = root
for index in $PATH:
    widget = widget.get_child(index)
widget.set_text($TEXT)
try:
    import udisplay
    udisplay.update(30)
except Exception:
    pass
print('OK')
"""


def _parse_streamed_tree(output, layer):
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise click.ClickException("UI tree request returned no response")

    nodes = {}
    for line in lines:
        try:
            node = json_mod.loads(line)
        except json_mod.JSONDecodeError as error:
            raise click.ClickException(
                f"UI tree request returned invalid JSON: {line!r}"
            ) from error
        path = tuple(node.get("path", []))
        node["path"] = list(path)
        node["children"] = []
        nodes[path] = node

    root = nodes.get(())
    if root is None:
        raise click.ClickException("UI tree request did not include a root node")

    for path, node in nodes.items():
        if not path:
            continue
        parent = nodes.get(path[:-1])
        if parent is None:
            raise click.ClickException("UI tree request has an orphaned node")
        parent["children"].append(node)
    return {"layer": layer, "root": root}


def _widget_summary(node):
    return {key: node.get(key) for key in ("path", "type", "x", "y", "text")}


def _node_at_path(root, path):
    node = root
    for index in path:
        if not isinstance(index, int) or index < 0 or index >= len(node["children"]):
            return None
        node = node["children"][index]
    return node


def _find_by_text(node, text, parent=None):
    if node.get("text") == text:
        if "label" in node["type"].lower() and parent is not None:
            return parent
        return node
    for child in node["children"]:
        found = _find_by_text(child, text, node)
        if found is not None:
            return found
    return None


def _select_widget(root, request):
    text = request.get("text")
    path = request.get("path")
    x = request.get("x")
    y = request.get("y")
    selector_count = int(text is not None) + int(path is not None) + int(x is not None or y is not None)
    if selector_count != 1:
        return None, "Provide exactly one selector: text, path, or x+y"
    if (x is None) != (y is None):
        return None, "Provide both x and y"
    if text is not None:
        widget = _find_by_text(root, text)
    elif path is not None:
        widget = _node_at_path(root, path)
    else:
        return None, "Coordinate selection is unavailable on hardware"
    if widget is None:
        return None, "Widget not found"
    return widget, None


def _click_target(root, widget):
    path = widget["path"]
    while path:
        candidate = _node_at_path(root, path)
        if "button" in candidate["type"].lower():
            return candidate
        path = path[:-1]
    return widget


def _textareas(node, result):
    if "textarea" in node["type"].lower():
        result.append(node)
    for child in node["children"]:
        _textareas(child, result)


def _tree_request(dev, layer, baud, timeout):
    script = (
        _STREAMED_TREE_SCRIPT
        .replace("$ROOT", _root_expr(layer))
    )
    try:
        output = repl_backend.exec_raw(dev, script, baud, timeout)
    except RuntimeError as error:
        raise click.ClickException(str(error))
    return _parse_streamed_tree(output, layer)


def _run_path_script(dev, script, baud, timeout, action):
    try:
        output = repl_backend.exec_raw(dev, script, baud, timeout)
    except RuntimeError as error:
        raise click.ClickException(str(error))
    if output.strip().splitlines()[-1:] != ["OK"]:
        raise click.ClickException(f"{action} failed: {output.strip()}")


def _generic_control_request(dev, request, baud, timeout):
    """Handle portable UI control with generic transient LVGL scripts."""
    action = request.get("action")
    if action == "capabilities":
        return {
            "ok": True,
            "ui": {
                "tree": True, "find": True,
                "click": ["text", "path"],
                "write_text": ["path", "textarea_index"],
                "layers": ["screen", "top"],
            },
            "application": False,
        }
    if action in ("get_state", "navigate", "set_state"):
        return {"ok": False, "error": "Unsupported action on hardware: " + action}

    layer = request.get("layer", "screen")
    if layer not in ("screen", "top"):
        return {"ok": False, "error": "Unknown layer: " + str(layer)}
    tree = _tree_request(dev, layer, baud, timeout)
    root = tree["root"]

    if action == "tree":
        return {"ok": True, "tree": tree}
    if action == "find":
        widget, error = _select_widget(root, request)
        return {"ok": False, "error": error} if error else {
            "ok": True, "layer": layer, "widget": _widget_summary(widget)
        }
    if action == "click":
        widget, error = _select_widget(root, request)
        if error:
            return {"ok": False, "error": error}
        target = _click_target(root, widget)
        script = (
            _CLICK_PATH_SCRIPT
            .replace("$ROOT", _root_expr(layer))
            .replace("$PATH", repr(target["path"]))
        )
        _run_path_script(dev, script, baud, timeout, "UI click")
        return {
            "ok": True, "layer": layer,
            "widget": _widget_summary(widget),
            "clicked": _widget_summary(target),
        }
    if action == "write_text":
        path = request.get("path")
        if path is not None:
            textarea = _node_at_path(root, path)
            if textarea is None:
                return {"ok": False, "error": "Widget not found"}
            if "textarea" not in textarea["type"].lower():
                return {"ok": False, "error": "Widget at path is not a textarea"}
        else:
            textareas = []
            _textareas(root, textareas)
            target = request.get("target", 0)
            if not isinstance(target, int) or target < 0 or target >= len(textareas):
                return {"ok": False, "error": "Textarea index out of range"}
            textarea = textareas[target]
        script = (
            _WRITE_PATH_SCRIPT
            .replace("$ROOT", _root_expr(layer))
            .replace("$PATH", repr(textarea["path"]))
            .replace("$TEXT", repr(request.get("text", "")))
        )
        _run_path_script(dev, script, baud, timeout, "UI text write")
        return {"ok": True, "layer": layer, "widget": _widget_summary(textarea)}
    return {"ok": False, "error": "Unknown action: " + str(action)}


@click.group()
def ui():
    """LVGL remote control.

    Low-level commands to inspect and interact with the LVGL widget tree
    running on the board. Requires LVGL 9+ firmware.

    \b
    Commands:
      disco ui screen           # dump widget tree
      disco ui screen --json    # dump as JSON
      disco ui click "1"        # click widget with label "1"
      disco ui write "hello"    # set text on a textarea
    """
    pass


@ui.command("control")
@click.argument("request_json")
@click.option("--timeout", "-t", default=10, type=int, help="Response timeout in seconds")
def ui_control(request_json: str, timeout: int):
    """Send a canonical generic UI-control request to LVGL firmware.

    It sends temporary LVGL-only scripts over raw REPL and never requires an
    application-specific control module in flashed firmware.

    \b
    Examples:
      disco ui control '{"action":"tree"}'
      disco ui control '{"action":"click","text":"Manage Device"}'
      disco ui control '{"action":"write_text","path":[1,0],"text":"Name"}'
    """
    try:
        request = json_mod.loads(request_json)
    except json_mod.JSONDecodeError as error:
        raise click.ClickException(f"Invalid request JSON: {error.msg}") from error
    if not isinstance(request, dict):
        raise click.ClickException("Request JSON must be an object")

    dev = _ser.require_device()
    _check_lvgl_version(dev, _ser.baud)
    response = _generic_control_request(dev, request, _ser.baud, timeout)
    click.echo(json_mod.dumps(response, sort_keys=True))


@ui.command("screen")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON tree")
@click.option("--layer", "layer", default="screen",
              type=click.Choice(["screen", "top"]),
              help="Root layer: 'screen' (default) or 'top' (layer_top overlay)")
@click.option("--timeout", "-t", default=10, type=int, help="Response timeout in seconds")
def ui_screen(as_json: bool, layer: str, timeout: int):
    """Dump the LVGL widget tree.

    Shows each widget's index, type, child count, and text (for labels).
    Use --layer top to inspect overlay widgets (e.g. modal dialogs, tour).

    \b
    Examples:
      disco ui screen
      disco ui screen --json
      disco ui screen --layer top --json
    """
    dev = _ser.require_device()
    _check_lvgl_version(dev, _ser.baud)

    script = (
        _TREE_SCRIPT
        .replace("$ROOT", _root_expr(layer))
        .replace("$AS_JSON", "True" if as_json else "False")
    )
    try:
        output = repl_backend.exec_raw(dev, script, _ser.baud, timeout)
    except RuntimeError as e:
        raise click.ClickException(str(e))

    if as_json:
        try:
            tree = json_mod.loads(output)
            click.echo(json_mod.dumps(tree, indent=2))
        except json_mod.JSONDecodeError:
            click.echo(output)
    else:
        click.echo(output)


@ui.command("click")
@click.argument("text", required=False, default=None)
@click.option("--index", "-i", default=None, help="Dot-separated tree path (e.g. 1.0.1.5.2)")
@click.option("--layer", "layer", default="screen",
              type=click.Choice(["screen", "top"]),
              help="Root layer: 'screen' (default) or 'top' (layer_top overlay)")
@click.option("--timeout", "-t", default=10, type=int, help="Response timeout in seconds")
def ui_click(text: str, index: str, layer: str, timeout: int):
    """Click a widget by its label text or tree position.

    By default, searches depth-first for a widget whose label text matches.
    With --index, navigates the tree by child indices (dot-separated).
    Use --layer top to target overlay widgets (e.g. modal dialogs, tour).

    \b
    Examples:
      disco ui click "1"               # click by label text
      disco ui click "OK"
      disco ui click -i 1.0.1.5.2      # click by tree path
      disco ui click --layer top "Skip"  # click button in overlay
      disco ui click --layer top -i 0.2  # click overlay button by index
    """
    if text is None and index is None:
        raise click.ClickException("Provide TEXT or --index")
    if text is not None and index is not None:
        raise click.ClickException("Provide TEXT or --index, not both")

    dev = _ser.require_device()
    _check_lvgl_version(dev, _ser.baud)

    if index is not None:
        try:
            path = [int(x) for x in index.split(".")]
        except ValueError:
            raise click.ClickException(
                f"Invalid index path: {index!r} (expected dot-separated integers)")
        script = (
            _CLICK_INDEX_SCRIPT
            .replace("$ROOT", _root_expr(layer))
            .replace("$PATH", repr(path))
        )
        label = f"index {index}"
    else:
        script = (
            _CLICK_SCRIPT
            .replace("$ROOT", _root_expr(layer))
            .replace("$TEXT", repr(text))
        )
        label = f"text \"{text}\""

    try:
        output = repl_backend.exec_raw(dev, script, _ser.baud, timeout)
    except RuntimeError as e:
        raise click.ClickException(str(e))

    lines = output.strip().splitlines()
    result = lines[-1] if lines else ""
    if result == "OK":
        if len(lines) > 1:
            click.echo("\n".join(lines[:-1]))
        click.secho(f"Clicked widget at {label}", fg="green")
    elif result == "NOT_FOUND":
        raise click.ClickException(f"No widget found with {label}")
    elif result.startswith("INDEX_ERROR:"):
        parts = result.split(":")
        raise click.ClickException(
            f"Child index {parts[1]} out of range (parent has {parts[2]} children)")
    else:
        raise click.ClickException(f"Unexpected response: {output.strip()}")


@ui.command("write")
@click.argument("text")
@click.option("--target", "-n", default=0, type=int,
              help="Index of textarea to target (default: 0)")
@click.option("--timeout", "-t", default=10, type=int, help="Response timeout in seconds")
def ui_write(text: str, target: int, timeout: int):
    """Set text on a textarea widget.

    Finds textarea widgets on the active screen and sets the text on the
    one at the given index (default: first textarea found).

    \b
    Examples:
      disco ui write "hello"
      disco ui write "secret" --target 1
    """
    dev = _ser.require_device()
    _check_lvgl_version(dev, _ser.baud)

    script = _WRITE_SCRIPT.replace("$TARGET", str(target)).replace("$TEXT", repr(text))
    try:
        output = repl_backend.exec_raw(dev, script, _ser.baud, timeout)
    except RuntimeError as e:
        raise click.ClickException(str(e))

    result = output.strip()
    if result == "OK":
        click.secho(f"Set textarea[{target}] text to \"{text}\"", fg="green")
    elif result == "NO_TEXTAREA":
        raise click.ClickException("No textarea widget found on screen")
    elif result.startswith("INDEX_OUT_OF_RANGE:"):
        count = result.split(":")[1]
        raise click.ClickException(
            f"Textarea index {target} out of range (found {count} textareas)")
    else:
        raise click.ClickException(f"Unexpected response: {result}")


# --- Screenshot support ---

# Framebuffer constants
_FB_ADDR = 0xC0000000
_FB_WIDTH = 480
_FB_HEIGHT = 800
_FB_BPP = 4  # ARGB8888
_FB_SIZE = _FB_WIDTH * _FB_HEIGHT * _FB_BPP  # 1,536,000 bytes


def _raw_to_png(raw_path: str, png_path: str,
                width: int = _FB_WIDTH, height: int = _FB_HEIGHT) -> None:
    """Convert a raw ARGB8888 framebuffer dump to a PNG file.

    The STM32 LTDC stores ARGB8888 as 0xAARRGGBB words.  In little-endian
    memory that's bytes BB GG RR AA.  PNG RGBA expects RR GG BB AA, so we
    swap bytes 0 and 2 (B <-> R) in each pixel.

    Uses only stdlib (struct + zlib).
    """
    import zlib

    with open(raw_path, "rb") as f:
        raw = bytearray(f.read())

    # Swap B and R channels: memory is [B,G,R,A], PNG wants [R,G,B,A]
    raw[0::4], raw[2::4] = raw[2::4], raw[0::4]

    # Build PNG scanlines: filter byte (0 = None) + row pixels
    row_bytes = width * _FB_BPP
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)
        offset = y * row_bytes
        scanlines.extend(raw[offset:offset + row_bytes])

    compressed = zlib.compress(bytes(scanlines))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + body + crc

    with open(png_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        # IHDR: width, height, bit-depth=8, color-type=6 (RGBA)
        f.write(_chunk(b"IHDR", struct.pack(">IIBBBBB",
                                            width, height, 8, 6, 0, 0, 0)))
        f.write(_chunk(b"IDAT", compressed))
        f.write(_chunk(b"IEND", b""))


@ui.command("screenshot")
@click.argument("output", default="/tmp/screenshot.png", type=click.Path())
@click.option("--timeout", "-t", default=30, type=int,
              help="OpenOCD dump timeout in seconds")
def ui_screenshot(output: str, timeout: int):
    """Capture the display framebuffer and save as a PNG file.

    Halts the CPU, reads the LTDC framebuffer from SDRAM, converts the
    raw ARGB8888 data to a PNG, then resumes the CPU.

    \b
    Examples:
      disco ui screenshot
      disco ui screenshot ~/desktop/shot.png
    """
    output = os.path.abspath(output)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".bin")
    os.close(tmp_fd)

    try:
        ocd = get_ocd()
        with ocd.ensure_running(), cpu_backend.halted(ocd):
            click.echo(f"Dumping framebuffer (0x{_FB_ADDR:08x}, "
                       f"{_FB_SIZE:,} bytes)...")
            success = memory.dump_to_file(
                ocd, tmp_path, _FB_ADDR, _FB_SIZE, timeout=timeout)
            if not success:
                raise click.ClickException("Failed to dump framebuffer")

        actual = os.path.getsize(tmp_path)
        if actual != _FB_SIZE:
            raise click.ClickException(
                f"Unexpected dump size: {actual:,} bytes "
                f"(expected {_FB_SIZE:,})")

        _raw_to_png(tmp_path, output)
        click.secho(f"Screenshot saved to {output}", fg="green")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
