# Q1 HUMAN ACTION REQUIRED

Q1 is not run and is not closed. A live DipTrace PCB Layout GUI edit and a
fresh DipTrace XML re-export are required before `rotate_components` can be
used as validated angle evidence.

## Controlled experiment

1. On Windows, install or open the exact DipTrace PCB Layout build. Record the
   application version and build from the application's About dialog.
2. Create a new, disposable PCB owned by the project maintainer. Place two
   instances of the same component and pattern. Name them `U_CTRL` and
   `U_PROBE`; keep footprint, value, side, and all non-rotation properties
   equal. Put the control at UI rotation 0 degrees and the probe at UI
   rotation 90 degrees. If the build supports a bottom-side instance, repeat
   the probe on the bottom side and record the side/mirror state.
3. Export the design directly from DipTrace as `source.xml`. Do not pass it
   through MCP or edit its bytes by hand. Preserve the original file.
4. Open `source.xml` in DipTrace, save it under a distinct name, and export
   that saved design as `reexport.xml`. Record the literal `Component/@Angle`
   values for both references without converting them.
5. Independently perform the GUI sequence `0 → 90 → 180 → 270 → 0` (or `360`)
   on a disposable copy. Re-export after each step when the build permits it.
   Record sign, direction, units, numeric range, 0/360 normalization, side and
   mirror behavior, and unchanged RefDes, footprint, coordinates, and
   connectivity.
6. Capture the source/open-save/reexport triple with the existing recipe:

   ```text
   python scripts/capture_diptrace_evidence.py init --root <private-capture-root> --session q1-component-angle-001 --recipe q1-component-angle.recipe.json
   python scripts/capture_diptrace_evidence.py record --root <private-capture-root> --session q1-component-angle-001 --stage source --file <source.xml>
   python scripts/capture_diptrace_evidence.py record --root <private-capture-root> --session q1-component-angle-001 --stage open_save --file <open-save.xml>
   python scripts/capture_diptrace_evidence.py record --root <private-capture-root> --session q1-component-angle-001 --stage reexport --file <reexport.xml>
   python scripts/capture_diptrace_evidence.py check --root <private-capture-root> --session q1-component-angle-001
   python scripts/capture_diptrace_evidence.py finalize --root <private-capture-root> --session q1-component-angle-001
   ```

   Use the exact command syntax in `docs/EVIDENCE_CAPTURE.md` if the installed
   collector exposes additional required checklist flags.

## Acceptance boundary

The candidate manifest, XML hashes, exact version/build, literal observations,
semantic comparison, and independent review are required. A candidate is not a
trusted fixture automatically. Do not commit private source files, screenshots,
operator notes, or correspondence. Do not claim Novarm/DipTrace permission.

Until the result is independently accepted, leave the result file at
`status=NOT_RUN` or `status=FAIL` and keep the `component_angle_live_validation_pending`
warning.
