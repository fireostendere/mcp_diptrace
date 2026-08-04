"""Local DipTrace live-session lifecycle orchestration."""

from __future__ import annotations

from typing import Any

from ..sessions import SessionAction, SessionStore
from .context import ServiceContext


class LiveSessionService:
    """Implementation for local live-session finish and abandonment."""

    def __init__(self, context: ServiceContext, session_store: SessionStore) -> None:
        self.context = context
        self.session_store = session_store

    def finish_live_session(
        self,
        action: SessionAction,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        if action == "apply":
            self.context.policy.require_write(dry_run=False, operation="finish_live_session")
        request = self.session_store.request_finish(action, expected_sha256)
        return self.session_store.wait_for_finish_outcome(request)

    def abandon_live_session(self, reason: str) -> dict[str, Any]:
        """Terminate stale local session state without applying working XML."""

        metadata = self.session_store.abandon_active(reason)
        return {
            "session_id": metadata["session_id"],
            "outcome": "abandoned",
            "local_bridge_status": "abandoned",
            "written": False,
            "reason": metadata["abandon_reason"],
            "diptrace_host_acknowledged": False,
            "acknowledgement_scope": "local_session_state_only",
            "message": (
                "The local session was abandoned without applying working XML or "
                "replacing the exchange file."
            ),
        }
