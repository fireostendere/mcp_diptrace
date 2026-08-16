# PCB Design Engine

## Scope

The PCB design engine turns normalized board connectivity plus explicit engineering facts
into deterministic, explainable placement/routing policy and bounded candidate selection.
It remains layered above the XML adapters, geometry legalizer, routing compiler, review
engine and guarded semantic transaction path.

It does not claim globally optimal PCB layout or replace a field solver/autorouter.
Unknown edge rate, current, impedance, stackup, material, temperature or datasheet facts
remain unknown until explicitly supplied and source-bound.

The higher-level generations remain internal engines; the public MCP contract remains at
167 tools.

## Default authoring policy

The bounded PCB generators prefer compact, centered, explainable layouts while preserving
explicit electrical, mechanical, DRC, datasheet and manufacturing constraints. Current
project defaults include:

- smallest-area equally compatible simple footprint when geometry is otherwise unconstrained;
- compact centered outline with sane edge margin and useful symmetry;
- ordinary two-layer strategy with signals/positive power on Top and an effectively
  continuous Bottom GND reference plus useful Top GND;
- distributed GND stitching rather than count-only placement;
- four-spoke thermal intent on soldered connector GND pads;
- readable silkscreen kept away from bodies, pads, holes and vias.

These are bounded authoring preferences, not permission to override hard rules or final DFM.

## Architecture

```text
normalized PCB + explicit/source-bound facts
        |
        v
Generation A: intent + bounded placement candidates
        |
        v
Generation B: stackup / PDN / return-path / noise context
        |
        v
Generation C: routing policy / observed-route checks / copper strategy
        |
        v
candidate-specific deterministic quality review
        |
        v
Generation D: hard-first candidate selection
        |
        v
whole-board composition
        |
        v
guarded source-SHA/candidate-SHA plan -> preview -> apply -> rollback/review
```

## Generation A — electronics intent and placement

`pcb_design_intent.py` builds typed component roles, functional blocks, multi-role nets,
criticality and explicit electrical constraints.

`pcb_placement.py` produces deterministic bounded placement candidates and ordinary
`MoveComponentsOperation` objects. Compactness, centering, symmetry and topology-backed
high-di/dt loop span remain separate disclosed score terms. Locked placement and explicit
hard constraints dominate these preferences.

## Generation B — physical context

`pcb_physical.py` consumes intent plus exported stackup/geometry/via evidence and provides
preliminary reference candidates, PDN topology proxies, regulator hot-loop candidates,
bounded return-path analysis, timing-dependent aggressor/victim triage and semantic via
roles.

No missing current density, voltage-drop, via-current, thermal or EMI fact is guessed.

### Physics knowledge and provenance

`pcb_physics_knowledge.py` carries only bounded qualitative principles such as continuous
reference paths, small high-di/dt loops and short decoupling loops. A principle without
complete source binding is not claim-eligible.

`reference_rules.py` requires source SHA-256, revision, locator, units/limit semantics,
conditions and applicability for claim-eligible engineering facts. Model memory cannot
stand in for a missing source.

## Generation C — routing policy

`pcb_routing_policy.py` produces deterministic per-net routing policy including priority,
known width/spacing/layer constraints, via budget, impedance/skew/length constraints when
known, reference requirements and copper strategy.

Observed-route checks return pass/fail/unknown according to available evidence. Native
poured copper remains subject to real DipTrace refill/inspection.

## Generation D — hard-first candidate comparison

`pcb_joint_optimizer.py` ranks bounded candidates lexicographically by hard dimensions
before any soft score.

Hard dimensions remain separate: safety, mechanical, connectivity, DRC, reference path and
manufacturing. Soft terms remain disclosed tie-breaks: placement, routing, vias, SI/PI
proxies, return path, EMI risk, thermal risk and manufacturing preference.

Synthetic benchmark catalogs remain regression-only and never become native DipTrace proof.

## Candidate ensemble

