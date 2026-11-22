# Third-party notices

This file is a reproducible engineering inventory of direct dependencies declared by
`pyproject.toml`. It is not legal advice and does not conclude that a release is cleared
for redistribution. Verify each dependency's current license text, notices, transitive
dependencies, and any bundled native library before publishing an artifact.

Inventory binding: commit `56e607fd15af5eed3a9fbe97cb1d12661d04765b`, inspected date `2026-11-22`.

The Python wheel declares dependencies but does not vendor them. The Windows bridge is a
PyInstaller bundle and requires a separate per-build contents and notice review.

| Dependency | Declared groups | Declared requirement(s) | License metadata used by this inventory | Review |
| --- | --- | --- | --- | --- |
| `hatchling` | build, development | hatchling>=1.27,<2 | `MIT` | human review required |
| `hypothesis` | development | hypothesis>=6.135,<7 | `MPL-2.0` | human review required |
| `jsonschema` | development | jsonschema>=4.24,<5 | `MIT` | human review required |
| `mcp` | runtime | mcp>=1.30.0,<1.31 | `MIT` | human review required |
| `mypy` | development | mypy>=1.16,<2 | `MIT` | human review required |
| `Pillow` | headless-gui | Pillow>=13,<14; sys_platform == 'win32' | `MIT-CMU` | human review required |
| `pydantic` | runtime | pydantic>=2.11,<3 | `MIT` | human review required |
| `pyinstaller` | bridge | pyinstaller==6.14.2 | `GPL-2.0-or-later WITH Bootloader-exception` | human review required |
| `pytest` | development | pytest>=9.0.3,<10 | `MIT` | human review required |
| `pytest-cov` | development | pytest-cov>=6.2,<7 | `MIT` | human review required |
| `pywinauto` | headless-gui | pywinauto==0.6.9; sys_platform == 'win32' | `BSD-3-Clause` | human review required |
| `PyYAML` | development | PyYAML>=6.0,<7 | `MIT` | human review required |
| `ruff` | development | ruff>=0.12,<1 | `MIT` | human review required |
| `shapely` | geometry | shapely>=2.0,<3 | `BSD-3-Clause` | human review required |
| `typing-extensions` | runtime | typing-extensions>=4.12,<5 | `PSF-2.0` | human review required |

## Open review items

- Resolve unknown or incomplete license metadata from authoritative upstream files.
- Review `hypothesis` and the PyInstaller licensing/bootloader exception before any bundled release.
- Inspect the actual Windows bridge bundle and record all bundled native libraries and notices.
- Keep any external documentation material outside release archives; the replacement factual inventory is project-authored observation data and is not a normative source.
