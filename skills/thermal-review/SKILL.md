---
name: thermal-review
description: "Orchestrate DipTrace MCP for Thermal Review: Evaluate heat sources, copper spreading, thermal vias, clustering, and current-heating bottlenecks. Use when the user requests this workflow for a DipTrace schematic, PCB, library, review, or explicitly bounded project scope. Start with capability discovery; never simulate unavailable tools or write without a guarded preview."
---

# Thermal Review

## Purpose

Evaluate heat sources, copper spreading, thermal vias, clustering, and current-heating bottlenecks.

Priority: `P1`. Declared maturity: `heuristic; optional solver support`. Treat maturity as planning metadata, not runtime proof of availability.

## Applicability

Use this skill for the complete workflow described by the trigger, for a bounded subsystem, or to resume an interrupted run from current document state. It may consume an offline DipTrace XML document or the active live document. Resolve every file/session explicitly; never guess which revision is active.

Required inputs:

- power dissipation
- ambient and enclosure
- copper stack
- thermal data
- airflow

## Do not use

- Do not use it as a substitute for missing datasheets, manufacturer profiles, lab measurements, certification or solver evidence.
- Do not edit raw XML, reimplement parsing, DRC, geometry, placement, routing, impedance or transaction logic inside the skill.
- Do not claim global or solver-backed results from bounded or heuristic MCP checks.
- Do not operate outside the explicit document, selector, region, layer, variant and revision scope.

## Capability discovery

The first two MCP calls must be ordered and sequential: `diptrace_status`, then `get_capabilities`. Do not reverse or parallelize them. When a document is known, read its exact identity and SHA-256 with `get_document_info`, then call `get_capabilities` again with that exact path so document-specific policy, adapters and feature limits replace the generic report. Use the client runtime tool inventory as the callable-name source of truth.

| Target contract | Callable runtime tool | State | Required handling |
| --- | --- | --- | --- |
| `diptrace_status` | `diptrace_status` | `exact` | Use only when document capabilities allow it. |
| `get_capabilities` | `get_capabilities` | `exact` | Use only when document capabilities allow it. |
| `get_document_info` | `get_document_info` | `exact` | Use only when document capabilities allow it. |
| `run_thermal_review` | `run_thermal_review` | `exact` | Metadata and heuristic review profile, not CFD or thermal simulation. |
| `measure_geometry` | — | `missing` | Do not call the target name. Use dependency contract `geometry-query-v1`; block only dependent stages. |
| `get_component_neighborhood` | — | `missing` | Do not call the target name. Use dependency contract `geometry-query-v1`; block only dependent stages. |
| `analyze_power_tree` | — | `missing` | Do not call the target name. Use dependency contract `power-tree-v1`; block only dependent stages. |

Names in the Target contract column are conceptual contracts. Only a non-empty name in the Callable runtime tool column may be invoked. Re-resolve at every run; the table documents this repository revision but does not override runtime discovery.

## Workflow

0. Record the request, allowed scope and policy profile. Call `diptrace_status`, then `get_capabilities`.
1. Read the exact document with `get_document_info` and the required domain model; record revision/session and source SHA-256 before any semantic operation. For a genuinely pre-design task with no document, hash the normalized input bundle and set applicability to `pre_design`; never invent a document SHA.
2. Separate user facts, document facts, external facts and assumptions. For write-capable work, preserve the mandatory dry-run → preview → validation → expected-SHA commit → applicable ERC/DRC/connectivity → stop/rollback order from the write policy.
3. Identify heat sources and temperature-sensitive parts.
4. Evaluate operating modes.
5. Check copper and thermal vias.
6. Check thermal clustering.
7. Identify bottlenecks.
8. Prepare solver and measurement plans.
9. Validate the result against `schemas/result.schema.json`; store large graphs, models, previews and reports as resource URIs.
10. Evaluate every acceptance criterion and emit evidence or an explicit skipped check.

## Findings

Every finding must carry severity, confidence, rationale, suggested action and an object locator. The locator contains exact RefDes, nets, stable object IDs, layers and coordinates when those exist. For pre-design work, keep those arrays empty and set locator applicability to `pre_design`; never invent an object or coordinate.

Separate deterministic MCP findings from engineering heuristics. Preserve explicit no-connects, DNP, waivers and user constraints. A waiver is not suppression: retain the underlying finding and link the waiver ID. Set `blocks_completion` only when the finding prevents completion of the requested workflow or mandatory evidence collection; an open design-critical finding may coexist with a completed review report.

## Stop conditions

