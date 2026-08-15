# PCB Design Engine

## Scope

The PCB design engine turns normalized board connectivity plus explicit engineering facts into deterministic, explainable placement/routing policy and bounded candidate selection. It remains layered above the XML adapters, geometry legalizer, routing compiler, review engine and guarded semantic transaction path.

It does not claim globally optimal PCB layout or replace a field solver/autorouter. Unknown edge rate, current, impedance, stackup or datasheet facts remain unknown until supplied or supported by authoritative project evidence.

The higher-level generations remain internal engines; the bounded read-only ensemble comparison is productized as the `compare_pcb_placement_candidates` tool. The public MCP contract currently registers 167 tools.

See [EDA_INTELLIGENCE.md](EDA_INTELLIGENCE.md) for the cross-domain implementation map.

## Architecture

```text
normalized PCB + explicit project/operator facts
        |
        v
Generation A: design intent + bounded placement candidates
        |
        v
Generation B: stackup / PDN / return-path / noise context
        |
        v
Generation C: routing policy / observed-route checks / copper strategy
        |
        v
Generation D: hard-first whole-board candidate selection
        |
        v
guarded semantic plan -> preview -> expected SHA -> transaction -> review
```

## Generation A — electronics intent and placement

`pcb_design_intent.py` builds typed component roles, functional blocks, multi-role nets, criticality, explicit electrical constraints and conservative power/ground topology intent.

`pcb_placement.py` produces deterministic bounded placement candidates and ordinary `MoveComponentsOperation` objects. It does not write XML directly.

Conservative defaults remain intentional: ordinary ground prefers continuity, switch nodes remain local-copper-minimized candidates, sense nets become Kelvin candidates, and star grounding is never invented automatically.

## Generation B — physical context

`pcb_physical.py` consumes Generation-A intent plus exported stackup/geometry/via evidence and provides:

- preliminary reference candidates;
- PDN source/load/decoupling candidates;
- regulator hot-loop candidates;
- bounded return-path analysis;
- aggressor/victim triage only when timing evidence exists;
- semantic via roles.

Analytical impedance remains preliminary. Current density, voltage drop, via current capacity, thermal behavior and EMI compliance remain unknown without sufficient physical evidence.

## Generation C — intentional routing policy

`pcb_routing_policy.py` produces deterministic per-net routing policy including priority/order, known spacing/width/layer constraints, via budget, impedance/skew/length constraints when known, reference requirements and copper strategy.

Observed-route checks report pass/fail/unknown according to available evidence. Missing constraints stay unknown rather than being fabricated.

Strategies involving native poured/plane copper remain subject to real DipTrace refill/geometry evidence before acceptance.

## Generation D — hard-first whole-board comparison

`pcb_joint_optimizer.py` ranks bounded candidates lexicographically by hard violations before any soft score.

Hard dimensions remain separate:

- safety;
- mechanical;
- connectivity;
- DRC;
- reference path;
- manufacturing.

Soft dimensions remain decomposed:

- placement;
- routing;
- vias;
- signal integrity;
- power integrity;
- return path;
- EMI risk;
- thermal risk;
- manufacturing.

The soft total is only a deterministic tie-break between equal hard-violation vectors.

The Generation-D benchmark catalog remains `synthetic_regression_only` and explicitly requires real-DipTrace acceptance for native copper/plane/via claims.

## A-D candidate ensemble

`pcb_candidate_ensemble.py` closes the previous gap where Generation D had a strong selector but did not itself receive a useful family of internally generated whole-board candidates.

The ensemble now generates actual bounded Generation-A placement plans under multiple disclosed engineering profiles:

- `balanced` — existing default weights;
- `critical_nets` — stronger critical-connection pressure;
- `noise_aware` — stronger aggressor/sensitive separation pressure;
- `support_compact` — stronger local support-component/block cohesion pressure;
- `existing_board` — unchanged-board baseline for comparison.

Every non-baseline candidate comes from the existing bounded placement planner. Generation B/C output contributes conservative evidence-proxy score terms. The existing Generation-D `select_pcb_candidate` remains the sole selector and keeps hard violations dominant.

This is deliberately not an invented autorouter. Candidate scoring may penalize unresolved routing/reference evidence, but it does not synthesize traces, vias, stackup facts, current ratings or solver output.

The selected candidate still requires ordinary semantic application, review/DRC and claim-specific real DipTrace evidence.

## DSN/SES integration

The existing DSN exporter, SES parser and bounded semantic SES importer remain authoritative for Specctra exchange.

`specctra_analysis.py` adds non-mutating screening before import:

- bounded S-expression root/token/depth/scope inventory;
- route net/wire/via/segment counts;
- route length and width range;
- used layers;
- duplicate SES nets;
- unknown target PCB nets/layers;
- importable/skipped classification using the existing importer itself.

A clean pre-import analysis does not replace post-import connectivity/DRC/native round-trip validation.

## Testing

Automated coverage now includes:

- Generation-A intent/placement and unknown-physics preservation;
- Generation-B stackup/PDN/return-path/noise/via-role behavior;
- Generation-C routing policy and observed-route behavior;
- Generation-D hard-rule dominance and deterministic ranking;
- deterministic generation of multiple A-D ensemble profiles;
- reuse of the exact existing Generation-D selection key;
- deterministic profile deduplication;
- DSN/SES structural/importability analysis.

Repository CI is authoritative. Synthetic tests do not transfer PASS status to a newer real DipTrace candidate by inference.

## Non-claims / remaining acceptance

The PCB design engine does not currently claim:

- field-solver accuracy;
- PDN/PI sign-off;
- EMC compliance;
- thermodynamic/CFD analysis;
- authoritative native copper refill geometry;
- proof that a plane/star/Kelvin topology is electrically optimal;
- manufacturing/fabrication sign-off;
- globally optimal placement/routing.

Real-DipTrace whole-board product-quality acceptance remains appropriate before stronger claims about current A-D candidate quality, native refill, planes or via structures are made.
