# PCB Design Engine

## Scope

The PCB design engine turns normalized board connectivity plus explicit engineering facts into deterministic, explainable placement/routing policy. It is intentionally layered above the existing XML adapters, local placement legalizer, router, review engine and guarded semantic transaction path.

The goal is not to claim globally optimal PCB layout or replace a mature field solver/autorouter. The goal is to make defensible engineering decisions, expose the assumptions behind them, and improve a board through a bounded generate -> score -> improve loop.

PCB-generation capabilities remain internal while the architecture is proven. The current 159-tool public MCP `tools/list` contract stays frozen; generations do not add one MCP tool per heuristic.

## Architecture

```text
schematic / PCB connectivity
        +
operator / project constraints
        |
        v
PCB design intent                         Generation A
        |
        +--> component roles / functional blocks
        +--> net roles / electrical criticality
        +--> power / ground strategy intent
        |
        v
intent-aware placement                    Generation A
        |
        v
physical context / stackup / PDN / return Generation B
        |
        v
routing policy / SI / copper decisions    Generation C
        |
        v
joint score and bounded repair            Generation D
        |
        v
guarded semantic plan -> preview -> SHA-bound apply -> review
```

Physical facts are never invented to make the model look complete. Unknown edge rate, current, impedance, stackup or datasheet facts remain unknown until supplied or supported by authoritative project data.

## Generation A — PCB understands electronics

**Status: implemented, regression-tested and merged to `main` in PR #81.**

`pcb_design_intent.py` builds a typed engineering view of component roles, functional blocks, multi-role nets, electrical criticality, explicit physical constraints and conservative power/ground topology intent. `pcb_placement.py` adds deterministic bounded placement above the existing geometry legalizer and emits ordinary `MoveComponentsOperation` objects instead of writing XML directly.

Generation A deliberately preserves unknown physics. Ordinary ground defaults to `continuous_plane_preferred`; switch nodes to `local_copper_minimized`; sense nets to `kelvin_candidate`; power rails to `local_plane_or_pour_candidate`; star grounding is never inferred automatically.

## Generation B — PCB understands fields and current paths

**Status: implemented, regression-tested and merged to `main` in PR #83.**

`analyze_pcb_physics()` consumes Generation A intent plus existing normalized stackup, geometry, via and return-path evidence. It is non-mutating and provides:

- typed microstrip/stripline reference candidates from exported stackup;
- conservative PDN rail source/load/decoupling candidates;
- regulator hot-loop candidates without pretending pad-level current direction is proven;
- bounded reuse of `analyze_return_path()` for reference-sensitive nets;
- aggressor/victim triage only when explicit edge-rate/frequency evidence exists;
- semantic signal/power/ground/return-transition/differential/thermal via roles.

Analytic impedance candidates stay `preliminary_only`; current density, voltage drop and numeric via capacity remain unknown until sufficient physical evidence exists. No via fence, split ground, EMC compliance or field-solver result is invented.

## Generation C — PCB routes intentionally

**Status: implemented, regression-tested and merged to `main` in PR #84.**

Generation C translates A/B engineering evidence into deterministic routing policy while leaving actual trace/via/pour mutation in the existing routing compiler and guarded semantic transaction path.

### Routing policy compiler

`compile_pcb_routing_policy()` produces one typed policy per net with:

- deterministic engineering priority and stable route order;
- explicit minimum spacing and preferred/forbidden layers;
- explicit via budget and Generation A via penalty;
- target impedance/tolerance when known;
- max length/skew when known;
- reference requirement/reference net and preliminary stackup candidates;
- stub sensitivity and shielding preference.

Missing width, spacing, impedance, timing or other physical limits remain unknown. Generation C does not manufacture a trace width merely because a net is critical.

### Route ordering

Nets are sorted by criticality, electrical roles and explicit constraints rather than XML order or one hard-coded protocol list. Switching/RF/differential/clock/precision nets naturally receive higher priority when their intent/evidence supports it.

### Observed-route SI checks

`evaluate_route_observation()` evaluates supplied route observations for:

