# Specter Devtools

Shared developer tooling for Specter simulators and hardware targets.

## Layout

| Path | Purpose |
|---|---|
| `src/specter_devtools/` | Shared control contract, target adapters, artifact capture, board-first CLI |
| `f469/` | STM32F469 Discovery board tool (`disco`): OpenOCD, flash, REPL, LVGL UI control |
| `simulator/sim_control/` | MicroPython control runtime frozen into the Unix simulator by the parent project |

Targets:

- `simulator`: TCP control endpoint of a simulator started with `--control`.
- `f469`: bundled `f469/disco`, using temporary raw-REPL LVGL scripts and OpenOCD framebuffer reads.
- `esp32-p4`: reserved for the upcoming board port; not implemented yet.

Nothing is installed persistently into production firmware.

The simulator binary itself stays in the product repository: it is the product's Python frozen into f469-disco's MicroPython Unix port. The parent project freezes `simulator/sim_control`; screenshots use f469-disco's `SDL.screenshot`, whose color fix is pending upstream in [miketlk/f469-disco#3](https://github.com/miketlk/f469-disco/pull/3), a follow-up to [#1](https://github.com/miketlk/f469-disco/pull/1) (see [docs/control-contract.md](docs/control-contract.md#transports)).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r f469/requirements.txt -e .
```

`f469/disco` activates this `.venv` automatically. OpenOCD must be installed for flash, CPU, and screenshot commands.

## Usage

```bash
specter-devtools --target simulator request '{"action":"capabilities"}'
specter-devtools --target f469 request '{"action":"click","text":"Manage Device"}'
specter-devtools --target f469 click "Manage Device"
specter-devtools --target f469 labels --layer top
specter-devtools --target f469 screenshot /tmp/board.png
specter-devtools --target simulator capture /tmp/sim-capture
specter-devtools --target simulator goto manage_security
specter-devtools --target simulator explore /tmp/screens
specter-devtools --target f469 board flash analyze firmware.bin
```

`request`, `screenshot`, and `capture` return the same JSON shapes on every target; use `capabilities` to discover differences. The shortcuts `click`, `tree`, and `labels` work on every target; `state`, `goto`, `back`, `set`, and `explore` need application state, which only the simulator offers. `board` passes raw commands to the board tool. See [docs/control-contract.md](docs/control-contract.md) for all requests and target differences.

## Tests

```bash
.venv/bin/python -m pytest
```

## License

[Grug 2-Clause License](LICENSE). `f469/` and `simulator/` contain MIT-licensed material from f469-disco and specter-playground; their [f469/LICENSE](f469/LICENSE) and [simulator/LICENSE](simulator/LICENSE) notices apply.
