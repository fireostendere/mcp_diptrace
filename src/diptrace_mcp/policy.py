from __future__ import annotations

from dataclasses import dataclass

from .config import PolicyProfile
from .errors import PolicyDeniedError


@dataclass(frozen=True, slots=True)
class Policy:
    profile: PolicyProfile

    @property
    def allows_preview(self) -> bool:
        return self.profile != "read_only"

    @property
    def allows_commit(self) -> bool:
        return self.profile in {"interactive_edit", "automation", "manufacturing"}

    @property
    def allows_external_execution(self) -> bool:
        return self.profile in {"interactive_edit", "automation", "manufacturing"}

    @property
    def allows_manufacturing_export(self) -> bool:
        return self.profile == "manufacturing"

    def require_write(self, *, dry_run: bool, operation: str) -> None:
        allowed = self.allows_preview if dry_run else self.allows_commit
        if allowed:
            return
        action = "preview" if dry_run else "commit"
        raise PolicyDeniedError(
            f"Policy profile {self.profile!r} denies {action} for {operation}",
            details={
                "active_profile": self.profile,
                "operation": operation,
                "dry_run": dry_run,
            },
        )

    def require_external_execution(self, *, operation: str) -> None:
        if self.allows_external_execution:
            return
        raise PolicyDeniedError(
            f"Policy profile {self.profile!r} denies external execution for {operation}",
            details={"active_profile": self.profile, "operation": operation},
        )

    def capability_payload(self) -> dict[str, object]:
        return {
            "active_profile": self.profile,
            "allows_preview": self.allows_preview,
            "allows_commit": self.allows_commit,
            "allows_external_execution": self.allows_external_execution,
            "allows_manufacturing_export": self.allows_manufacturing_export,
        }
