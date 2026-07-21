---
name: schematic-authoring
description: "Orchestrate DipTrace MCP for Schematic Authoring: Build a readable schematic incrementally from the architecture while continuously validating connectivity and ERC. Use when the user requests this workflow for a DipTrace schematic, PCB, library, review, or explicitly bounded project scope. Start with capability discovery; never simulate unavailable tools or write without a guarded preview."
---

# Schematic Authoring

## Purpose

Build a readable schematic incrementally from the architecture while continuously validating connectivity and ERC.

Priority: `P0`. Declared maturity: `requires schematic write support`. Treat maturity as planning metadata, not runtime proof of availability.

## Applicability

Use this skill for the complete workflow described by the trigger, for a bounded subsystem, or to resume an interrupted run from current document state. It may consume an offline DipTrace XML document or the active live document. Resolve every file/session explicitly; never guess which revision is active.

Required inputs:

- architecture
- approved components
- interface matrix
- power tree and schematic conventions

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
| `get_schematic_model` | `get_schematic_model` | `exact` | Use only when document capabilities allow it. |
| `set_component_value` | `set_component_value` | `exact` | Use only when document capabilities allow it. |
| `set_component_fields` | `set_component_fields` | `exact` | Use only when document capabilities allow it. |
| `add_wire` | `add_wire` | `exact` | Use only when document capabilities allow it. |
| `add_net_label` | `add_net_label` | `exact` | Use only when document capabilities allow it. |
| `assign_pattern` | — | `incompatible` | Do not call the target name. Use dependency contract `schematic-authoring-v1`; block only dependent stages. |
| `run_erc` | `run_erc` | `exact` | Use only when document capabilities allow it. |
| `begin_transaction` | `begin_transaction` | `exact` | Use only when document capabilities allow it. |
| `stage_operations` | `stage_operations` | `exact` | Use only when document capabilities allow it. |
| `preview_transaction` | `preview_transaction` | `exact` | Use only when document capabilities allow it. |
| `validate_transaction` | `validate_transaction` | `exact` | Use only when document capabilities allow it. |
| `commit_transaction` | `commit_transaction` | `exact` | Use only when document capabilities allow it. |
| `rollback_transaction` | `rollback_transaction` | `exact` | Use only when document capabilities allow it. |
| `run_drc` | `run_drc` | `exact` | Use only when document capabilities allow it. |
| `run_connectivity_check` | `run_connectivity_check` | `exact` | Use only when document capabilities allow it. |

Names in the Target contract column are conceptual contracts. Only a non-empty name in the Callable runtime tool column may be invoked. Re-resolve at every run; the table documents this repository revision but does not override runtime discovery.

## Workflow

0. Record the request, allowed scope and policy profile. Call `diptrace_status`, then `get_capabilities`.
1. Read the exact document with `get_document_info` and the required domain model; record revision/session and source SHA-256 before any semantic operation. For a genuinely pre-design task with no document, hash the normalized input bundle and set applicability to `pre_design`; never invent a document SHA.
2. Separate user facts, document facts, external facts and assumptions. For write-capable work, preserve the mandatory dry-run → preview → validation → expected-SHA commit → applicable ERC/DRC/connectivity → stop/rollback order from the write policy.
3. Partition the schematic into sheets and blocks.
4. Place components for logical readability.
5. Assign values, fields, and patterns.
6. Create wires, labels, buses, and hierarchy.
7. Add explicit no-connect markers.
8. Run localized ERC after each block.
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

Use the guarded semantic write pipeline only when the requested stage is supported and the user has authorized that stage.

1. Call `diptrace_status`, then `get_capabilities`. Read the exact document with `get_document_info` plus the required domain model and freeze its source SHA-256, selectors, region/layers and allowed operations.
2. Read locked objects, keepouts, user constraints, explicit no-connects, DNP state and waivers. Never set an `allow_locked` override unless the user names the exact object.
3. Start `begin_transaction(expected_sha256=<baseline SHA-256>)`. Stage typed semantic operations with `stage_operations`; when a semantic tool is called directly, pass `dry_run=true` and the transaction ID. Staging is itself non-committing; never use `dry_run=false` as a substitute for commit.
4. Call `preview_transaction`, then `validate_transaction`; inspect the semantic diff plus SVG/JSON resources. Treat validation as the mandatory post-preview gate.
5. Commit only after explicit confirmation with `commit_transaction(txid, expected_sha256=<validated source SHA-256>)`. Never infer confirmation from a request for a plan or preview.
6. Re-read document identity and SHA-256, then rerun every applicable regression check. For schematic or mixed documents run `run_erc`; for PCB or mixed documents run `run_drc`; for schematic, PCB or mixed documents always run `run_connectivity_check`. Also run the affected domain checks from: `run_erc`, `run_connectivity_check`, `get_schematic_model`. Record a check as `not_applicable` only when the document kind makes it invalid; an unavailable applicable check blocks success.
7. Compare the post-checks with the baseline. Stop on any regression. If a commit occurred, call `rollback_transaction(txid, expected_sha256=<committed SHA-256>)`, verify the restored SHA and rerun the same applicable ERC/DRC/connectivity checks. Never return `completed` while a regression or failed rollback remains.

Preview generation is not authorization to commit. Unsupported semantic writes must use the dependency report, never raw XML as a workaround.

## Dependency contracts

### `schematic-authoring-v1`

Typed schematic wire, label, bus and hierarchy mutation with verified round-trip.

Required inputs: document identity and SHA-256; sheet and block scope; typed connectivity operations; explicit no-connect intent; locked objects.

Required outputs: semantic transaction; connectivity delta; schematic preview; localized ERC result; committed SHA and rollback token.

Invariants: no raw XML synthesis; no unnamed accidental nets; preview and localized ERC before commit; connectivity cannot silently change outside scope.

The canonical machine-readable contracts are in `../dependency-contracts.json`. A dependency report is a request for an MCP/runtime extension, not permission to implement a brittle parser, geometry approximation or raw XML patch in this skill.

## Outputs

- `updated schematic`
- `sheet map`
- `connectivity report`
- `unresolved decisions`

Return the required common fields: `status`, `summary`, `document_identity`, `inputs_used`, `assumptions`, `findings`, `planned_changes`, `transactions`, `resources`, `skipped_checks`, `confidence` and `next_actions`. Also return `dependency_report`, `acceptance_evidence` and all skill-specific `deliverables`.

Status semantics:

- `completed`: the requested scope and every mandatory acceptance check have evidence.
- `partial`: valid independent work exists, with precise limitations.
- `blocked_by_capability`: an exact dependency contract blocks the requested stage.
- `blocked_by_input`: a named missing or ambiguous input blocks the requested stage.
- `failed`: execution or validation failed and success was not claimed.

`completed` describes execution of the requested workflow, not approval of the design. In particular, `release-gate` carries the independent `PASS|BLOCKED` decision in its release-decision deliverable.

## Acceptance criteria

- There are no accidental unnamed nets.
- Power pins are handled explicitly.
- Every block passes localized ERC.
- The schematic remains readable.

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

> Implement schematic block <name>; produce a plan and preview, run ERC, and commit only after explicit confirmation.
