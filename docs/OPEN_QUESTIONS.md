# Open Questions — DipTrace XML Format

This document lists every fact the code depends on but the official specification does not
settle. Each entry includes the question, why the code depends on it, the file:line that
assumes it, and the exact experiment that would settle it.

---

## Q1: Is `Component/@Angle` in radians or degrees?

**Why the code depends on it:** The reader at `adapters.py:223` reads the raw attribute
and calls `math.degrees()` on it, assuming it is in radians. The writer at
`semantic_compiler.py:2175` writes `math.radians(angle_deg)`. Every existing test
round-trips through the same assumption, so the test passes whether or not the assumption
is correct.

**File:line:** `adapters.py:223`, `adapters.py:591`, `semantic_compiler.py:2175`

**What the spec says:** "Component rotation angle. The parameter is absent if = 0."
No unit is stated. For text/picture shapes the spec explicitly says "Angle of the text
and picture in radians." For table orientation it says "digrees." The component angle
is silent.

**Experiment:** In DipTrace, place one component, set rotation to exactly 90 degrees,
export XML, read the literal attribute value. If the value is approximately 1.5708
(pi/2), the unit is radians. If it is exactly 90, the unit is degrees.

**Who can perform:** Human with DipTrace license.

---

## Q2: Does DipTrace address top-level arrays by `Id` or by position?

**Why the code depends on it:** The code deletes elements out of the middle of arrays
(Components, Nets, Ratlines, Traces). If DipTrace addresses by position (index), then
deleting element at index 2 causes element at index 3 to become index 2, and all
cross-references break. If it addresses by `Id`, deletions are safe.

**File:line:** Various deletion paths in `semantic_compiler.py`, `synchronization.py`

**Experiment:** Export a board with 3 components (Ids 0, 1, 2). Delete the middle
component (Id 1) by hand in a text editor. Open in DipTrace, save, re-export, compare
Ids. If the remaining components have Ids 0 and 2, DipTrace uses Id-based addressing.
If they have Ids 0 and 1, it uses position-based addressing.

**Who can perform:** Human with DipTrace license.

---

## Q3: What encoding and line endings does DipTrace write?

**Why the code depends on it:** The writer emits UTF-8 unconditionally. If DipTrace
produces UTF-16 with BOM, or uses CRLF line endings, round-tripping will change bytes.

**File:line:** `xml_document.py` (write path)

**Experiment:** Export the same board with `Units` = mm, inch, and mil. Examine the
raw bytes of each file. Check: (a) encoding declaration in the XML prolog, (b) presence
of BOM, (c) line endings (LF vs CRLF).

**Who can perform:** Human with DipTrace license.

---

## Q4: How many significant digits does DipTrace emit for `Real` attributes?

**Why the code depends on it:** The writer can produce scientific notation (e.g.
`9.6e-09`). If DipTrace does not emit scientific notation, or uses a fixed number of
significant digits, round-tripping will change the byte representation of every real
number.

**File:line:** `semantic_compiler.py` (float formatting), `xml_document.py`

**Experiment:** Place a component at a coordinate that requires many significant digits
(e.g. X="12.345678"). Export XML, examine the literal value. Try values like 0.001,
0.000001, 1e-6, 1e-9.

**Who can perform:** Human with DipTrace license.

---

## Q5: With `ImpMode=All`, does DipTrace re-import the exchange file after Cancel?

**Why the code depends on it:** If Cancel is a no-op (no re-import), then the
`ImpMode=All` profiles can safely be used for read-only sessions. If Cancel still
triggers a re-import, the plug-in must not modify the file at all during a read-only
session.

**File:line:** `sessions.py`, `bridge.py` (session state machine)

**Experiment:** Export XML, run the plug-in with `ImpMode=All`, press Cancel, save in
DipTrace, export again, compare SHA-256. If hashes differ, Cancel triggers re-import
and the PCB/Schematic profiles must move to `ImpMode=Edit`.

**Who can perform:** Human with DipTrace license.

---

## Q6: Does DipTrace honour `Selected="Y"` on import for newly added objects?

**Why the code depends on it:** The writer currently emits `Selected="N"` for all
objects. If DipTrace ignores this attribute on import, it is harmless. If DipTrace
uses it to determine which objects to highlight or apply operations to, emitting "N"
silently suppresses a user-visible state.

**File:line:** `semantic_compiler.py` (Selected attribute handling)

**Experiment:** Create a board with one component selected. Export XML. Verify that
the exported component has `Selected="Y"`. Then manually add a new component to the
XML with `Selected="Y"`, import via the plug-in, and check if DipTrace shows it as
selected.

**Who can perform:** Human with DipTrace license.

---

## Q7: What does DipTrace do if the plug-in exits non-zero, leaves the file unchanged,
or truncates it?

**Why the code depends on it:** The bridge must handle these error conditions. Today
the bridge reports success in all cases. If DipTrace ignores non-zero exit codes,
the bridge must use a different mechanism (file hash comparison) to detect failure.

**File:line:** `bridge.py` (exit handling), `service.py` (finish_live_session)

**Experiment:** (a) Make the plug-in exit with code 1. Does DipTrace show an error?
(b) Make the plug-in exit with code 0 but leave the file unchanged. Does DipTrace
import the unchanged file? (c) Make the plug-in truncate the file to 0 bytes. Does
DipTrace show an error or crash?

**Who can perform:** Human with DipTrace license.

---

## Q8: Which XML elements did DipTrace 5.3 add that the 2023 specifications do not cover?

**Why the code depends on it:** The spec PDFs describe format version 4.3.0.3. DipTrace
5.3 added a native XML project format and may have added new XML elements or attributes.
Without knowing what was added, the reader may silently drop data from 5.3 files.

**File:line:** `adapters.py` (element parsing), `xml_document.py` (version detection)

**Experiment:** Open the vendor's public "What's new" page for DipTrace 5.3. Check
the `Docs` folder inside the DipTrace installation for updated specification PDFs.
Export a board from DipTrace 5.3 and compare the element set against the 4.3.0.3 spec.

**Who can perform:** Human with DipTrace license and access to the installation directory.

---

## Q9: Does DipTrace write `Component/@Angle` when the value is 0?

**Why the code depends on it:** The spec says "The parameter is absent if = 0." The
code already handles this (omits the attribute when angle is 0). But we need to verify
DipTrace actually does this.

**File:line:** `semantic_compiler.py` (angle handling)

**Experiment:** Place a component with rotation 0. Export XML. Check whether the `Angle`
attribute is present or absent.

**Who can perform:** Human with DipTrace license.

---

## Q10: What is the maximum number of significant digits DipTrace uses for coordinates?

**Why the code depends on it:** If DipTrace uses 6 significant digits but the writer
uses 9, every coordinate will differ in the least significant digits, breaking
byte-for-byte round-tripping.

**File:line:** `semantic_compiler.py` (float formatting)

**Experiment:** Place components at various coordinates and export. Examine the number
of digits after the decimal point. Try coordinates like 0.1, 0.01, 0.001, 123.456789.

**Who can perform:** Human with DipTrace license.
