# Windows/WSL lock interoperability probe

`SessionStore` can be accessed by a Windows bridge and a WSL MCP process through the same NTFS
directory. Windows `FileStream.Lock` and Linux/WSL `flock` are different locking APIs, so their
interoperability must not be assumed.

Run the manual topology probe from WSL:

```bash
./.venv/bin/python scripts/probe_windows_wsl_lock_interop.py
```

The script creates a UUID-named directory strictly below Windows Temp, tests both lock directions,
prints a path-free JSON report, and removes the one file and empty directory it created. It does not
modify a DipTrace project or the MCP state directory.

## Observed result

The probe was run on 2026-07-29 on the project's Windows 11 + WSL development host. In both
directions the contender acquired its lock while the other side still held its lock:

| Holder | Contender | Result |
| --- | --- | --- |
| WSL `flock` | Windows `FileStream.Lock` | acquired; incompatible |
| Windows `FileStream.Lock` | WSL `flock` | acquired; incompatible |

Host versions recorded by the path-free JSON output:

- Windows: `Windows 11 Pro` (localized product caption), version `10.0.26200.0`
- PowerShell: `5.1.26100.8894`
- WSL kernel: `6.18.33.2-microsoft-standard-WSL2`
- Python: `3.12.3`

This is manual evidence for one real Windows/WSL topology, not a portable guarantee and not a CI
test. The result means a cross-boundary live-session mutation protocol must not rely on either lock
API excluding the other. Re-run the probe after a Windows, WSL kernel, filesystem, or storage-layout
change; do not generalize the observation to native Linux, network filesystems, or other Windows
versions.
