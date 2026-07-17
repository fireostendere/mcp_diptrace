---
name: pcb-skill-evaluator
description: "Orchestrate DipTrace MCP for PCB Skill Evaluator: Evaluate accuracy, safety, graceful degradation, determinism, and regression behavior of other PCB skills. Use when the user requests this workflow for a DipTrace schematic, PCB, library, review, or explicitly bounded project scope. Start with capability discovery; never simulate unavailable tools or write without a guarded preview."
---

# PCB Skill Evaluator

## Purpose

Evaluate accuracy, safety, graceful degradation, determinism, and regression behavior of other PCB skills.

Priority: `P0`. Declared maturity: `requires an isolated fixture runtime`. Treat maturity as planning metadata, not runtime proof of availability.

## Applicability

Use this skill for the complete workflow described by the trigger, for a bounded subsystem, or to resume an interrupted run from current document state. It may consume an offline DipTrace XML document or the active live document. Resolve every file/session explicitly; never guess which revision is active.

Required inputs:

- skill definition
- golden and adversarial fixtures
- expected findings and changes
- capability profiles

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
| `execute_agent_fixture` | — | `missing` | Do not call the target name. Use dependency contract `agent-eval-runtime-v1`; block only dependent stages. |
| `get_findings` | `get_findings` | `exact` | Requires a report_id returned by a review; use the document findings resource for aggregate history. |
| `list_transactions` | `list_transactions` | `exact` | Use only when document capabilities allow it. |
| `rollback_transaction` | `rollback_transaction` | `exact` | Use only when document capabilities allow it. |
| `compare_review_reports` | — | `missing` | Do not call the target name. Use dependency contract `semantic-compare-v1`; block only dependent stages. |

Names in the Target contract column are conceptual contracts. Only a non-empty name in the Callable runtime tool column may be invoked. Re-resolve at every run; the table documents this repository revision but does not override runtime discovery.

## Workflow

0. Record the request, allowed scope and policy profile. Call `diptrace_status`, then `get_capabilities`.
1. Read the exact document with `get_document_info` and the required domain model; record revision/session and source SHA-256 before any semantic operation. For a genuinely pre-design task with no document, hash the normalized input bundle and set applicability to `pre_design`; never invent a document SHA.
2. Separate user facts, document facts, external facts and assumptions. For write-capable work, preserve the mandatory dry-run → preview → validation → expected-SHA commit → applicable ERC/DRC/connectivity → stop/rollback order from the write policy.
3. Validate package structure and capability contracts.
4. Run fixtures in an isolated scope.
5. Measure precision and recall.
6. Detect unsafe writes.
7. Check determinism and regression behavior.
8. Produce a scorecard and remediation tasks.
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

This skill evaluates only disposable, isolated fixtures; it never writes the selected user design.

- Require a compatible `execute_agent_fixture` adapter that proves fixture isolation, deterministic seed, scope and baseline SHA-256. Without it, return `blocked_by_capability` with `agent-eval-runtime-v1`.
- The adapter may exercise the guarded preview/commit path only inside its cloned fixture. Never redirect an evaluation transaction to an active document or user working copy.
- Inspect the returned tool trace and transaction ledger. `rollback_transaction` may be called only for a transaction whose adapter evidence identifies the same isolated fixture and SHA-256.
- Require rollback evidence for every committed fixture write. Treat an unrolled committed fixture, overlapping write scope or hidden tool call as a critical safety failure.
- Keep this skill result's `transactions` empty; return the adapter ledger through a hashed resource URI and the scorecard deliverable.

Successful evaluation is not permission to install, publish or mutate the evaluated skill or design.

## Dependency contracts

### `agent-eval-runtime-v1`

Isolated multi-agent and skill-evaluation runtime with conflict-safe scopes.

Required inputs: skill package identity; fixture bundle and capability profile; agent roles; scope and risk policy; deterministic seed.

Required outputs: structured traces; tool-call sequence; transaction ledger; precision and recall metrics; regression comparison.

Invariants: fixtures are isolated; parallel write scopes do not overlap; high-risk work gets independent review; all committed fixture writes are rolled back.

### `semantic-compare-v1`

Stable-ID semantic comparison of revisions, reports, routes and libraries.

Required inputs: base and candidate identities with SHA-256; comparison profile; stable-ID policy; waiver set.

Required outputs: added, removed and changed objects; new, resolved, changed and waived findings; metric deltas; regression classification; resource URI.

Invariants: XML ordering is ignored; fixes and regressions are separate; ambiguous identity mapping blocks dependent conclusions.

The canonical machine-readable contracts are in `../dependency-contracts.json`. A dependency report is a request for an MCP/runtime extension, not permission to implement a brittle parser, geometry approximation or raw XML patch in this skill.

## Outputs

- `skill scorecard`
- `failed scenarios`
- `safety findings`
- `regression baseline`

Return the required common fields: `status`, `summary`, `document_identity`, `inputs_used`, `assumptions`, `findings`, `planned_changes`, `transactions`, `resources`, `skipped_checks`, `confidence` and `next_actions`. Also return `dependency_report`, `acceptance_evidence` and all skill-specific `deliverables`.

Status semantics:

- `completed`: the requested scope and every mandatory acceptance check have evidence.
- `partial`: valid independent work exists, with precise limitations.
- `blocked_by_capability`: an exact dependency contract blocks the requested stage.
- `blocked_by_input`: a named missing or ambiguous input blocks the requested stage.
- `failed`: execution or validation failed and success was not claimed.

`completed` describes execution of the requested workflow, not approval of the design. In particular, `release-gate` carries the independent `PASS|BLOCKED` decision in its release-decision deliverable.

## Acceptance criteria

- A skill is never marked ready without acceptance evidence.
- False success is a critical failure.
- Graceful degradation is tested.

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

> Evaluate skill <slug> against fixture suite <suite> for accuracy, safety, determinism, and regression behavior.
