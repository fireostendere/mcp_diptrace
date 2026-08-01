from __future__ import annotations

import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
readme = root / "README_RU.md"
content = readme.read_text(encoding="utf-8")
start = content.index("Текущий релиз — версия 0.1.0.")
marker = "commit. CI собирает"
end = content.index(marker, start)
expected = (
    "Текущий релиз — версия 0.1.0. Tag `v0.1.0`, unsigned-артефакты,\n"
    "`SHA256SUMS.txt` и provenance-запись в\n"
    "[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) указывают на один и тот же\n"
    "commit. "
)
readme.write_text(content[:start] + expected + content[end + len("commit. "):], encoding="utf-8")
subprocess.run(
    ["git", "rm", "--force", "--", "scripts/sitecustomize.py"],
    cwd=root,
    check=True,
)
