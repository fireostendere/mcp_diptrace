# Q1 Component Angle — operator procedure and completed manual observation

This file remains the canonical operator procedure for Q1, but the private/manual acceptance campaign has now executed it successfully on production candidate:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

with DipTrace PCB Layout 5.3.0.3.

The manual gate `diptrace_q1_component_angle` is therefore **PASS** for that campaign scope. The private evidence ZIP SHA256 is:

`6b7d561e2fda4118cf6b4d94c137b04882f608d42dfc1f5148a093ac6b4a20bc`

The repository-owned `q1-component-angle.result.json` and the public runtime warning remain a separate source-controlled evidence-promotion boundary. The private source artifacts are not committed or redistributed by this documentation update.

## Observed semantics from the completed run

- GUI 90° -> `Component/@Angle="1.5708"`.
- GUI 180° -> `Component/@Angle="3.1416"`.
- GUI 270° -> `Component/@Angle="4.7124"`.
- Entering 360° normalizes the GUI to 0°; a canonical zero export may omit `Angle`.
- An existing `6.2832` literal can be preserved while the GUI displays 0°, so 0/360 are equivalent within the observed scope.
- `Change Side` from Top 90° produced Bottom `Angle="4.7124"`, `Flip="Y"`; the current reader reported `mirrored=true`.
- Coordinates, pattern, connectivity and other non-orientation component properties were preserved.
- Native open/save/re-export completed without warning, repair or error.

## Controlled experiment procedure

Use this procedure for any future independent rerun or evidence promotion:

1. On Windows, install or open the exact DipTrace PCB Layout build. Record the application version and build from the About dialog.
2. Create a new, disposable PCB owned by the project maintainer. Place two instances of the same component and pattern. Name them `U_CTRL` and `U_PROBE`; keep footprint, value, side, and all non-rotation properties equal. Put the control at UI rotation 0 degrees and the probe at UI rotation 90 degrees. If the build supports a bottom-side instance, repeat the probe on the bottom side and record the side/mirror state.
3. Export the design directly from DipTrace as `source.xml`. Do not pass it through MCP or edit its bytes by hand. Preserve the original file.
4. Open `source.xml` in DipTrace, save it under a distinct name, and export that saved design as `reexport.xml`. Record the literal `Component/@Angle` values for both references without converting them.
5. Independently perform the GUI sequence `0 -> 90 -> 180 -> 270 -> 0` (or `360`) on a disposable copy. Re-export after each step when the build permits it. Record sign, direction, units, numeric range, 0/360 normalization, side and mirror behavior, and unchanged RefDes, footprint, coordinates, and connectivity.
6. Capture the source/open-save/reexport triple with the existing recipe:

   ```text
   python scripts/capture_diptrace_evidence.py init --root <private-capture-root> --session q1-component-angle-001 --recipe q1-component-angle.recipe.json
   python scripts/capture_diptrace_evidence.py record --root <private-capture-root> --session q1-component-angle-001 --stage source --file <source.xml>
   python scripts/capture_diptrace_evidence.py record --root <private-capture-root> --session q1-component-angle-001 --stage open_save --file <open-save.xml>
   python scripts/capture_diptrace_evidence.py record --root <private-capture-root> --session q1-component-angle-001 --stage reexport --file <reexport.xml>
   python scripts/capture_diptrace_evidence.py check --root <private-capture-root> --session q1-component-angle-001
   python scripts/capture_diptrace_evidence.py finalize --root <private-capture-root> --session q1-component-angle-001
   ```

Use the exact command syntax in `docs/EVIDENCE_CAPTURE.md` if the installed collector exposes additional required checklist flags.

## Evidence boundary

The manual campaign PASS establishes the observed behavior for the exact captured candidate/build. It does not automatically make private source files redistributable and does not by itself change the source-controlled public evidence flag.

Any future public evidence promotion should preserve the candidate manifest, XML hashes, exact version/build, literal observations, semantic comparison and provenance boundary. Do not commit private source files, screenshots, operator notes or correspondence unless their redistribution status is explicitly resolved.
