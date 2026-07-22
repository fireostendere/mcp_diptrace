# Field-Solver Runner Protocol

The optional openEMS integration uses a fixed JSON-file protocol instead of accepting an
arbitrary command. Configure a compatible runner with `DIPTRACE_MCP_OPENEMS_RUNNER`.
Python runners are launched with the server interpreter; native runners must be executable.

The server invokes only:

```text
<runner> --input <isolated-job-dir>/field_solver_input.json \
         --output <isolated-job-dir>/field_solver_result.json
```

The runner must exit non-zero on setup, meshing, execution, or post-processing failure and
write diagnostics to stdout/stderr. It must write the result atomically or only after the
simulation and post-processing succeed. The server does not accept additional user CLI
arguments or shell fragments.

## Request v1

`schema_version` is `diptrace-field-solver-request-v1`. The current structure is
`stripline`. `lower_dielectric_height_mm` and `upper_dielectric_height_mm` are the clear
distances from the respective conductor surface to the lower and upper reference planes;
different values describe an off-center trace. Total plane separation is their sum plus
`copper_thickness_mm`.

Required geometry and materials are trace width/thickness, both dielectric heights,
relative dielectric constant, loss tangent, and conductor conductivity. The request also
contains a strictly increasing unique frequency sweep, line length, reference impedance,
and bounded mesh-accuracy control. All numbers are finite SI-derived values; geometry is
expressed in millimeters and frequency in hertz.

## Result v1

`schema_version` is `diptrace-field-solver-result-v1` and `backend` is `openems`. The
result contains the actual solver version, convergence flag, mesh/convergence metadata,
warnings, and one point for every requested frequency. Each point contains:

- real and imaginary characteristic impedance in ohms;
- propagation alpha in nepers per meter and beta in radians per meter;
- optional conductor and dielectric loss in decibels per meter.

The server rejects malformed JSON, unknown fields, non-finite or out-of-range values,
non-converged results, and frequency vectors that differ from the request. A successful
job preserves request, result, manifest, and bounded log artifacts with hashes.

## Runtime and Testing

Jobs run with `shell=false`, an isolated job directory, sanitized environment, bounded
log/result sizes, timeout, cancellation, and persistent error records. Core CI uses a
synthetic protocol fixture and fake runners to test portability and failures; it does not
present those values as real openEMS output. A solver-enabled integration environment
must replace the synthetic golden data with a captured result and record the openEMS
version, mesh settings, convergence evidence, and analytical centered-stripline delta.
