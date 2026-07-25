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
returned in `validity`. The equations and all three bounds come from the
[Qucs Hammerstad-Jensen coupled-microstrip section](https://qucs.sourceforge.net/tech/node77.html).
The `0.1<=gap/h<=10` range shown earlier on that page belongs to the different
Kirschning-Jansen model and is not presented as a bound for this implementation.

The [swept physical-invariant suite](../tests/test_impedance_invariants.py) checks
3,360 combinations of width, gap, height, dielectric constant, and the three requested
test thicknesses. It checks modal-permittivity ordering only inside the published band,
checks width/height/gap monotonicity, and checks the far-separation permittivity and
`Zdiff -> 2*Z0` limits. The last impedance limit is intentionally restricted to zero
thickness because the coupled branch does not implement a thickness correction.

The coupled implementation is a zero-thickness quasi-static model. Non-zero copper
thickness is not silently ignored: the tool returns a warning and `confidence="low"`.

`suggest_trace_geometry_for_impedance` performs a bounded deterministic width search.
`analyze_stackup_for_impedance` uses only explicit stackup thickness and dielectric
constant values and reports missing inputs instead of substituting material properties.

`structure="symmetric_stripline"` uses the closed-form IPC-2141 centered stripline
model: `Z0 = (60/sqrt(Er)) * ln(1.9*B / (0.8*W + T))`, where `dielectric_height_mm` is
the total plane-to-plane separation `B = 2H + T`. The published validity range is
`W/(B-T) < 0.35` and `T/(B-T) < 0.25`; outside the range the tool returns a warning and
`confidence="low"`. The effective permittivity equals the bulk `Er` of the homogeneous
dielectric. `analyze_stackup_for_impedance` emits `stripline_candidates` for internal
signal layers when both sides have uniform dielectrics with known thickness/Dk,
including the plane separation and off-center offset.

## Length and Differential Pairs

- Geometric trace length accounts for DipTrace three-point arcs.
- Results include per-layer length, via count, transitions, and optional delay derived from explicit effective permittivity.
- Pair analysis includes skew, per-layer delta, via balance, width/gap, and coupled/uncoupled length.
- Rule and tolerance checks include confidence information.
- Arc length contributes to the total, but curved coupling is reported as a limitation.

## External Simulation

The ngspice adapter runs user-supplied netlists in batch mode
(`run_ngspice_simulation`) with a fixed CLI contract, an isolated job directory,
timeout, cancellation, bounded logs, and a typed log summary. It is enabled through
`DIPTRACE_MCP_NGSPICE` or an `ngspice` executable on `PATH` and never fabricates
results: an unavailable executable ends in `external_tool_unavailable`.

`run_openems_stripline_analysis` submits explicit centered or off-center stripline
geometry and a frequency sweep to a configured `DIPTRACE_MCP_OPENEMS_RUNNER`. Its result
is solver-produced rather than an analytical estimate and includes complex characteristic
impedance, propagation constant, optional separated losses, mesh/convergence metadata,
and solver version. The adapter validates the typed protocol and does not fall back to the
closed-form estimate when the runner is unavailable. See
[Field-Solver Runner Protocol](FIELD_SOLVER_PROTOCOL.md).

## Not Implemented

- differential stripline impedance;
- solder-mask, roughness, or frequency-dispersion corrections;
- a bundled field solver or a verified real-openEMS golden fixture;
- netlist generation from a design;
- meander or phase-tuning synthesis.

These modes return `solver_required` or `capability_unavailable`. An analytical estimate
must not be used as the sole basis for controlled-impedance fabrication.
