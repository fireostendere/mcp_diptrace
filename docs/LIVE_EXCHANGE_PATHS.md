# Live exchange paths across Windows and WSL

A live session records the exchange path in the native syntax of the bridge
process that created it. For the supported Windows DipTrace bridge this remains
a Windows path such as:

```text
C:\Users\name\AppData\Local\Temp\DipTrace\plugin_exchange.xml
```

When the MCP server runs in WSL, it derives the corresponding
`/mnt/<drive>/...` path in memory for validation and reads. It never writes the
derived WSL path back into session metadata. The Windows bridge therefore keeps
using the authoritative Windows-native target during finalization.

`DIPTRACE_MCP_WSL_MOUNT_ROOT` may override the default `/mnt` drive-mount root.
The value must be absolute.

A path whose syntax disagrees with the recorded creator platform fails closed
before `control.json` is published. In particular, Windows rejects a persisted
`/mnt/c/...` exchange path instead of resolving it as the phantom target
`C:\mnt\c\...` and reporting a false successful apply.

After upgrading the server and bridge, close any pre-upgrade active live session
and start a fresh bridge session so the new `exchange_path_platform` binding is
present in metadata.
