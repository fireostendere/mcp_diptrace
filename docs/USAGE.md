# Complete DipTrace MCP Guide

## 1. Purpose

DipTrace MCP gives a language model structured access to PCB and schematic design data.
It does not emulate mouse or keyboard input. The integration is based on the official
DipTrace XML formats, which represent components, nets, geometry, design rules, and
other project objects.

Two operating modes are available:

1. **Live** — analyze and modify the document currently open in DipTrace.
2. **Offline** — analyze and modify an XML file on disk without running DipTrace.

Live mode is intended for interactive work. Offline mode is suitable for reviews,
automated reports, version control, and batch processing of saved XML documents.

This guide and the live acceptance path were reviewed against an installed DipTrace 5.3
build exporting XML `Version="5.3.0.2"`. The integration remains feature- and
fixture-gated because the public XML specification PDFs used by the project still
contain 4.3-era examples.

## 2. Installing the Server

### 2.1 Windows

Install Python 3.10 or later. The project CI covers Python 3.10, 3.12, and 3.13. Check
the installed version:

```powershell
py -3 --version
```

Create an environment and install the project:

```powershell
cd C:\path\to\mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Verify the entry point:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --help
```

For exact polygon, ellipse, obround, and swept-trace geometry, install the optional
geometry extra:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[geometry]"
```

### 2.2 Linux and macOS

The live bridge is a Windows executable, but the offline MCP server is cross-platform:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

### 2.3 WSL

DipTrace runs on Windows while the MCP server may run in WSL. Both processes must use
the same Windows state directory:

```bash
export DIPTRACE_MCP_WORKSPACE=/mnt/c/Users/you/Documents/DipTrace
export DIPTRACE_MCP_STATE_DIR=/mnt/c/Users/you/AppData/Local/DipTraceMCP
```

When the workspace is under `/mnt/<drive>/Users/<user>/...`, the server can usually
derive the Windows state directory automatically. Setting it explicitly removes
ambiguity.

Create the WSL virtual environment with Linux Python. Do not reuse a Windows virtual
environment from WSL.

## 3. Building the DipTrace Bridge

DipTrace plug-ins are executable `.exe` files. The build script packages the bridge with
PyInstaller:

```powershell
cd C:\path\to\mcp_diptrace
powershell -ExecutionPolicy Bypass -File .\plugin\build_bridge.ps1
```

Output:

```text
plugin\dist\diptrace_mcp_bridge.exe
```

Clean rebuild:

```powershell
.\plugin\build_bridge.ps1 -Clean
```

When Python is not available through `py`:

```powershell
.\plugin\build_bridge.ps1 -PythonCommand "C:\Python312\python.exe"
```

The result is unsigned because it is built locally from the repository source.

## 4. Installing the DipTrace Plug-in

Close PCB Layout and Schematic Capture before installation. DipTrace reads plug-in
folders and `settings.xml` when the corresponding module starts.

Open PowerShell as Administrator:

```powershell
cd C:\path\to\mcp_diptrace
.\plugin\install_plugin.ps1
```

The installer selects the first detected installation, checking `DipTrace5` before the
legacy `DipTrace` directory. A default DipTrace 5.x installation receives plug-in
folders equivalent to:

```text
C:\Program Files\DipTrace5\Plugins\PCB\DipTraceMCP\
C:\Program Files\DipTrace5\Plugins\Schematic\DipTraceMCP\
```

Each folder contains:

```text
diptrace_mcp_bridge.exe
settings.xml
```

Install for PCB Layout only:

```powershell
.\plugin\install_plugin.ps1 -Mode PCB
```

Install for Schematic Capture only:

```powershell
.\plugin\install_plugin.ps1 -Mode Schematic
```

Use a non-standard DipTrace directory:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\EDA\DipTrace"
```

Remove the plug-in:

```powershell
.\plugin\install_plugin.ps1 -Uninstall
```

Restart DipTrace and verify `Tools → Plugins → DipTrace MCP Bridge`.

The official DipTrace plug-in contract launches the configured executable with the
path to a temporary `plugin_exchange.xml` file. DipTrace waits for the process to exit
and then imports the same file.

## 5. Connecting an MCP Client

### 5.1 Codex CLI

Codex stores MCP configuration in `~/.codex/config.toml`, or in a project-scoped
`.codex/config.toml` for a trusted project. Add the local STDIO server with:

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\path\to\mcp_diptrace\.venv\Scripts\diptrace-mcp.exe"
```

Check the configuration:

```powershell
codex mcp list
codex mcp --help
```

Manual configuration:

```toml
[mcp_servers.diptrace]
command = "C:\\path\\to\\mcp_diptrace\\.venv\\Scripts\\diptrace-mcp.exe"
cwd = "C:\\path\\to\\mcp_diptrace"
startup_timeout_sec = 20
tool_timeout_sec = 120

