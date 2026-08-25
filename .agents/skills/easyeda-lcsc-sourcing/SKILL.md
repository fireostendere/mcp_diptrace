---
name: easyeda-lcsc-sourcing
description: >
  Fetch real LCSC/EasyEDA component catalog data over plain HTTPS: resolve an
  MPN to its LCSC part code, download the combined symbol+footprint JSON from
  the EasyEDA API, grab the official datasheet PDF, and convert the geometry
  into a DipTrace .elixml library fragment for schematic/PCB builds. Use when
  the user asks to source parts, download a datasheet, get a component symbol
  or footprint from EasyEDA/LCSC/JLCPCB, or feed vendor geometry into the
  headless DipTrace build pipeline. Not for the EasyEDA Pro editor MCP and not
  for stock/price queries at scale.
---

# EasyEDA / LCSC Component Sourcing

Verified against the live endpoints on 2026-08-25. All commands are stdlib-only
(`curl`, `python3`). Rate-limit yourself: ~1 request/second, cache everything
you download into the project's `vendor/` directory.

## Verified pipeline

### 1. Resolve MPN -> LCSC part code

LCSC's own search APIs (`wmsc.lcsc.com/wmsc/...`, `cart.jlcpcb.com/shoppingCart/
...`) are dead or auth-walled. Two working options:

- DuckDuckGo HTML endpoint (scriptable, no JS):

```bash
curl -sSL -m 20 -A "Mozilla/5.0" \
  "https://html.duckduckgo.com/html/?q=INA226AIDGSR+lcsc+product-detail" \
| grep -oE 'lcsc\.com/product-detail/(C[0-9]{6,8})\.html' | head -1
```

- Or any web-search tool with the query `<MPN> lcsc product detail`.
- If you already have the code (`C2980299`), skip this step.

### 2. Product page -> EasyEDA uuids + datasheet URL

`item.lcsc.com` may not resolve; use `www.lcsc.com`:

```bash
curl -sSL -m 25 -A "Mozilla/5.0" \
  "https://www.lcsc.com/product-detail/C165948.html" -o item.html
grep -oE 'component_svgs/prod/[a-f0-9]{32}' item.html | sort -u
grep -oE '"pdfUrl":"[^"]+"' item.html
```

The page embeds one or more `image.easyeda.com/component_svgs/prod/<uuid>.svg`
previews (symbol-only doc and usually a combined doc) plus a
`"pdfUrl":"https://datasheet.lcsc.com/datasheet/pdf/<uuid>.pdf?productCode=C..."`
field.

### 3. Download the combined component JSON

The authoritative geometry lives behind:

```bash
curl -sS "https://easyeda.com/api/components/<uuid>" > C165948.json
```

Response shape (same as historical `vendor/*.json` files):

- `result.dataStr.shape` — **symbol**: `P~show~0~<pin>~<x>~<y>~...` pins,
  `R~...` body rectangle;
- `result.packageDetail.dataStr.shape` — **footprint**: `PAD~RECT~...`,
  `TRACK~...`, `CIRCLE~...` entries, plus `packageDetail.title` (land-pattern
  name) and `dataStr.head.x/y` (footprint origin);
- `result.uuid`, `result.packageDetail.uuid` — provenance for AddFields.

If several svg uuids were found on the page, call the API for each and keep the
one whose `result.packageDetail` is non-null (that is the combined
symbol+footprint document).

### 4. Datasheet PDF

Direct download, no viewer:

```bash
curl -sSL -m 30 -A "Mozilla/5.0" "<pdfUrl>" -o C165948.pdf
file C165948.pdf   # must say: PDF document
```

Espressif moved its own docs to `documentation.espressif.com`; the old
`espressif.com/sites/default/files/documentation/*.pdf` links now return HTML.
For Espressif parts use `https://documentation.espressif.com/<doc>_en.pdf`.

### 5. Convert to DipTrace .elixml

Follow the proven converter pattern in
`attiny85-arduino-clone/convert_lcsc_c2845237.py`: parse the `P~show~...`
symbol pins and the footprint `PAD~RECT~...` records, emit
`Library/Library/PadStyles` + `Patterns` + `Library/Components` XML
(units are EasyEDA 1/100 inch -> multiply by 0.254 mm), validate with the repo
component/pattern validators, then import through `_component_definitions`
(`diptrace_mcp.services.builtin_library`) during schematic build.

Never hand-draw a component before this lookup documented zero exact matches
(house rule: DipTrace catalog -> LCSC/EasyEDA -> custom).

## One-shot helper

`fetch_component.py` in this directory automates steps 1-4:

```bash
python3 fetch_component.py INA226AIDGSR --out vendor     # by MPN
python3 fetch_component.py C2980299 --out vendor          # by LCSC code
# writes vendor/C2980299.json + vendor/C2980299.pdf, prints the summary
```

## Failure modes

- Endpoints change silently: always `file`-check downloads and assert
  `result.packageDetail` before converting; record the check date in the
  project `COMPONENT_PROVENANCE.md`.
- Some parts have no EasyEDA library at all (page has no `component_svgs`);
  fall back to the manufacturer land pattern from the datasheet and document it.
- Do not scrape search pages in bulk; keep lookups targeted and cached.
