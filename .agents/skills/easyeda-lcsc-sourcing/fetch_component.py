#!/usr/bin/env python3
"""Fetch LCSC/EasyEDA component JSON + datasheet PDF for one part.

Usage:
    fetch_component.py <MPN | C-code> [--out DIR]

Endpoints verified 2026-08-25 (see SKILL.md). Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CODE_RE = re.compile(r"lcsc\.com/product-detail/(C[0-9]{6,8})\.html")
SVG_RE = re.compile(r"component_svgs/prod/([a-f0-9]{32})")


def curl(url: str, *, dest: Path | None = None, follow: bool = True) -> str | bytes:
    cmd = ["curl", "-sS", "-m", "40", "-A", UA]
    if follow:
        cmd.append("-L")
    if dest is None:
        cmd += ["--", url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    result = subprocess.run([*cmd, "-o", str(dest), "--", url])
    if result.returncode != 0:
        raise RuntimeError(f"curl failed ({result.returncode}) for {url}")
    return dest.read_bytes()


def resolve_code(query: str) -> str:
    if re.fullmatch(r"C[0-9]{6,8}", query):
        return query
    html = curl(f"https://html.duckduckgo.com/html/?q={query}+lcsc+product-detail")
    match = CODE_RE.search(html)
    if not match:
        raise SystemExit(f"No LCSC product code found for {query!r}")
    return match.group(1)


def pick_component_json(code: str) -> tuple[dict, dict]:
    html = curl(f"https://www.lcsc.com/product-detail/{code}.html")
    uuids = list(dict.fromkeys(SVG_RE.findall(html)))
    if not uuids:
        raise SystemExit(f"{code}: product page has no EasyEDA library (component_svgs)")
    pdf = re.search(r'"pdfUrl":"(https://datasheet\.lcsc\.com/[^"]+)"', html)
    for uuid in uuids:
        payload = json.loads(curl(f"https://easyeda.com/api/components/{uuid}"))
        result = payload.get("result") or {}
        time.sleep(0.5)
        if result.get("packageDetail"):  # combined symbol+footprint doc
            return payload, (pdf.group(1) if pdf else "")
        print(f"  skip symbol-only doc {uuid}", file=sys.stderr)
    raise SystemExit(f"{code}: no combined EasyEDA document among {uuids}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("part")
    parser.add_argument("--out", default="vendor", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    code = resolve_code(args.part)
    print(f"{args.part} -> {code}")
    payload, pdf_url = pick_component_json(code)

    json_path = args.out / f"{code}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = payload["result"]
    pins = sum(1 for s in result["dataStr"]["shape"] if s.startswith("P~"))
    pads = sum(
        1
        for s in result["packageDetail"]["dataStr"]["shape"]
        if s.startswith("PAD~") or s.startswith("PAD,")
    )
    title = result.get("title", "?")
    package = result["packageDetail"].get("title", "?")
    print(f"wrote {json_path}: '{title}' pins~{pins} package='{package}' pads~{pads}")

    if pdf_url:
        pdf_path = args.out / f"{code}.pdf"
        pdf_path.write_bytes(curl(pdf_url, dest=pdf_path))  # type: ignore[arg-type]
        magic = pdf_path.read_bytes()[:5]
        if magic != b"%PDF-":
            raise SystemExit(f"datasheet download is not a PDF: {pdf_path}")
        print(f"wrote {pdf_path}")

    # Sanity: pin numbers must be non-empty strings.
    for shape in result["dataStr"]["shape"]:
        if shape.startswith("P~show~"):
            number = shape.split("~")[3]
            assert number and number.strip("~"), f"pin with empty number in {code}"
            break


if __name__ == "__main__":
    main()
