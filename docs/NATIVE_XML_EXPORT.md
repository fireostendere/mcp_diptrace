# Native XML export for review

Use this workflow to inspect saved native schematic and PCB files without a live
bridge session. The real DipTrace editor performs the export on a private copy.
It does not save the original, refill pours, run ERC/DRC, or certify the design.

## Windows command

Install the headless GUI dependencies and use an editable checkout, or explicitly
select the checkout rather than an older installed wheel:

```powershell
$env:PYTHONPATH = 'C:\work\mcp_diptrace\src'
py -m diptrace_mcp.native_xml_export `
  --diptrace-root 'C:\Program Files\DipTrace' `
  --project 'C:\work\board\main.dch' `
  --output-xml 'C:\work\board\build\main.dchxml' `
  --timeout 90
```

For PCB Layout, use `.dip` input and `.dipxml` output. Both filenames must be
distinct, and the output must not already exist. The exporter rejects symlink
inputs, validates finite timeouts up to 300 seconds, validates the exported XML
type, and compares the original SHA-256 before and after the operation.

The worker and its editor/encoder descendants belong to an owned Windows Job
Object. Timeout or exceptional exit closes that job instead of leaving an
editor on an inaccessible desktop. No unrelated editor process is terminated.
The physical input desktop must remain unchanged.

## Startup dialogs and menus

A hidden desktop can cause a Direct3D initialization warning. DipTrace paints
the warning text itself, so ordinary control text contains only an OK button.
Do not treat that button as permission to acknowledge an unknown warning.

With FFmpeg available, a blocked export captures a lossless dialog client PNG
beside the requested output and reports its SHA-256. Review that image first;
then repeat the command with `--startup-dialog-sha256` set to the reported hash.
The exporter also requires the expected dialog class and a unique enabled OK
button. A changed image or unknown modal dialog stops the export.
Only the owned message dialog's OK button uses a plain, non-animated Windows
theme during capture. Its label, enabled state and action are unchanged; this
prevents default-button glow from changing otherwise identical approval images.

Save As is selected by its native menu label. For owner-drawn blank labels, only
the verified editor executable hashes and complete menu ID sequences in the
exporter are accepted. Another build or menu layout fails closed. Current native
checks cover DipTrace 5.3.0.3 on a Windows hidden desktop.

## MCP access

The MCP server reads XML, not binary `.dch` or `.dip` files. Configure
`DIPTRACE_MCP_ALLOWED_ROOTS` with the project directory and reconnect the server.
The separator is the server platform's path separator (`:` on Linux, `;` on
Windows). Keep `DIPTRACE_MCP_POLICY=read_only` for review.

Keep exports in an allowed project directory. Confirm the effective roots with
`diptrace_status`, read the exported file with `get_document_info`, then inspect
components with `get_component`. When developing the server, select its checkout
with `PYTHONPATH` too; an old wheel can otherwise hide a tested parser fix.

Native caches can contain nonphysical default pad-style dimensions, including
unused negative sizes. The reader preserves those raw values with warnings;
it does not invent copper geometry or silently take the absolute value. A pad
that actually uses such a style still produces a library validation error.
Successful logical inspection is not a geometry or manufacturing PASS.

## Verification

```sh
.venv/bin/python -m pytest -q tests/test_native_export_process.py tests/test_nonphysical_pad_styles.py tests/test_libraries.py
```

The synthetic tests exercise timeout containment and invalid cached pad styles.
Native runs separately check both editor exports, unchanged input hashes,
normal editor shutdown and subsequent MCP component inspection. No customer
design, captured dialog, or workstation configuration is redistributed here.
