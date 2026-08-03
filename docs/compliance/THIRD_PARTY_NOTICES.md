# Third-party notices

This file is a reproducible engineering inventory of direct dependencies declared by
`pyproject.toml`. It is not legal advice and does not conclude that a release is cleared
for redistribution. Verify each dependency's current license text, notices, transitive
dependencies, and any bundled native library before publishing an artifact.

Inventory binding: commit `a73ac649d156148b33c89f4c31009727eb0e8264`, inspected date `2026-08-03`.

The Python wheel declares dependencies but does not vendor them. The Windows bridge is a
PyInstaller bundle and requires a separate per-build contents and notice review.

| Dependency | Declared groups | Declared requirement(s) | License metadata used by this inventory | Review |
| --- | --- | --- | --- | --- |
| `hatchling` | build, development | hatchling>=1.27,<2 | `MIT` | human review required |
| `hypothesis` | development | hypothesis>=6.135,<7 | `MPL-2.0` | human review required |
| `jsonschema` | development | jsonschema>=4.24,<5 | `MIT` | human review required |
| `mcp` | runtime | mcp>=1.28.1,<2 | `MIT` | human review required |
| `mypy` | development | mypy>=1.16,<2 | `MIT` | human review required |
| `pydantic` | runtime | pydantic>=2.11,<3 | `MIT` | human review required |
| `pyinstaller` | bridge | pyinstaller>=6.14,<7 | `GPL-2.0-or-later WITH Bootloader-exception` | human review required |
| `pytest` | development | pytest>=8.4,<9 | `MIT` | human review required |
| `pytest-cov` | development | pytest-cov>=6.2,<7 | `MIT` | human review required |
| `PyYAML` | development | PyYAML>=6.0,<7 | `MIT` | human review required |
| `ruff` | development | ruff>=0.12,<1 | `MIT` | human review required |
| `shapely` | geometry | shapely>=2.0,<3 | `BSD-3-Clause` | human review required |
| `typing-extensions` | runtime | typing-extensions>=4.12,<5 | `PSF-2.0` | human review required |

## Open review items

- Resolve unknown or incomplete license metadata from authoritative upstream files.
- Review `hypothesis` and the PyInstaller licensing/bootloader exception before any bundled release.
- Inspect the actual Windows bridge bundle and record all bundled native libraries and notices.
- Keep any external documentation material outside release archives; the replacement factual inventory is project-authored observation data and is not a normative source.