`pcb_candidate_ensemble.py` generates multiple real Generation-A alternatives under
bounded engineering profiles plus an existing-board baseline. Each candidate is applied to
an in-memory document before B/C/quality analysis, so alternatives are not accidentally
scored against unchanged baseline geometry.

Quality errors feed hard dimensions. Compactness, centering, symmetry, plane, stitching,
thermal, silkscreen and loop metrics feed disclosed soft comparison. Candidate selection
never invents traces, vias, stackup facts, current ratings or solver results.

## Whole-board pipeline and guarded apply

`pcb_whole_board.py` composes the existing bounded stages:

1. select placement candidate;
2. apply placement and planned routes in memory;
3. compact an unlocked simple rectangular outline around occupied geometry;
4. request Top/Bottom GND pours and distributed stitching for ordinary two-layer boards;
5. repair/normalize silkscreen;
6. run final deterministic quality review.

The roadmap closure adds a guarded package-level plan/apply contract around that composition.
The plan records:

- exact source SHA-256;
- exact candidate SHA-256;
- deterministic plan identity and stage list;
- semantic/connectivity deltas, warnings and assumptions;
- final `PCBQualityReview` and native-required/refill-required status.

Apply rechecks stale source identity and hard review blockers, writes through the existing
backup/transaction boundary, validates post-write identity and rolls back on bounded failure.
Preview and commit are tied to the same planned result identity.

Authoritative DipTrace refill, real thermal spoke geometry, plane connectivity and native DRC
are not fabricated by the package layer. M1 remains required before stronger whole-board
native-quality/refill claims or default public mutation.

## Quantitative engineering estimates

`physics_estimates.py` adds bounded explicit-input calculations for:

- trace DC resistance;
- via DC resistance;
- voltage drop;
- aggregate loss budget;
- first-order thermal estimates.

Every result records exact inputs, formula/method identity, source revision/SHA/locator,
assumptions, limitations and sensitivity terms. Missing geometry, material, current or source
facts return `unknown`; there are no silent typical-value substitutions.

M3 governs source applicability. M8 governs physical correlation/sign-off. These helpers are
engineering estimates, not field-solver or laboratory proof.

## Copper pours and stitching

`copper_pours.py` can request explicit-net pour boundaries, four-spoke thermal intent and
bounded stitching vias after excluding known obstacles. It owns requested boundary/via
intent only. DipTrace remains authoritative for refill regions, cutouts, islands and actual
thermal-spoke geometry.

## DSN/SES integration

The existing DSN exporter, SES parser and bounded importer remain the Specctra exchange
path. `specctra_analysis.py` adds non-mutating structure/importability screening. A clean
pre-import analysis does not replace post-import connectivity/DRC/native round-trip
validation.

## Testing

Automated coverage includes:

- A-D intent/placement/physical/routing/hard-first selection;
- candidate-specific in-memory quality review;
- compact pattern selection, GND-pour/stitching and silkscreen helpers;
- whole-board staged composition;
- source-SHA/candidate-SHA guarded plan/apply and stale-input/rollback paths;
- source-bound physics principles and explicit unknown facts;
- quantitative resistance/voltage-drop/loss/thermal estimates;
- DSN/SES structure/importability analysis;
- the repository compact I2C level-shifter demo path.

Repository CI remains authoritative for code behavior. Synthetic tests do not transfer PASS
status to a newer real DipTrace candidate by inference.

## Non-claims / remaining acceptance

The PCB design engine does not claim:

- globally optimal placement/routing;
- authoritative native refill geometry;
- field-solver, PDN/PI, SI, EMC or thermal sign-off;
- proof that a plane/star/Kelvin topology is electrically optimal;
- manufacturing/fabrication acceptance.

The repository I2C example and cinematic output have scoped operator acceptance. Stronger
whole-board native refill/DRC claims require M1. Source applicability and physical-performance
claims require M3/M8. Trigger-based P2 work such as push-and-shove or broader global
optimization should start only after measured real-project failures show the bounded engine
is the limiting factor.
