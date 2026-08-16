# macOS installation and GUI modes

DipTrace MCP `v0.4.0` adds a one-command macOS installation path that uses the
Wine runtime already bundled by the official DipTrace macOS application. It does
not require a separate Homebrew Wine or XQuartz installation.

## Validated hosts

The release gate exercises fresh GitHub-hosted macOS 15 environments on both:

- Apple Silicon (`arm64`, Apple M1 runner; DipTrace's bundled x86-64 Wine runs
  through Rosetta);
- Intel (`x86_64`).

The tested DipTrace application is `5.3.0.3`. The installer verifies the pinned
official DMG SHA-256 before copying `DipTrace.app` into a user-owned location.
These gates establish the tested paths only; they are not a universal claim for
every macOS/DipTrace version.

## One-command installation

Review the DipTrace license before running the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/main/scripts/install_macos.sh \
  | bash -s -- --accept-diptrace-license
```

On Apple Silicon, if Rosetta is already available, no additional flag is needed.
If Rosetta is absent, the installer fails closed instead of accepting Apple's
license silently. After reviewing those terms, rerun with:

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/main/scripts/install_macos.sh \
  | bash -s -- --accept-diptrace-license --accept-rosetta-license
```

By default the installer uses:

- DipTrace: `~/Applications/DipTrace.app`;
- MCP runtime/state: `~/Library/Application Support/DipTrace MCP`;
- workspace: `~/DipTrace`;
- command wrappers: `~/.local/bin`.

All locations can be overridden with the environment variables documented by
`install_macos.sh --help`.

## Visible GUI

The installed wrappers launch the real DipTrace Windows executables through the
Wine runtime and prefix embedded in `DipTrace.app`:

```bash
diptrace-schematic
diptrace-pcb
diptrace-component-editor
diptrace-pattern-editor
```

A host project path may be supplied to a visible launcher; the wrapper converts
it to the matching Wine path before launch.

## Headless GUI

macOS does not need the Linux Xvfb backend. DipTrace's bundled Wine exposes the
same Win32 desktop APIs used by the existing Windows GUI worker, so the default
headless path is:

```text
MCP / automation
    -> DipTrace.app bundled Wine prefix
        -> private hidden Win32 desktop
            -> real DipTrace GUI
                -> bounded Win32/UI automation worker
```

Run the isolation smoke with:

```bash
diptrace-gui-headless smoke
```

The clean-install gate verifies that the worker creates a private randomly named
Win32 desktop and that the input desktop is still `Default` before and after the
worker. It also runs `native-smoke` and the automation doctor. The worker has no
physical mouse/keyboard fallback.

A real project round-trip uses the same helper contract as Windows:

```bash
diptrace-gui-headless roundtrip \
  --editor schematic \
  --project "$HOME/DipTrace/design.dch" \
  --timeout 30
```

The wrapper translates the host path into the bundled Wine prefix. Native
Save/Close semantics remain claim-specific evidence: the hosted macOS release
gate currently proves real DipTrace GUI liveness, hidden-desktop isolation,
worker readiness, MCP stdio and bridge/session integration. It does not claim a
full native `.dch`/`.dip` Save/Close/Reopen round-trip without a suitable native
fixture and corresponding evidence.

## Shared state and bridge

`diptrace-mcp`, the bridge, the visible launchers and the hidden GUI worker all
use the same DipTrace Wine prefix and the same host workspace/state directories.
The wrappers convert those host directories to Windows paths before starting the
frozen Windows MCP or bridge. This avoids a split Linux/macOS-vs-Windows path
namespace inside the public MCP contract.

The installer places the matching bridge/settings payload into the four DipTrace
module plug-in directories inside the installed app's Wine prefix:

- PCB Layout;
- Schematic Capture;
- Component Editor;
- Pattern Editor.

## Doctor and repair

Run:

```bash
diptrace-mcp-doctor
```

The doctor checks the bundled Wine runtime, frozen MCP server and automation
helper against `C:\Program Files\DipTrace` in the app's prefix.

The installer is idempotent. To reuse an already installed `DipTrace.app` while
repairing/updating only the MCP integration:

```bash
bash scripts/install_macos.sh --skip-diptrace
```

## Security and boundaries

- The installer does not accept the DipTrace or Rosetta licenses implicitly.
- Downloaded release assets are SHA-256 checked.
- The official DipTrace DMG is pinned to the release-tested hash/version.
- Headless mode uses a private Win32 desktop and does not switch the user's input
  desktop or synthesize physical mouse/keyboard input.
- Headless GUI isolation is an automation boundary, not a process/filesystem/
  network sandbox.
- Windows binaries embedded in DipTrace MCP remain unsigned development assets.
- No Novarm/DipTrace endorsement, universal compatibility, or engineering
  sign-off is implied.
