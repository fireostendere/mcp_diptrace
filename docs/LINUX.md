# Linux: one-command install, visible GUI, and headless GUI

Release candidate: `v0.4.0`. The permanent gate validates Ubuntu 24.04 x86-64.

The validated Linux deployment keeps DipTrace, the Windows standalone MCP server,
the bridge plug-in, and the GUI automation helper inside one user-owned Wine
prefix. No Python environment is required for this path.

## One-command install

Review the DipTrace license first, then explicitly allow the unattended DipTrace
installer:

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/main/scripts/install_linux.sh \
  | bash -s -- --accept-diptrace-license
```

The installer currently validates x86-64 Debian/Ubuntu-style systems with `apt`.
It uses `sudo` only for operating-system packages. The Wine prefix, DipTrace,
MCP runtime, workspace, state, wrappers, and desktop launchers are owned by the
normal user.

The installer pins and verifies the DipTrace installer and the DipTrace MCP
portable bundle by SHA-256. It installs Wine with the explicit 32-bit X11/OpenGL
runtime needed by the current DipTrace GUI, creates the Wine prefix, performs the
silent DipTrace installation, installs the bridge plug-in into the DipTrace
modules, installs the standalone MCP server and bundled Win32 GUI helper, and
runs a readiness doctor.

Default locations:

```text
Wine prefix  ~/.local/share/diptrace-mcp/wineprefix
MCP runtime  ~/.local/share/diptrace-mcp/runtime/current
Workspace    ~/DipTrace
State        ~/.local/state/diptrace-mcp
Commands     ~/.local/bin
```

## Visible GUI

The normal launchers use the current Linux display and run the real DipTrace
applications through the validated Wine prefix:

```bash
diptrace-schematic
diptrace-pcb
diptrace-component-editor
diptrace-pattern-editor
```

When installed without `--no-desktop`, matching Linux desktop entries are also
created for the four DipTrace editors.

## Headless GUI

`diptrace-gui-headless` creates a fresh private Xvfb server for each invocation,
disables X11 TCP listening, starts the existing bundled Win32 GUI worker through
Wine, and keeps the real DipTrace GUI off the physical desktop. Linux isolation
therefore happens at the X-server boundary; inside Wine the helper deliberately
uses its verified `native` Win32 desktop path rather than trying to create a
second hidden Win32 desktop.

This preserves the existing GUI safety model: the worker uses bounded Win32/UI
automation and does not fall back to physical mouse or keyboard input, screen
coordinates, `SendInput`, or desktop switching. The shared invariants and the
Windows implementation are documented in [Headless GUI worker](HEADLESS_GUI.md).

Check the private GUI path without opening a project:

```bash
diptrace-gui-headless native-smoke --timeout 20
```

Run a guarded native open/save/close round trip with a normal Linux path:

```bash
diptrace-gui-headless roundtrip \
  --editor schematic \
  --project "$HOME/DipTrace/design.dch" \
  --timeout 30
```

The wrapper converts the Linux project path and DipTrace installation path to
Wine paths itself and forces the helper to the Xvfb-backed native desktop. Do not
pass `--desktop` or `--diptrace-root`; those boundaries are owned by the Linux
wrapper.

The virtual screen can be changed when a larger or smaller canvas is required:

```bash
DIPTRACE_MCP_HEADLESS_SCREEN=2560x1440x24 \
  diptrace-gui-headless native-smoke --timeout 20
```

Accepted screen values have the form `WIDTHxHEIGHTx16`, `WIDTHxHEIGHTx24`, or
`WIDTHxHEIGHTx32`.

## MCP and bridge

The MCP client command is:

```bash
diptrace-mcp
```

The bridge, visible GUI launchers, headless GUI wrapper, and MCP server all use
the same Wine prefix, Linux workspace, and state directory. This avoids a second
Linux-specific project/session namespace.

Run the installation checks at any time with:

```bash
diptrace-mcp-doctor
```

The doctor verifies the DipTrace executables, MCP server, bridge plug-ins, bundled
GUI helper, MCP/bridge startup, and the private-Xvfb Win32 worker probe.

## Automated acceptance scope

The permanent `Linux one-command install` GitHub Actions workflow starts from a
fresh Ubuntu 24.04 runner and exercises the exact one-command installer. It then
checks the frozen MCP stdio contract, bridge shared state, a real DipTrace
Schematic GUI process on Xvfb, the installed private-Xvfb GUI worker, a second
virtual-screen size, and an idempotent reinstall.

That automated gate demonstrates the Linux Wine GUI runtime and GUI-worker
desktop plumbing. It does not by itself claim that every DipTrace dialog or every
future native host action has been validated under Wine. Native actions remain
bounded to the controls and flows explicitly implemented and tested by the GUI
worker.
