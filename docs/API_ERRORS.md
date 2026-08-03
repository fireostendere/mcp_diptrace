# MCP error contract

Registered MCP tools return the project response envelope on success and the
following envelope on a bounded failure:

```json
{
  "ok": false,
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "safe client-facing message",
    "details": {},
    "retryable": false
  }
}
```

The boundary is installed after tool registration, so service methods retain
their typed internal exceptions while public tool calls share one translation
point. Domain exceptions preserve only safe structured details. Absolute paths,
XML bodies, credentials, causes and tracebacks are removed. Unexpected
`KeyError`, `AssertionError`, raw `ValueError`, and other programming failures
are logged locally and returned as `INTERNAL_ERROR`; filesystem and
external-process failures use `EXTERNAL_TOOL_ERROR`. Caller validation uses
Pydantic `ValidationError` or the typed `InvalidArgumentError`. On the wire,
failures also set MCP's native `isError` flag; `structuredContent` and the text
content carry the same stable envelope.

The transport contract is tested through an in-memory connected MCP session
using `session.call_tool`, not only by calling a registered Python function.
Those tests assert one outer `CallToolResult`, one JSON error envelope, matching
text and `structuredContent`, and no nested or stringified `CallToolResult`.
They cover a missing document, schema failures (including missing, wrong-type,
extra-field, and non-finite numeric inputs), typed domain errors, raw
`ValueError`, `KeyError`, `AssertionError`, `OSError`, and a representative
external-adapter failure. No registered public tool is asynchronous at present;
the async wrapper itself remains covered by the boundary unit tests.

The stable public taxonomy is:

| Code | Meaning | Retryable default |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Caller supplied an invalid value or shape | no |
| `OBJECT_NOT_FOUND` | Requested document/object/transaction is absent | no |
| `CONFLICT` | Source, transaction or evidence state changed | yes |
| `VALIDATION_ERROR` | Document, geometry or rule validation failed | no |
| `UNSUPPORTED_OPERATION` | Capability or bounded operation is unavailable | no |
| `SAFETY_GATE` | Policy, lock or confirmation gate rejected the call | no |
| `EXTERNAL_TOOL_ERROR` | External process or filesystem dependency failed | yes |
| `INTERNAL_ERROR` | Unexpected implementation/state failure | no |

`retryable` is a transport hint, not a promise that retrying a mutation is
safe. Mutations still require the existing transaction and SHA-256 gates.

## Boundary audit scope

The registered-tool surface is generated in `src/diptrace_mcp/server.py`; every
registered callable is wrapped by `error_boundary.wrap_tool_callable`, and the
argument-validation and tool-run hooks use the same boundary. A registry
traversal test proves that all 159 snapshot tools carry all three boundary
markers; end-to-end tests cover representative groups rather than invoking all
159 tools with every possible invalid input. The project service layer also
validates the same high-risk unit and numeric inputs before mutation.

## Boundary audit matrix

The following groups cover every registered callable; the exact public names are
the committed `tools/list` snapshot. The “current result” column records the
failure shape before this hardening branch, while “desired result” is the
post-boundary contract.

| Tool group | Service method family | Exceptions observed in audit | Current result | Desired code | Retryable | Safe details |
| --- | --- | --- | --- | --- | --- | --- |
| Discovery/status/capabilities | `status`, `get_capabilities`, `document_info`, model/query/list methods | `DocumentError`, `ObjectNotFoundError`, `ValidationError`, `OSError` | mixed raw text and project error payloads | `VALIDATION_ERROR`, `OBJECT_NOT_FOUND`, `EXTERNAL_TOOL_ERROR` | no except external | document kind, stable id, field names; no path bodies |
| Units and numeric conversions | model validators, `numeric_inputs`, geometry conversion | `ValidationError`, `DocumentError`, typed `InvalidArgumentError` | Pydantic or raw conversion text | `INVALID_ARGUMENT` or `VALIDATION_ERROR` | no | field, unit token, bounded XML location; no raw XML |
| Semantic mutations/transactions | `create_*`, `stage_*`, `preview_*`, `commit_*`, component/text/net/testpoint edits | `PolicyDeniedError`, `ConfirmationRequiredError`, `TransactionConflictError`, `EditError`, `ObjectNotFoundError` | internal exception text could cross the tool call | `SAFETY_GATE`, `CONFLICT`, `VALIDATION_ERROR`, `OBJECT_NOT_FOUND` | only conflict according to payload | transaction id, stable object ids, SHA names; no filesystem path |
| Routing and congestion | `route_*`, `plan_*route`, `analyze_routing_congestion` | `RoutingError`, `GeometryError`, `CapabilityUnavailableError`, `NetClassResolutionError` | raw routing or NetClass-resolution text | `VALIDATION_ERROR`, `UNSUPPORTED_OPERATION` | no | net/object ids, layer ids, clearance status; no XML |
| Differential-pair routing | `route_diff_pair`, `plan_diff_pair_route` | `GeometryError`, `RoutingError`, `NetClassResolutionError` | raw geometry text | `VALIDATION_ERROR` | no | pair id, layer ids, bounded numeric constraints |
| Review/analysis | `run_*review`, `run_drc`, `run_erc`, report methods | `DocumentError`, `CapabilityUnavailableError`, `ObjectNotFoundError` | mixed exception/result forms | `VALIDATION_ERROR`, `UNSUPPORTED_OPERATION`, `OBJECT_NOT_FOUND` | no | check id, finding id, skip reason |
| Live-session lifecycle | `begin_live_session`, `finish_live_session`, `abandon_live_session` | `SessionError`, `PolicyDeniedError`, `Sha256MismatchError`, `OSError` | bridge/internal messages were not uniformly bounded | `OBJECT_NOT_FOUND`, `SAFETY_GATE`, `CONFLICT`, `EXTERNAL_TOOL_ERROR` | conflict/external only | session id, SHA field names, local acknowledgement scope |
| External adapters/jobs | DSN/SES, autorouter, ngspice/openEMS and job methods | `ExternalToolUnavailableError`, `ExternalToolFailedError`, `JobTimeoutError`, `OSError` | external command or filesystem text | `EXTERNAL_TOOL_ERROR`, `UNSUPPORTED_OPERATION` | external failures/timeouts | job id, adapter name, bounded status |
| Library and fabrication exports | library reads/validation, BOM and generic export methods | `DocumentError`, `EditError`, external-tool exceptions, `OSError` | raw path/artifact errors were possible | `VALIDATION_ERROR`, `OBJECT_NOT_FOUND`, `EXTERNAL_TOOL_ERROR` | external only | artifact kind, stable id, bounded validation fields |

The table is intentionally grouped by service boundary rather than copying
implementation stack traces into a public artifact. `error_boundary.py` wraps
all registered tools, and the contract tests assert that raw `ValueError`,
`KeyError`, `AssertionError`, and tracebacks never appear in a result.