- maximum length;
- via budget;
- forbidden-layer use;
- continuous reference requirement;
- explicit impedance tolerance;
- skew;
- stubs on stub-sensitive nets;
- measured parallel-route exposure.

Absent observation or absent constraint stays `unknown`. Parallel exposure is reported without inventing one universal crosstalk pass/fail threshold.

### Copper strategy

Generation C preserves Generation A/B topology intent when deciding whether a net is fundamentally a trace, local-copper-minimized path, local plane/pour candidate, continuous plane, shield/chassis domain, Kelvin candidate or explicit star topology.

Any strategy involving native poured/plane copper is marked as requiring authoritative DipTrace refill/geometry evidence before acceptance. Unknown rail current does not become a fabricated current-capacity conclusion.

### Placement feedback

Failed route observations can return bounded endpoint-placement feedback. Reference-continuity and via-budget failures are treated as strong feedback signals; the optimizer may consider a bounded endpoint move, but routing policy itself does not move components.

## Generation D — whole-board optimization

**Status: implemented, regression-tested and merged to `main` in PR #86.**

Generation D selects among bounded whole-board candidates without bypassing the existing guarded write path.

### Hard-rule dominance

`PCBHardViolations` keeps safety, mechanical, connectivity, DRC, reference-path and manufacturing violations as separate integer dimensions. Candidate ranking is lexicographic across those dimensions before any soft metric is considered. A candidate that introduces a hard violation cannot win because it has shorter routing, fewer vias or a prettier placement score.

### Decomposed soft score

`PCBSoftScore` keeps placement, routing, via count, signal integrity, power integrity, return path, EMI risk, thermal risk and manufacturing cost separate. Their finite sum is only a deterministic tie-break between candidates with identical hard-violation vectors.

The optimizer rejects non-finite soft metrics, duplicate candidate IDs, empty candidate sets and candidate counts above the configured bound. External routers, external solvers and operator candidates can participate only as candidate/evidence sources; they do not gain authority to apply edits.

### Benchmark catalog

`pcb_benchmark_catalog()` defines engineering-trap families for:

- MCU + decoupling + crystal;
- regulator/power;
- ADC mixed signal;
- precision current sense;
- high-speed differential;
- Ethernet/CAN/interface;
- RF/antenna;
- higher-current power distribution;
- multilayer controlled-impedance routing.

These catalog entries are explicitly `synthetic_regression_only`. Each retains `requires_real_diptrace_acceptance=True`; a synthetic PASS cannot be promoted into a claim about native copper refill, planes, via structures or DipTrace round-trip behavior.

## Testing and acceptance

Generation A automated coverage includes component/net role inference, functional grouping, explicit overrides, unknown-value preservation, ground-topology safety, differential-pair evidence, decomposed placement scoring and hard-geometry/budget refusal.

Generation B adds stackup provenance, unknown-current/source preservation, explicit current/converter facts, reference-sensitive return paths, timing-gated noise analysis, bounded via-role classification and invalid-radius rejection.

Generation C adds deterministic route ordering, constraint propagation, preliminary reference policy, unknown-width preservation, observed SI failure/unknown behavior, bounded placement feedback, copper/refill evidence boundaries and wrong-net rejection.

Generation D adds hard-rule dominance, deterministic ranking/tie-breaking, plan-reference preservation, bounded candidate counts, non-finite score rejection and benchmark acceptance-boundary tests.

A real-DipTrace acceptance fixture remains required before claims about poured copper, plane behavior, via structures or native round-trip semantics are promoted beyond the existing evidence boundary.

## Non-claims

The PCB design engine does **not** currently claim:

- field-solver accuracy;
- PDN/PI sign-off;
- EMC compliance;
- automatic proof that a plane, star point or Kelvin connection is electrically optimal;
- authoritative copper refill geometry;
- thermodynamic/CFD analysis;
- fabrication or assembly sign-off;
- globally optimal placement/routing.

Generations A-D provide deterministic intent, placement, physical-context, routing-policy and bounded whole-board candidate-selection foundations. Applying any resulting semantic plan remains subject to the normal preview, SHA, policy, transaction and review boundaries.