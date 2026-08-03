from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class ErrorPayload:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    suggested_action: str = ""
    object_ids: list[str] = field(default_factory=list)
    txid: str | None = None
    jobid: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # ``recoverable`` is retained for bridge/job compatibility.  Public MCP
        # tools use the less ambiguous ``retryable`` spelling at the transport
        # boundary.
        payload["retryable"] = self.recoverable
        return payload


class DipTraceMcpError(RuntimeError):
    code: ClassVar[str] = "diptrace_error"
    recoverable: ClassVar[bool] = True
    suggested_action: ClassVar[str] = ""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        object_ids: list[str] | None = None,
        txid: str | None = None,
        jobid: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self._code = code or self.code
        self.details = details or {}
        self.object_ids = object_ids or []
        self.txid = txid
        self.jobid = jobid
        # Retain the cause for local diagnostics without making it part of the
        # serializable payload.
        self.cause = cause

    @property
    def payload(self) -> ErrorPayload:
        return ErrorPayload(
            code=self._code,
            message=str(self),
            details=dict(self.details),
            recoverable=self.recoverable,
            suggested_action=self.suggested_action,
            object_ids=list(self.object_ids),
            txid=self.txid,
            jobid=self.jobid,
        )


class ConfigurationError(DipTraceMcpError):
    code = "configuration_error"
    recoverable = False


class PathAccessError(DipTraceMcpError):
    code = "path_access_denied"


class DocumentError(DipTraceMcpError):
    code = "schema_parse_error"


class EditError(DipTraceMcpError):
    code = "schema_write_error"


class Sha256MismatchError(EditError):
    code = "sha256_mismatch"
    suggested_action = "Reload the document and rebuild the plan."


class RoundtripValidationError(EditError):
    code = "roundtrip_validation_failed"


class SessionError(DipTraceMcpError):
    code = "no_active_session"


class TransactionNotFoundError(DipTraceMcpError):
    code = "transaction_not_found"


class TransactionConflictError(DipTraceMcpError):
    code = "transaction_conflict"
    suggested_action = "Reload the transaction and inspect its current state."


class PolicyDeniedError(DipTraceMcpError):
    code = "policy_denied"


class ConfirmationRequiredError(DipTraceMcpError):
    code = "confirmation_required"


class ScopeRequiredError(DipTraceMcpError):
    code = "scope_required"


class ObjectNotFoundError(DipTraceMcpError):
    code = "object_not_found"


class AmbiguousSelectorError(DipTraceMcpError):
    code = "ambiguous_selector"


class LockedObjectError(DipTraceMcpError):
    code = "locked_object"


class GeometryError(DipTraceMcpError):
    code = "geometry_invalid"


class PlacementError(DipTraceMcpError):
    code = "placement_illegal"


class RoutingError(DipTraceMcpError):
    code = "routing_failed"


class ConnectivityRegressionError(DipTraceMcpError):
    code = "connectivity_regression"


class DrcRegressionError(DipTraceMcpError):
    code = "drc_regression"


class CapabilityUnavailableError(DipTraceMcpError):
    code = "capability_unavailable"


class ExternalToolUnavailableError(CapabilityUnavailableError):
    code = "external_tool_unavailable"


class ExternalToolFailedError(DipTraceMcpError):
    code = "external_tool_failed"


class JobTimeoutError(DipTraceMcpError):
    code = "job_timeout"


class JobCancelledError(DipTraceMcpError):
    code = "job_cancelled"


class InsufficientStackupDataError(DipTraceMcpError):
    code = "insufficient_stackup_data"


class InvalidArgumentError(DipTraceMcpError):
    """A caller supplied an argument that cannot be applied safely."""

    code = "invalid_argument"
    recoverable = False


class ObjectConflictError(DipTraceMcpError):
    """A requested mutation conflicts with current document state."""

    code = "conflict"
    recoverable = True


class UnsupportedOperationError(DipTraceMcpError):
    """The requested operation is outside the supported bounded surface."""

    code = "unsupported_operation"
    recoverable = False


class SafetyGateError(DipTraceMcpError):
    """A safety or evidence gate prevents the operation."""

    code = "safety_gate"
    recoverable = False


class InternalStateError(DipTraceMcpError):
    """An invariant or state-store failure occurred internally."""

    code = "internal_error"
    recoverable = False


class NetClassResolutionError(CapabilityUnavailableError):
    """A referenced NetClass cannot be resolved without guessing."""

    code = "unknown_net_class"
    recoverable = False


# Public spelling used by the service→MCP contract documentation.  Keep the
# historical mixed-case name as the canonical implementation for compatibility.
DipTraceMCPError = DipTraceMcpError