[mcp_servers.diptrace.env]
DIPTRACE_MCP_WORKSPACE = "C:\\Users\\you\\Documents\\DipTrace"
```

Restart the Codex client after changing the configuration. In the Codex TUI, use `/mcp`
to inspect active servers.

### 5.2 Codex in WSL

Create a Linux virtual environment, for example `.venv-wsl`, and register its Linux
entry point:

```bash
codex mcp add diptrace \
  --env DIPTRACE_MCP_WORKSPACE=/mnt/c/Users/you/Documents/DipTrace \
  --env DIPTRACE_MCP_STATE_DIR=/mnt/c/Users/you/AppData/Local/DipTraceMCP \
  -- /mnt/c/path/to/mcp_diptrace/.venv-wsl/bin/diptrace-mcp
```

### 5.3 Claude Desktop

Add the server to the Claude Desktop configuration and replace the paths:

```json
{
  "mcpServers": {
    "diptrace": {
      "command": "C:\\path\\to\\mcp_diptrace\\.venv\\Scripts\\diptrace-mcp.exe",
      "env": {
        "DIPTRACE_MCP_WORKSPACE": "C:\\Users\\you\\Documents\\DipTrace"
      }
    }
  }
}
```

A complete template is available at `examples/claude_desktop_config.json`. Fully restart
Claude Desktop after editing the configuration.

### 5.4 Any STDIO MCP Client

Use:

```text
command: C:\path\to\.venv\Scripts\diptrace-mcp.exe
args: []
transport: stdio
```

Do not write diagnostic messages to `stdout`; that stream carries MCP JSON-RPC. Logging
must go to `stderr` or a file.

### 5.5 Streamable HTTP

Start a local endpoint:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --transport streamable-http --host 127.0.0.1 --port 8765
```

Client URL:

```text
http://127.0.0.1:8765/mcp
```

The server does not implement built-in remote authentication. Keep it on loopback unless
a separate authenticated reverse proxy is configured. STDIO is preferred for ordinary
local use.

## 6. Live Workflow

### 6.1 Start

1. Open a schematic or PCB in DipTrace.
2. Save the project using the normal DipTrace command.
3. Select `Tools → Plugins → DipTrace MCP Bridge`.
4. The bridge window displays a session identifier.
5. DipTrace waits for the plug-in process; the current document cannot be edited in the
   GUI during this time.
6. Ask the MCP client to inspect the session status.

Example request:

> Use DipTrace MCP. Show the status and a concise summary of the active project. Do not modify anything.

The client should call `diptrace_status`, `get_capabilities`, and then
`summarize_design` without a `path`. Omitting `path` selects the active live session.

### 6.2 Analyze

Example natural-language requests:

> Show all components containing `USB` and the nets connected to them.

> Find R17 and list the nets on all of its pins or pads.

> Show DRC settings, net classes, via styles, and the stackup of the active PCB.

> Check the schematic for pins with `NetId=-1`, distinguishing them from intentional `NotConnected=Y` pins.

> Read only the XML fragment for net `USB_D+`.

> Run the available offline board review and explain all skipped checks and confidence levels.

### 6.3 Modify

Prefer semantic high-level tools and transactions. A suitable request is:

> Change R1 from 10k to 22k. First create a dry-run semantic transaction, show the diff and preview, and verify the source SHA. Commit only after the preview is accepted, then rerun the relevant checks.

For a structure not covered by semantic tools, use the low-level expert workflow:

> Change the `Value` element of R1 from 10k to 22k. Run `apply_xml_edits` with `dry_run=true`, require exactly one XPath match, and show the diff. Then repeat the same edit with `dry_run=false` and `expected_sha256` from the preview.

After a successful write, the working XML copy has changed, but DipTrace has not yet
imported it.

### 6.4 Finish

Apply the working copy:

```text
finish_live_session(action="apply")
```

Cancel the entire live session:

```text
finish_live_session(action="cancel")
```

The buttons in the bridge window perform the same actions. After the bridge process
exits, DipTrace either imports the updated exchange file or continues with the original
unchanged file.

After `apply`:

1. visually inspect every modified object;
2. run ERC for a schematic, or DRC and Check Net Connectivity for a PCB;
3. save the project under controlled revision or version control.

## 7. Offline Workflow

### 7.1 Prepare a File

