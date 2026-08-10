# Post-0.2.1 development changes

This temporary development record avoids rewriting the immutable `0.2.1` release history while the next release version has not been selected.

## Added

- raw-preserving internal Component/Pattern Library mutation core;
- deterministic pattern recommendation and privacy-bounded feedback/evaluation baseline;
- deterministic synthetic acceptance fixture-pack generator;
- write-path trust invalidation regression coverage;
- deterministic DFM/DFA/DFT release-readiness supplement;
- manual-only acceptance evidence generator and validator;
- internal PCB Generation A design-intent layer with component roles, functional blocks, multi-role net classification, electrical criticality, explicit engineering constraints and conservative power/ground topology intent;
- internal intent-aware PCB placement v2 layered over the existing geometry legalizer, with decomposed functional-block, support-adjacency, critical-connection and noise-proximity scoring;
- PCB Generation A regression coverage for unknown-physics preservation, explicit overrides, differential-pair evidence, ground/switch/sense/shield strategies and deterministic placement improvement;
- internal PCB Generation B physical-context analysis that reuses exported stackup, return-path and normalized via evidence without promoting analytic results to field-solver trust;
- conservative PDN rail/source/load/decoupling and regulator hot-loop candidates with explicit unknown-current/current-density/voltage-drop boundaries;
- timing-gated aggressor/victim physical triage and semantic signal/power/ground/return-transition/differential/thermal via roles;
- PCB Generation B regression coverage for stackup provenance, PDN unknown preservation, explicit current facts, reference-sensitive return paths, timing-gated noise analysis and bounded via-role classification.

## Documentation

- reconciled roadmap, distribution status, release checklist and technical-debt records with the already-published `v0.2.1` state;
- expanded the intelligent PCB roadmap through Generations A-D: intent/placement, stackup/PDN/return paths/vias, engineering-aware routing/SI/copper strategy, and joint whole-board optimization/acceptance;
- documented the internal EDA architecture, PCB design-intent domain models and the split between low-level placement legalization and intent-aware placement v2;
- documented Generation B stackup/reference, PDN, return-path, timing-gated noise and via-intelligence evidence boundaries;
- clarified that the private/manual Q1 Component Angle campaign is PASS while package-owned public evidence/trust promotion remains a separate reviewed contract.

The Generation A/B work intentionally leaves the 159-tool public MCP surface unchanged. It is internal EDA capability until a separate, deliberate public API decision is made.

This file should be folded into the normal `CHANGELOG.md` when the next version is selected.