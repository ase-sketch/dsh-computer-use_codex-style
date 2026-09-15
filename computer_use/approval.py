"""App approval elicitation recovered from helper AppApprovalRequest + JS D()."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from computer_use.allowlist import load_always, save_always
from computer_use.errors import ApprovalDenied


@dataclass
class AppApprovalRequest:
    app: str
    display_name: str
    risk_level: str = "low"
    allow_persistent_approval: bool = True

    def to_helper(self) -> dict[str, Any]:
        from computer_use.notify_config import notify_approval

        payload = notify_approval(
            self.app,
            self.display_name,
            risk_level=self.risk_level,
            allow_persistent=self.allow_persistent_approval,
        )
        payload.update(
            {
                "app": self.app,
                "displayName": self.display_name,
                "riskLevel": self.risk_level,
                "allowPersistentApproval": self.allow_persistent_approval,
            }
        )
        return payload

    def message(self) -> str:
        if self.app == "computer-audio":
            return "Allow Computer Use to record computer audio?"
        return f"Allow DeepSeek Harness to use {self.display_name}?"


Elicitation = Callable[[AppApprovalRequest], dict[str, Any]]


def auto_accept(request: AppApprovalRequest) -> dict[str, Any]:
    persist = "always" if request.allow_persistent_approval else "session"
    return {"action": "accept", "_meta": {"persist": persist}}


@dataclass
class ApprovalGate:
    elicitation: Elicitation = auto_accept
    session: set[str] = field(default_factory=set)
    always: set[str] = field(default_factory=set)
    requests: list[AppApprovalRequest] = field(default_factory=list)
    persist: bool = False
    persist_path: Any = None

    @classmethod
    def from_disk(cls, elicitation: Elicitation = auto_accept, path: Any = None) -> "ApprovalGate":
        return cls(elicitation=elicitation, always=load_always(path), persist=True, persist_path=path)

    def ensure(self, app: str, display_name: str | None = None) -> None:
        key = app.lower()
        if key in self.always or key in self.session:
            return
        request = AppApprovalRequest(app=app, display_name=display_name or app)
        self.requests.append(request)
        decision = self.elicitation(request)
        if decision.get("action") != "accept":
            raise ApprovalDenied(f"Computer Use was not approved to use {request.display_name}")
        persist = str((decision.get("_meta") or {}).get("persist") or "session")
        if persist == "always" and request.allow_persistent_approval:
            self.always.add(key)
            if self.persist:
                save_always(self.always, self.persist_path)
        else:
            self.session.add(key)

    def from_helper(self, payload: dict[str, Any]) -> AppApprovalRequest:
        app = str(payload.get("app") or "").strip()
        name = str(payload.get("displayName") or app)
        risk = payload.get("riskLevel")
        level = risk if risk in {"high", "low"} else "low"
        allow = payload.get("allowPersistentApproval") is not False
        return AppApprovalRequest(app=app, display_name=name, risk_level=level, allow_persistent_approval=allow)