For a legacy binary project, export each document separately:

```text
File → Export → DipTrace XML
```

Place the result inside `DIPTRACE_MCP_WORKSPACE` or one of
`DIPTRACE_MCP_ALLOWED_ROOTS`.

Some current `.dip`, `.dch`, `.eli`, or `.lib` files may already contain XML. Direct
analysis is allowed only after the server verifies an official DipTrace XML root; the
file extension alone is not sufficient.

### 7.2 Scan

```text
scan_diptrace_documents(root="C:\\Projects\\BoardA", recursive=true)
```

The scanner may inspect `.xml`, `.dip`, `.dch`, `.eli`, and `.lib` candidates, but it
returns only files whose content passes DipTrace XML root validation.

### 7.3 Analyze a Specific File

```text
summarize_design(path="BoardA/controller.xml")
list_components(path="BoardA/controller.xml", query="USB")
list_nets(path="BoardA/controller.xml", query="GND")
```

Relative paths are resolved from `DIPTRACE_MCP_WORKSPACE`.

## 8. Tools and Resources

The runtime source of truth is MCP `tools/list`, together with `get_capabilities` for the
selected document. Do not infer support solely from this guide.

Representative read and query tools include:

| Tool or group | Purpose | Writes files |
|---|---|---:|
| `diptrace_status` | Configuration and active live-session status | No |
| `get_capabilities` | Available and unavailable capabilities with reasons | No |
| `scan_diptrace_documents` | Find validated DipTrace XML documents | No |
| `summarize_design` | Schematic, PCB, or library summary | No |
| component/net/object queries | Search objects, nets, endpoints, and relationships | No |
| board/schematic/library models | Normalized document models | No |
| rules/stackup/connectivity | DRC/ERC settings, classes, layers, and graph | No |
| review tools | Offline DRC/ERC, board, schematic, DFM/DFA/DFT/BOM reviews | No |
| SI tools | Length, skew, differential-pair, and preliminary impedance analysis | No |
| `read_xml_fragment` | Bounded XPath-based source XML read | No |

Representative write workflows include:

| Tool or group | Purpose | Writes files |
|---|---|---:|
| `create_schematic_document` / `create_pcb_document` | New project scaffolding (sheets, layers, stackup, rules) | Immediately |
| semantic transactions | Plan, preview, commit, and rollback typed edits | On commit |
| component/part/text/rule operations | Controlled high-level modifications | On commit |
| schematic authoring | `add_sheet`, `place_part`, `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, `add_net_label` | On commit |
| `sync_schematic_to_pcb` | Additive or guarded exact component/net/ratline synchronization | On commit |
| `set_panelization` / `clear_panelization` | Official panel parameters (V-Scoring / Tab Routing) | On commit |
| test-point operations | Add, move, or remove standalone test points | On commit |
| routing plans | Trace/via and coupled differential-pair operations | On commit |
| `analyze_routing_congestion` | Read-only corridor congestion and ordering evidence | Never |
| `route_connections` | Congestion-ordered multi-net routing with bounded rip-up/retry | On commit |
| silkscreen/placement plans | Deterministic plan, preview, and apply | On commit |
| `apply_xml_edits` | Low-level expert XML preview or write | Only with `dry_run=false` |
| `finish_live_session` | Apply or cancel a live session | Controls live import |

Large diffs, previews, findings, jobs, and exports are exposed through bounded
`diptrace://...` resources. See [MCP Tools and Resources](MCP_TOOLS.md) for the detailed
capability map.

### 8.1 Synchronize a Schematic into a PCB

`sync_schematic_to_pcb` uses the ordinary semantic transaction path. It is additive by default.
Set `reconciliation_mode` to `exact` only when the schematic is authoritative: unmatched PCB
components/nets/ratlines are removed and traces are removed only from nets whose endpoint sets
change. Locked objects require the additional `allow_locked_reconciliation=true` authorization.
Preview the operation first:

```json
{
  "schematic_path": "project/controller.dch",
  "pcb_path": "project/controller.dip",
  "pattern_library_paths": ["libraries/project_patterns.lib"],
  "component_mappings": [
    {"refdes": "R1", "pattern_style": "RES_0603"},
    {
      "refdes": "U1",
      "pattern_style": "QFN_32",
      "pin_map": [
        {"part_id": "12", "pin": 0, "pad_number": "1"},
        {"part_id": "13", "pin": 0, "pad_number": "17"}
      ]
    }
  ],
  "dry_run": true
}
```

