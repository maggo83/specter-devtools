"""Quickstart command - AI agent context for disco tool."""

import click

QUICKSTART_TEXT = """\
# disco - STM32F469 Discovery Board Tool

Use `disco` for hardware interactions with the STM32F469-Discovery board:
OpenOCD, JTAG debugging, flash programming, power, and MicroPython REPL.
For UI control, use `specter-devtools --target f469`; it calls `disco ui control`.

## Command Tree

```
disco
├── cables          # Detect connected USB cables
├── check           # Run full board diagnostics
├── doctor          # Automated diagnostics with logging
│
├── ocd             # OpenOCD server management
│   ├── start       # Start OpenOCD (background)
│   ├── stop        # Stop OpenOCD
│   ├── status      # Check if running
│   └── cmd         # Send raw OpenOCD command
│
├── cpu             # CPU control (requires ocd start)
│   ├── halt        # Halt CPU
│   ├── resume      # Resume execution
│   ├── reset       # Reset and halt
│   ├── step        # Single step
│   ├── pc          # Show program counter
│   ├── regs        # Show all registers
│   ├── stack       # Show stack (N words)
│   └── gdb         # Show/launch GDB
│
├── mem             # Memory inspection
│   ├── read        # Read memory words
│   ├── vectors     # Show vector table
│   ├── dump        # Dump N words from flash
│   └── save        # Save region to file
│
├── flash           # Flash programming
│   ├── program     # Program firmware
│   ├── erase       # Mass erase (dangerous!)
│   ├── verify      # Verify against file
│   ├── read        # Read flash to file
│   ├── info        # Show flash bank info
│   ├── analyze     # Analyze firmware layout
│   ├── identify    # Identify build type
│   ├── rdp         # Show read protection level
│   ├── lock        # Set RDP level 1 (dangerous!)
│   ├── unlock      # RDP level 1 -> 0, mass erase (dangerous!)
│   └── fingerprint # Firmware fingerprints
│       ├── create  # Create new fingerprint
│       ├── update  # Update existing fingerprint
│       └── test    # Test against fingerprint
│
├── power           # USB power via YKUSH hub
│   ├── status      # Show devices and port states
│   ├── on          # Power ports on
│   ├── off         # Power ports off
│   └── cycle       # Power cycle ports
│
├── serial          # Serial/REPL communication
│   ├── list        # List serial devices
│   ├── repl        # Test REPL connection
│   ├── console     # Interactive console (screen)
│   ├── test        # Quick serial test
│   └── boot        # Reset and capture boot output
│
├── repl            # MicroPython REPL interaction
│   ├── exec        # Execute Python code
│   ├── info        # Show board info
│   ├── modules     # List available modules
│   ├── help        # Show MicroPython help
│   ├── hello       # Display message on screen
│   ├── import      # Import module, show output
│   ├── reset       # Soft-reset (Ctrl-D)
│   ├── ls          # List files
│   ├── cat         # Print file contents
│   ├── cp          # Copy file to/from board
│   └── rm          # Remove file
│
└── ui              # LVGL remote control (LVGL 9+)
    ├── control     # Control-contract request (JSON)
    ├── screenshot  # Framebuffer as PNG
    ├── screen      # Dump widget tree
    ├── click       # Click widget by text or path
    └── write       # Set textarea text
```

## Quick Start

1. Connect: microUSB (ST-LINK) + miniUSB (USB OTG)
2. `disco cables` - Verify connections
3. `disco doctor` - Run full diagnostics (auto-connects to OpenOCD)

## Common Workflows

**First thing when board misbehaves:**
```
disco doctor          # Automated fault analysis with logging
```
Doctor checks: OpenOCD, JTAG, fault registers, FPU, vectors, USB/REPL.
Logs saved to `/tmp/disco_log/`.
Note: Commands auto-connect to OpenOCD; use `disco ocd start` to keep it running.

**Debug crash manually:**
```
disco cpu regs        # Check registers
disco mem vectors     # Verify vector table
disco cpu stack 16    # Inspect stack
```

**Flash firmware:**
```
disco flash program firmware.bin   # Address auto-detected; verifies and resets
disco flash verify firmware.bin    # Internal filesystem is reported separately
```

**Fingerprint testing (CI/regression):**
Fingerprints capture firmware identity (hash, regions, version) and runtime
behavior (JTAG, USB, REPL). Used for regression testing and CI validation.
```
disco flash fingerprint create firmware.bin    # Create new fingerprint
disco flash fingerprint test fingerprint.yaml  # Test against expected
disco flash fingerprint test fp.yaml --static-only  # File-only (no hardware)
```

**MicroPython interaction:**
```
disco repl exec "print('hello')"
disco repl ls / && disco repl cat /main.py
disco repl cp local.py :/main.py
```

## Memory Map

| Region      | Address    | Size  |
|-------------|------------|-------|
| Bootloader  | 0x08000000 | 128K  |
| Firmware    | 0x08020000 | 1.75M |
| RAM         | 0x20000000 | 320K  |
| SDRAM       | 0xC0000000 | 16M   |
"""


@click.command()
@click.option("--raw", is_flag=True, help="Output without formatting")
def quickstart(raw: bool):
    """Output AI agent context for disco tool.

    Prints command reference and workflows for AI agents.
    Use in Claude Code hooks (SessionStart, PreCompact).
    """
    click.echo(QUICKSTART_TEXT)
