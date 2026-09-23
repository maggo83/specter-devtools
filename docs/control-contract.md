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
| `find` | `text` or `path`; simulator also `x` + `y`; optional `layer` | Widget summary. |
| `click` | `text` or `path`; simulator also `x` + `y`; optional `layer` | Selected widget and actual event target. |
| `write_text` | `text`, plus `path` or textarea index `target`; optional `layer` | Updated textarea summary. |
| `get_state` | none | Simulator only: application device and navigation state. |
| `navigate` | menu `target` or `back` | Simulator only: updated application state. |
| `set_state` | public `attr`, JSON `value` | Simulator only: state update and redraw. |

Tree paths are zero-based integer arrays such as `[0, 1, 2]`, valid only for the current snapshot; navigation, animation, or rebuilds can change them. Prefer unique text; use paths for icon-only controls.

Target differences, discoverable through `capabilities`:

- The simulator supports text, path, and coordinate selectors, and application actions.
- The F469 supports text and path selectors. Its tree omits geometry to save MicroPython heap, so coordinate selection is unavailable, and application actions return an explicit unsupported-action error.

## Transports

- `simulator`: `simulator/sim_control` is frozen into the Unix simulator only and serves `{"action":"control","request":...}` over TCP port 9876 when the simulator starts with `--control`. Screenshots use f469-disco's `SDL.screenshot`, which has SDL convert the render target to a raw 16-bit RGB565 file (host byte order). Correct colors need its fix (branch `fix/sdl-screenshot-rgba32` of `maggo83/f469-disco_disco_tool`) until [miketlk/f469-disco#1](https://github.com/miketlk/f469-disco/pull/1) and its follow-up [#3](https://github.com/miketlk/f469-disco/pull/3) are merged.
- `f469`: `f469/disco ui control` injects short generic LVGL scripts through the raw MicroPython REPL; nothing is frozen or persisted on the device. Screenshots read the display framebuffer at `0xC0000000` (480×800, ARGB8888, the LTDC layer format) through OpenOCD while the CPU is briefly halted.

The client converts both to PNG with the same response shape; simulator PNGs carry only 16-bit color precision.

## Visual Validation

After every state-changing input, capture a screenshot and treat it as the source of truth. Trees and command responses can include hidden, disabled, stale, or mid-animation widgets. Check the `top` layer for overlays before acting on the screen beneath. On hardware, allow about 1.2 seconds after each input for transitions to finish before the next request.
