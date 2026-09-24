# Control Contract

`specter-devtools` sends the same UI request to every target; only `--target` changes. Every response is JSON with an `ok` field.

```bash
specter-devtools --target simulator request '{"action":"click","text":"Manage Device"}'
specter-devtools --target f469 request '{"action":"click","text":"Manage Device"}'
```

`capture` writes `screenshot.png`, `tree.json`, and `labels.txt` for any target:

```bash
specter-devtools --target f469 capture /tmp/board-capture
```

## Requests

`request` accepts one JSON object. UI selectors accept `layer`: `screen` (default) or `top` for modals and overlays.

| Action | Request fields | Result |
|---|---|---|
| `capabilities` | none | Supported UI and application features. |
| `tree` | optional `layer` | Canonical widget tree rooted at `tree.root`. |
| `find` | `text`, `path`, or `x` + `y`; optional `layer` | Widget summary; `x` + `y` uses LVGL's own hit-test. |
| `click` | `text`, `path`, or `x` + `y`; optional `layer` | A 50 ms tap through the virtual pointer (see below); `tapped` reports the point and the widget LVGL hit. |
| `touch` | `points`: `[[x, y, ms], ...]` | Presses at the first point, follows the points, releases after the last; returns `duration_ms` once released. |
| `write_text` | `text`, plus `path` or textarea index `target`; optional `layer` | Updated textarea summary. |
| `get_state` | none | MockUI device and navigation state. |
| `navigate` | menu `target` or `back` | Updated MockUI state. |
| `set_state` | public `attr`, JSON `value` | State update and redraw. |

Tree paths are zero-based integer arrays such as `[0, 1, 2]`, valid only for the current snapshot; navigation, animation, or rebuilds can change them. Prefer unique text; use paths for icon-only controls.

## Touch

Clicks and gestures use a virtual LVGL pointer next to the real touchscreen or mouse. LVGL reads it like a finger: it does its own hit-testing and delivers press, move, release, click, scroll, and long-press to the app inside its normal update. Sliders, scrolling, and long presses therefore behave as they do for a user.

- `click` by `text` or `path` taps the centre of the widget, or of its nearest ancestor that accepts presses. If LVGL's hit-test shows something else would receive the touch there, for example an overlay or an off-screen position, the click fails instead of tapping it.
- `click` by `x` + `y` taps there unconditionally.
- `touch` replays timed samples, for example a drag: `[[209, 440, 0], [300, 440, 300], [430, 440, 600]]`. Each sample is reported at least once, so short taps are never lost. Times must not decrease, and only one gesture runs at a time.

The device-side code is `simulator/sim_control/touch.py`. The simulator freezes it; the F469 receives it, together with `app_control.py`, over the REPL once per boot, in small chunks.

Target differences, discoverable through `capabilities`:

- Both targets support text, path, and coordinate selectors, and `touch`.
- Application actions (`get_state`, `navigate`, `set_state`) need MockUI: both targets run the shared `simulator/sim_control/app_control.py` against its `SpecterGui`. On the F469 that is the `scr` object MockUI's `main.py` leaves in the REPL; `capabilities` reports `application: false` without it. Navigation and state changes run with LVGL timers paused, because on the board they run outside LVGL's update.

## Transports

- `simulator`: `simulator/sim_control` is frozen into the Unix simulator only and serves `{"action":"control","request":...}` over TCP port 9876 when the simulator starts with `--control`. Screenshots use f469-disco's `SDL.screenshot`, which has SDL convert the render target to a raw 16-bit RGB565 file (host byte order). Correct colors need its fix (branch `fix/sdl-screenshot-rgba32` of `maggo83/f469-disco_disco_tool`) until [miketlk/f469-disco#1](https://github.com/miketlk/f469-disco/pull/1) and its follow-up [#3](https://github.com/miketlk/f469-disco/pull/3) are merged.
- `f469`: `f469/disco ui control` injects short generic LVGL scripts through the raw MicroPython REPL; only the touch module stays in RAM until the next reset. Screenshots read the display framebuffer at `0xC0000000` (480×800, ARGB8888, the LTDC layer format) through OpenOCD while the CPU is briefly halted.

The client converts both to PNG with the same response shape; simulator PNGs carry only 16-bit color precision.

## Visual Validation

After every state-changing input, capture a screenshot and treat it as the source of truth. Trees and command responses can include hidden, disabled, stale, or mid-animation widgets. Check the `top` layer for overlays before acting on the screen beneath. On hardware, allow about 1.2 seconds after each input for transitions to finish before the next request.
