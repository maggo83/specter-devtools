# AGENTS.md

Tooling to drive Specter simulators and hardware boards, mostly maintained and used by AI agents. [README.md](README.md) covers setup and commands; [docs/control-contract.md](docs/control-contract.md) is the reference for requests, responses, and target differences. This file covers what they don't.

## Layout and Runtimes

| Path | Runs on | Contents |
|---|---|---|
| `src/specter_devtools/` | Host, CPython ≥ 3.10 | `specter-devtools` CLI, target adapters (`targets.py`), `capture` and `explore` (`artifacts.py`) |
| `f469/disco_lib/` | Host, CPython | `disco` board tool: OpenOCD, flash, CPU, memory, serial, REPL, YKUSH power, UI control |
| `simulator/sim_control/` | Device, MicroPython | Control runtime: `lvgl`, `utime`, no CPython stdlib |

Device code in `simulator/sim_control/`:

- The simulator freezes the package. specter-playground includes this repo as its `devtools/` submodule and lists each file in its `manifests/unix.py`; a new module needs an entry there.
- The F469 receives only `touch.py` and `app_control.py`, over the raw REPL, once per boot (`_DEVICE_MODULES` in `f469/disco_lib/commands/ui.py`). Each runs in its own namespace, sent in small chunks with docstrings stripped: these two must not import each other or other `sim_control` modules, and must stay lean for a fragmented board heap.
- Host tests stub `lvgl` and `utime` (`simulator/conftest.py`); passing them does not prove the code runs on MicroPython.

## Same Command on Every Target That Can Do It

- **UI control** is target-independent: `request` and its shortcuts (`click`, `tap`, `drag`, ...), `screenshot`, `capture`, `explore`. The same request returns the same JSON shape on every target, always with `ok`. Implement a new UI action on every target that can support it; a target that can't says so in `capabilities` and replies `{"ok": false, "error": ...}`, never with another shape.
- **Application actions** (`get_state`, `navigate`, `set_state`, `translate`) depend on MockUI running, not on the target; `capabilities` reports it as `application`.
- **Hardware operations** (flash, memory, CPU, OpenOCD, serial, power) exist only on boards and go through `board`, which passes its arguments to the board's own tool (`f469/disco`). The simulator has no `board`. When another board gains an equivalent operation, give it the same subcommand and arguments as far as its hardware allows.
- `esp32-p4` is reserved; `make_target` rejects it until it is implemented.

## Rules

- Nothing is installed persistently into production firmware. On the board, only the `touch` and `app_control` modules stay in RAM, until the next reset.
- Clicks and gestures go through the virtual LVGL pointer in `touch.py`, so LVGL does its own hit-testing. Never send events to widgets directly; the older `disco ui click` still does, so build on `ui control`.
- `f469/disco_lib/commands/` calls the `cpu`, `memory`, and `flash` modules; only `commands/ocd.py` may call `ocd.send()` (enforced by `test_architecture.py`).
- RDP level 2 permanently disables debugging; `disco` intentionally cannot set it. Keep it that way.
- The simulator binary and its build stay in the product repository.
- Never soft-reset the board (Ctrl-D, or mpremote's raw REPL with `soft_reset=True`): MockUI's `display.init()` then fails and the board has no UI until a hard reset. `repl reset` does a hard reset.
- `f469/` and `simulator/` contain MIT-licensed code from f469-disco and specter-playground; keep [f469/LICENSE](f469/LICENSE) and [simulator/LICENSE](simulator/LICENSE).

## Hardware Safety

Use the simulator and developer boards only, never a device holding real funds. Ask the user before:

- `board flash` erase, program, lock, or unlock, and anything else that writes flash or option bytes;
- `board power` on, off, or cycle, `board cpu reset`, and `board repl reset`;
- `explore` on a board: it taps action buttons such as *Create* and changes device state.

Never answer `disco`'s confirmation prompts on the user's behalf. Reading is fine: screenshots, trees, `flash analyze`/`verify`/`read`, `mem read`, `doctor`.

## Tests and Verification

```bash
.venv/bin/python -m pytest
```

Runs `tests/`, `simulator/`, and `f469/disco_lib/tests/unit` without hardware. `f469/disco_lib/tests/integration` is not part of the default run.

End-to-end checks need a target:

- **Simulator:** `make simulate-automation` in specter-playground. It freezes the `devtools/` submodule's checkout, so check out your branch there and rebuild.
- **F469:** a connected board and OpenOCD; `f469/disco doctor` checks the setup without changing it. Board requests pick up `touch.py` and `app_control.py` changes without reflashing.

After every state-changing input, follow [Visual Validation](docs/control-contract.md#visual-validation): the screenshot is the source of truth. When reporting, say what you verified: unit tests, simulator, or board.

## Conventions

- Update README.md and docs/control-contract.md in the same change as the CLI or contract.
- Commit subjects: `area: what changes`, e.g. `f469: keep the CPU running when the tool starts OpenOCD`. Areas include `cli`, `explore`, `f469`, `simulator`; drop the prefix when a change spans targets.
- One topic per branch: `feat/`, `fix/`, `chore/`.