For a single-part component, pin order maps to pattern pad order when the pattern is available.
Multi-part components require explicit `part_id`/`pin` to `pad_number` entries for every connected
pin whose mapping cannot be proven. Library and PCB units must match when a pattern subtree is
copied. New components receive deterministic grid coordinates; run placement legalization before
routing. Commit the returned transaction with its PCB source SHA-256.

## 9. Low-Level XML Operations

`apply_xml_edits` supports:

- `set_text` — replace an element's text;
- `set_attribute` — set an attribute;
- `remove_attribute` — remove an existing attribute;
- `append_xml` — append one XML element to a matched parent;
- `replace_xml` — replace a matched element with one XML element;
- `delete_element` — delete a matched element.

Use this API only when a verified semantic tool is unavailable. Every edit must include
an exact `expected_matches` guard.

### 9.1 Change a Component Value

Preview:

```json
{
  "path": "controller.xml",
  "dry_run": true,
  "edits": [
    {
      "operation": "set_text",
      "xpath": "./Board/Components/Component[RefDes='R1']/Value",
      "value": "22k",
      "expected_matches": 1
    }
  ]
}
```

Commit the same edit array with the SHA returned by preview:

```json
{
  "path": "controller.xml",
  "dry_run": false,
  "expected_sha256": "SHA_FROM_PREVIEW",
  "edits": [
    {
      "operation": "set_text",
      "xpath": "./Board/Components/Component[RefDes='R1']/Value",
      "value": "22k",
      "expected_matches": 1
    }
  ]
}
```

For a schematic, the value path commonly resembles:

```text
./Schematic/Components/Part[RefDes='R1']/Value
```

A multi-part component may produce multiple matches. In that case, use the exact
expected count or refine the XPath with `PartRefDes`, `PartNumber`, `Id`, or another
verified discriminator.

### 9.2 Change an Attribute

```json
{
  "operation": "set_attribute",
  "xpath": "./Board/Components/Component[RefDes='U1']",
  "attribute": "Locked",
  "value": "Y",
  "expected_matches": 1
}
```

### 9.3 Add an Additional Field

When the component has no `AddFields` container:

```json
{
  "operation": "append_xml",
  "xpath": "./Board/Components/Component[RefDes='U1']",
  "value": "<AddFields><AddField Type='Text'><Name>MPN</Name><Text>ABC-123</Text></AddField></AddFields>",
  "expected_matches": 1
}
```

When `AddFields` already exists, append only an `AddField` inside that container. Confirm
the exact structure against the source document or official XML specification before
writing.

### 9.4 XPath

The implementation uses `xml.etree.ElementTree` syntax, not full XPath 1.0. Supported
constructs include ordinary paths, `.//Tag`, indices, and simple predicates such as
`[RefDes='R1']` and `[@Id='0']`.

The document root is `Source`. The following forms are normalized as equivalent where
supported by the service:

```text
./Board/Components
/Source/Board/Components
Source/Board/Components
```

Deleting or replacing the `<Source>` root is prohibited.

## 10. Environment Variables

| Variable | Default | Meaning |
|---|---|---|
| `DIPTRACE_MCP_WORKSPACE` | current process directory | Base directory for relative paths |
| `DIPTRACE_MCP_ALLOWED_ROOTS` | workspace only | Additional roots, separated by `;` on Windows and `:` on Unix |
| `DIPTRACE_MCP_STATE_DIR` | `%LOCALAPPDATA%\DipTraceMCP` on Windows | Shared live-session directory |
| `DIPTRACE_MCP_POLICY` | project default | `read_only`, `review`, `interactive_edit`, `automation`, or `manufacturing` |
| `DIPTRACE_MCP_MAX_DOCUMENT_BYTES` | `134217728` | Maximum size of one XML document |
| `DIPTRACE_MCP_MAX_SCAN_FILES` | `500` | Maximum number of scan candidates |
| `DIPTRACE_MCP_SESSION_TIMEOUT` | `7200` | Bridge timeout in seconds |
| `DIPTRACE_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `DIPTRACE_MCP_HOST` | `127.0.0.1` | HTTP server address |
| `DIPTRACE_MCP_PORT` | `8765` | HTTP server port |
| `DIPTRACE_MCP_FREEROUTING` | unset | Explicit Freerouting JAR or adapter enablement path |
| `DIPTRACE_MCP_JAVA` | auto-detected | Explicit Java executable for Freerouting jobs |
| `DIPTRACE_MCP_NGSPICE` | auto-detected | Explicit ngspice executable or portable Python wrapper |
| `DIPTRACE_MCP_OPENEMS_RUNNER` | unset | Compatible openEMS JSON-protocol runner |
| `DIPTRACE_MCP_EXTERNAL_TIMEOUT` | `3600` | Maximum external-job timeout in seconds |
| `DIPTRACE_MCP_MAX_EXTERNAL_RESULT_BYTES` | `16777216` | Maximum typed solver-result artifact size |

Example with multiple Windows roots:

```text
DIPTRACE_MCP_ALLOWED_ROOTS=C:\Projects\Boards;D:\Archive\DipTrace
```

## 11. Backups and State Directory

Offline backup:

```text
<XML directory>\.diptrace-mcp-backups\<name>.<UTC>.<hash>.bak
```

Live state:

```text
%LOCALAPPDATA%\DipTraceMCP\
  active.json
  sessions\<uuid>\
    metadata.json
    original.xml
    working.xml
    control.json
    backups\