- Return `blocked_by_input` when an ambiguous or missing fact can change topology, safety, ratings, pin mapping, units, coordinate datum, scope or acceptance. Continue independent stages only.
- Return `blocked_by_capability` when the requested dependent stage has no compatible runtime tool or adapter. Include contract ID, inputs, outputs, invariants and affected stages.
- Return `partial` when independent deliverables are valid but optional or dependent checks remain unavailable. List every skipped check and its impact.
- Return `failed` for an actual tool, validation, SHA, commit or rollback failure. Do not convert an exception into a successful narrative.
- Never return `completed` with a missing mandatory check, unresolved critical/error regression, stale SHA, failed post-check, ambiguous identity or unverified requested output.

## Write policy

This skill is read-only by default.

- Always complete `diptrace_status` → `get_capabilities` before analysis.
- When the workflow is bound to a document, resolve it with `get_document_info` and capture its SHA-256 before reading domain models. For a genuine pre-design workflow, record `pre_design` applicability and hash the normalized input bundle instead of inventing a document identity.
- Do not call mutating tools, open a write transaction, or export a state-changing artifact.
- Keep `planned_changes` descriptive and keep `transactions` empty.
- If the user later requests a mutation, hand off to a write-capable skill and preserve this report as baseline evidence.
- A review-only request can be `completed`; a requested mutation cannot be reported as completed by this skill.
- Steps 3–7 of the write sequence are `not_applicable` in read-only scope. Never create a no-op transaction merely to satisfy the sequence.

## Dependency contracts

### `geometry-query-v1`

Exact typed board-geometry measurement and neighborhood queries.

Required inputs: document_id and source_sha256; stable-id selectors; measurement kind; layers; units and coordinate frame.

Required outputs: matched stable IDs; exact coordinates or bounds; measured value and units; geometry backend and tolerance; confidence and resource URI.

Invariants: no hidden unit conversion; report the coordinate datum; distinguish exact geometry from bbox proxy.

### `power-tree-v1`

Deterministic directed power graph and rail-budget analysis.

Required inputs: document_id and source_sha256; rail and pin-role provenance; operating modes; load-current ranges; sequencing constraints.

Required outputs: typed sources, rails and consumers; directed edges; per-mode current and power ranges; unknowns and confidence; resource URI for the complete graph.

Invariants: never infer an unknown power-pin role; preserve units and source references; do not return pass while a mandatory consumer current is unknown.

The canonical machine-readable contracts are in `../dependency-contracts.json`. A dependency report is a request for an MCP/runtime extension, not permission to implement a brittle parser, geometry approximation or raw XML patch in this skill.

## Outputs

- `thermal report`
- `heat proxy map`
- `copper and via suggestions`
- `solver cases`

Return the required common fields: `status`, `summary`, `document_identity`, `inputs_used`, `assumptions`, `findings`, `planned_changes`, `transactions`, `resources`, `skipped_checks`, `confidence` and `next_actions`. Also return `dependency_report`, `acceptance_evidence` and all skill-specific `deliverables`.

Status semantics:

- `completed`: the requested scope and every mandatory acceptance check have evidence.
- `partial`: valid independent work exists, with precise limitations.
- `blocked_by_capability`: an exact dependency contract blocks the requested stage.
- `blocked_by_input`: a named missing or ambiguous input blocks the requested stage.
- `failed`: execution or validation failed and success was not claimed.

`completed` describes execution of the requested workflow, not approval of the design. In particular, `release-gate` carries the independent `PASS|BLOCKED` decision in its release-decision deliverable.

## Acceptance criteria

- The dissipation source is stated.
- Results without CFD are marked heuristic.
- Unknown boundary conditions remain explicit.

## Failure modes

- Capability advertised globally but disabled for the selected document: trust document discovery and degrade explicitly.
- Tool name exists but semantics are weaker than the target contract: use only the documented subset and never upgrade the claim.
- Large output is truncated: return a bounded summary plus resource URI.
- Source changes after analysis or preview: stop on SHA mismatch and rebuild the plan from the new source.
- Locked object, keepout, waiver, DNP or explicit no-connect conflicts with the plan: preserve it and return the conflict.
- External adapter, profile or solver is absent or unversioned: block the dependent result; do not synthesize a substitute.

## Examples and evals

- `examples/result.example.json` is a schema-valid representative result.
- `evals/scenarios.json` defines the happy path, read-only policy, missing capability, ambiguous input and safety/regression cases.
- `evals/assertions.json` defines tool selection, graceful degradation, write gating, scope/locks, output validation, post-check and false-success assertions.

Runtime prompt example:

> Run a thermal review of <RefDes/region> under conditions <description>.
