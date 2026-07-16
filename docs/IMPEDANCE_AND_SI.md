# Impedance and Preliminary SI

## Implemented

`calculate_impedance` uses the quasi-static Hammerstad-Jensen microstrip model with
finite conductor thickness. The result includes the original inputs, method, effective
permittivity, target delta and tolerance, ±1% sensitivity, validity range, assumptions,
warnings, confidence, and the mandatory flag `preliminary_only=true`.

Reference equations: Qucs Technical Papers, transmission-line chapter, equations
11.4-11.25: <https://qucs.sourceforge.net/tech/node75.html>.

`structure="differential_microstrip"` uses the Hammerstad-Jensen parallel-coupled
microstrip model: even and odd modes, `Zdiff=2*Zodd`, validity range
`0.1<=W/h<=10`, and `gap/h>=0.01`. Modal impedances and effective permittivity are
returned in `validity`. The golden case is checked against Qucs-core
`mscoupled::analysQuasiStatic`:
<https://qucs.sourceforge.net/doxygen/0.0.18/qucs-core/mscoupled_8cpp_source.html>.

The coupled implementation is a zero-thickness quasi-static model. Non-zero copper
thickness is not silently ignored: the tool returns a warning and `confidence="low"`.

`suggest_trace_geometry_for_impedance` performs a bounded deterministic width search.
`analyze_stackup_for_impedance` uses only explicit stackup thickness and dielectric
constant values and reports missing inputs instead of substituting material properties.

## Length and Differential Pairs

- Geometric trace length accounts for DipTrace three-point arcs.
- Results include per-layer length, via count, transitions, and optional delay derived from explicit effective permittivity.
- Pair analysis includes skew, per-layer delta, via balance, width/gap, and coupled/uncoupled length.
- Rule and tolerance checks include confidence information.
- Arc length contributes to the total, but curved coupling is reported as a limitation.

## Not Implemented

- symmetric or asymmetric stripline;
- differential stripline impedance;
- solder-mask, roughness, or frequency-dispersion corrections;
- field-solver or full-wave analysis;
- meander or phase-tuning synthesis.

These modes return `solver_required` or `capability_unavailable`. An analytical estimate
must not be used as the sole basis for controlled-impedance fabrication.