```

`original.xml` is the diagnostic copy of the live input. The MCP server modifies
`working.xml`. To finish a session, the server first atomically records the request in
`metadata.json`, then publishes `control.json` as the cross-process commit marker.
The control payload contains only `apply` or `cancel` and the expected working-file
hash. The bridge verifies that hash before finalization and uses bounded retries for
transient Windows metadata sharing errors.

## 12. Troubleshooting

### The Plug-in Does Not Appear

- Close every DipTrace module completely.
- Check `Plugins\PCB\DipTraceMCP\settings.xml` or
  `Plugins\Schematic\DipTraceMCP\settings.xml`.
- Verify that `diptrace_mcp_bridge.exe` is in the same folder.
- Verify `ExeFile="diptrace_mcp_bridge.exe"`.
- Restart the relevant DipTrace module.

### `No active DipTrace session`

- Start the plug-in from an open, saved document first.
- Compare the `state_dir` reported by `diptrace_status` with
  `%LOCALAPPDATA%\DipTraceMCP`.
- Set `DIPTRACE_MCP_STATE_DIR` explicitly in WSL.
- Finish the existing live session before starting another one.

### DipTrace Appears Frozen

This is expected during a live session: DipTrace is synchronously waiting for the
plug-in process to finish. Complete the session through MCP or press `Cancel` in the
bridge window.

### The Server Rejects a Path

The file is outside `DIPTRACE_MCP_WORKSPACE` and `DIPTRACE_MCP_ALLOWED_ROOTS`. Add only
the required directory, restart the MCP server, and retry.

### `Expected <Source> root`

The input is not a supported DipTrace XML document. A legacy `.dip` or `.dch` file may
be binary. Export it as DipTrace XML, or verify that a current native file actually
contains an official XML root.

Standalone Component and Pattern Library XML may use an official `<Library>` root; the
normalized library reader handles only verified library source types.

### `matched N elements, expected M`

The match guard worked correctly. Read the relevant source fragment, then refine the
XPath or explicitly supply the correct match count.

### `Document changed: expected ..., current ...`

The document changed after preview. Do not bypass the guard. Repeat the dry run against
the current version.

### Windows Blocks the Bridge

Build the executable locally from the repository. Review the source and verify the file
hash. If necessary, allow that specific executable through the applicable Windows or
corporate policy. Do not disable system protection globally.

### Manual Server Check

```powershell
$env:DIPTRACE_MCP_WORKSPACE = "C:\Users\you\Documents\DipTrace"
.\.venv\Scripts\diptrace-mcp.exe --transport stdio
```

In STDIO mode the process waits for JSON-RPC and may display nothing. Stop it with
`Ctrl+C`.

## 13. Engineering Limits

A structurally valid XML modification does not prove that the schematic or PCB is
electrically or manufacturably correct. After every write, verify:

- uniqueness and semantics of `Id` and `UpdateId`;
- component, part, pad, and pin references;
- net-class and via-style identifiers;
- units from `Source@Units`;
- ERC, DRC, and connectivity;
- visual geometry, layers, solder mask, paste, courtyard, and board outline;
- copper-pour refill inside DipTrace;
- final manufacturing exports generated by DipTrace or the selected fabrication flow.

The MCP server does not generate authoritative native Gerber, NC Drill, ODB++, or
IPC-2581 output. Generic manifests are review artifacts only.

Official XML and plug-in specifications are available from the DipTrace
[Tutorials & Docs](https://diptrace.com/support/tutorials/) page and may also be
installed in the application's documentation directory. The current public plug-in
specification confirms the synchronous executable exchange mechanism and the
`Plugins/PCB`, `Plugins/Schematic`, `Plugins/CompEdit`, and `Plugins/PattEdit` module
folders.
