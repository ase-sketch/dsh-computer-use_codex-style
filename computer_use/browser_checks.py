"""Official browser security checks: ids, consent/denial text, and the mode tables.

Recovered from `browser-service.mjs` (security class `Hd`, ~:20539-20847 and the
mode tables at ~:20050-20064). Together with `browser_security` this gives the DSH
engine the same gate names, the same user-facing sentences, and the same bypass
semantics as the official bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from computer_use.browser_persistence import (
    NEVER_ASK,
    PersistedConsentStore,
    TurnGrants,
    never_ask_mode_key,
    section_for_check,
)
from computer_use.browser_security import (
    AUTO_REVIEW_INCOMPLETE,
    AUTO_REVIEW_NEEDS_TOOL,
    AUTO_REVIEW_UNSUPPORTED,
    DEFAULT_DISPLAY_NAME,
    BrowserUseSecurityError,
    ConsentRequest,
    download_consent,
    full_cdp_consent,
    history_consent,
    origin_consent,
    upload_consent,
)

# --- Check catalog ---------------------------------------------------------

#: Every official check id, with the telemetry permission name it maps to.
CHECK_PERMISSION_NAMES: dict[str, str] = {
    "browser-history-read": "history",
    "browser-origin-access": "origin_access",
    "check-navigation-url-policy": "navigation_url",
    "check-url-site-status": "site_status",
    "file-download": "file_download",
    "file-upload": "file_upload",
    "full-cdp": "full_cdp_access",
    "page-asset-cross-origin-fetch": "page_asset_cross_origin_fetch",
    "page-asset-download": "page_asset_download",
    "raw-cdp-destination-url": "raw_cdp_destination",
    "webmcp-tool-call": "webmcp_access",
    "automated-safety-precheck": "automated_safety_precheck",
}

ALL_CHECKS = tuple(CHECK_PERMISSION_NAMES)

#: Official BROWSER_USE_SECURITY_MODE values.
SECURITY_MODES = ("", "disabled-for-local-testing", "gaas-browser-environment")

#: Mode -> checks that are skipped entirely. The empty mode skips nothing.
BYPASSED_CHECKS: dict[str, frozenset[str]] = {
    "": frozenset(),
    "disabled-for-local-testing": frozenset({
        "browser-history-read",
        "browser-origin-access",
        "check-navigation-url-policy",
        "check-url-site-status",
        "file-download",
        "file-upload",
        "full-cdp",
        "page-asset-cross-origin-fetch",
        "page-asset-download",
        "raw-cdp-destination-url",
    }),
    "gaas-browser-environment": frozenset(),
}

#: Mode -> operations that proceed without asking the user.
NO_CONSENT_OPERATIONS: dict[str, frozenset[str]] = {
    "": frozenset(),
    "disabled-for-local-testing": frozenset({
        "browser-history-read",
        "browser-origin-access",
        "file-download",
        "file-upload",
        "full-cdp",
        "page-asset-cross-origin-fetch",
        "page-asset-download",
        "raw-cdp-destination-url",
        "webmcp-tool-call",
    }),
    "gaas-browser-environment": frozenset({
        "browser-history-read",
        "file-download",
        "page-asset-cross-origin-fetch",
        "page-asset-download",
    }),
}


# --- Denial sentences ------------------------------------------------------


def denial_text(check: str, *, name: str = DEFAULT_DISPLAY_NAME, **fields: str) -> str:
    """The official denial sentence for a blocked check.

    Every branch is a verbatim official string with the display name and the
    context values substituted.
    """
    origin = fields.get("origin", "")
    display_url = fields.get("display_url", origin)
    if check == "browser-origin-access":
        return f"{name} cannot access {origin} because the admin-enforced policy blocks it."
    if check == "browser-origin-access-unavailable":
        return f"{name} could not verify the admin-enforced policy before accessing {origin}."
    if check == "check-navigation-url-policy":
        return (
            f"{name} cannot visit the requested page because its URL is blocked by the "
            f"{name} URL policy."
        )
    if check == "check-url-site-status":
        return f"{display_url} is not permitted on {name}."
    if check == "file-download":
        return (
            f"{name} cannot download files from {origin} because the Browser Use origin "
            "policy blocks it."
        )
    if check == "file-upload":
        return (
            f"{name} cannot upload files to {origin} because the Browser Use origin "
            "policy blocks it."
        )
    if check in {"full-cdp", "raw-cdp-destination-url"}:
        return f"{name} cannot use raw CDP because the Browser Use origin policy blocks it."
    if check == "raw-cdp-non-http":
        return (
            "Raw CDP requires an HTTP(S) page. Navigate to the tab first then use the CDP "
            "capability."
        )
    if check == "page-asset-download":
        return (
            f"{name} cannot download page assets from {display_url} because the Browser Use "
            "origin policy blocks it."
        )
    if check == "page-asset-cross-origin-fetch":
        return (
            f"{name} cannot download an asset from {display_url} because the Browser Use "
            "origin policy blocks it."
        )
    if check == "webmcp-tool-call":
        return (
            f"{name} cannot use WebMCP tools because the current page changed while waiting "
            "for approval."
        )
    raise KeyError(f"no denial text for check {check}")


def consent_for(check: str, **fields: str) -> ConsentRequest | None:
    """The consent prompt for a check, or None when the official flow never asks."""
    name = fields.get("name", DEFAULT_DISPLAY_NAME)
    if check == "browser-origin-access":
        return origin_consent(fields["origin"], name)
    if check == "browser-history-read":
        return history_consent(name)
    if check == "file-upload":
        return upload_consent(fields["url"], name)
    if check == "file-download":
        return download_consent(fields["url"], name)
    if check in {"full-cdp", "raw-cdp-destination-url"}:
        return full_cdp_consent(fields["origin"], name)
    if check == "page-asset-download":
        host = fields.get("host", fields.get("origin", ""))
        return ConsentRequest(
            message=f"I need your permission to download assets used by {host}",
            tool_name="download_page_assets",
            tool_title="Download page assets",
        )
    if check == "page-asset-cross-origin-fetch":
        host = fields.get("host", fields.get("origin", ""))
        return ConsentRequest(
            message=f"I need your permission to download an asset from {host}",
            tool_name="download_page_asset",
            tool_title="Download a page asset",
        )
    if check == "automated-safety-precheck":
        tool = fields.get("tool", "")
        if not tool:
            raise ValueError(AUTO_REVIEW_NEEDS_TOOL)
        return ConsentRequest(
            message=AUTO_REVIEW_INCOMPLETE.format(name=tool),
            tool_name=f"automated_safety_precheck.{tool}",
            tool_title="Automated safety precheck",
            risk_level="high",
        )
    # check-navigation-url-policy and check-url-site-status never ask: they fail closed.
    return None


# --- Policy -----------------------------------------------------------------


#: How an un-granted, consent-requiring check is resolved when no approval
#: service answers (DSH decision D-A). "ask" consults the injected approver and,
#: when none is configured, records the request and proceeds -- the DSH approval
#: service wiring is still pending (05 report appendix C-7), and the alternative
#: (hard deny with no UI) would turn a missing integration into a broken browser.
#: "deny" fails closed; "record" is an unanswered "ask" without consulting anyone.
CONSENT_DECISIONS = ("ask", "deny", "record")


@dataclass
class BrowserSecurityPolicy:
    """Gates browser commands with the official check names and text.

    The policy decides and records; the caller supplies the approval service via
    `gate(..., approver=...)`, which keeps this module testable without a harness.
    Every decision lands in `audit` (the official audit trail only covers
    `management` mutations -- OV-1).
    """

    mode: str = ""
    display_name: str = DEFAULT_DISPLAY_NAME
    #: "ask" | "deny" | "record" (see CONSENT_DECISIONS).
    default_decision: str = "ask"
    #: Origins the user already approved for this session.
    approved_origins: set[str] = field(default_factory=set)
    #: check -> key -> scope ("session" | "always").
    grants: dict[str, dict[str, str]] = field(default_factory=dict)
    #: One entry per gate decision.
    audit: list[dict[str, str]] = field(default_factory=list)
    #: BR-17: the official config.global / config.session(id) document.
    #: None keeps every grant in process memory (the pre-BR-17 behaviour).
    store: PersistedConsentStore | None = None
    #: The conversation id used for the official "conversation" scope.
    conversation_id: str = ""
    #: The current turn id used by the official turn-scoped origin grant.
    turn_id: str = ""
    #: Official Hw("iab"): which history-approval section to read.
    iab: bool = False
    #: Official Ps map: a one-turn, 300 s origin grant.
    turn_grants: TurnGrants = field(default_factory=TurnGrants)

    @classmethod
    def from_disk(cls, path: object = None, **kwargs: Any) -> "BrowserSecurityPolicy":
        """Load the persisted prompt results (BR-17).

        The host points path at browser_persistence.default_consent_path();
        with no path the store stays in memory.
        """
        return cls(store=PersistedConsentStore.load(path), **kwargs)

    def __post_init__(self) -> None:
        if self.mode not in SECURITY_MODES:
            raise ValueError(f"unknown browser security mode: {self.mode!r}")
        if self.default_decision not in CONSENT_DECISIONS:
            raise ValueError(f"unknown consent decision: {self.default_decision!r}")

    def check_bypassed(self, check: str) -> bool:
        return check in BYPASSED_CHECKS[self.mode]

    def consent_required(self, check: str) -> bool:
        if self.check_bypassed(check):
            return False
        return check not in NO_CONSENT_OPERATIONS[self.mode]

    @property
    def precheck_required(self) -> bool:
        """Official `vh(runtime)`: the automated safety precheck exists only in
        the GaaS browser environment."""
        return self.mode == "gaas-browser-environment"

    def granted(self, check: str, key: str) -> bool:
        return str(key or "") in self.grants.get(check, {})

    def remember(self, check: str, key: str, scope: str = "session") -> None:
        if key:
            self.grants.setdefault(check, {})[str(key)] = scope

    def export_grants(self, *, include_session: bool = True) -> dict[str, dict[str, str]]:
        """BR-17: the host persists `always` grants across sessions; `session`
        grants live only as long as the surface."""
        if include_session:
            return {check: dict(keys) for check, keys in self.grants.items()}
        return {
            check: {key: scope for key, scope in keys.items() if scope == "always"}
            for check, keys in self.grants.items()
        }

    def import_grants(self, grants: dict[str, dict[str, str]]) -> None:
        for check, keys in (grants or {}).items():
            for key, scope in (keys or {}).items():
                self.remember(str(check), str(key), str(scope))
                if str(check) == "browser-origin-access":
                    self.approved_origins.add(str(key))

    def remember_origin(self, origin: str) -> None:
        """Official `handleOriginPromptResult`: persist the granted origin."""
        if not origin:
            return
        self.approved_origins.add(origin)
        self.remember("browser-origin-access", origin, "session")

    def _record(self, check: str, key: str, decision: str, fields: dict[str, str]) -> None:
        entry = {"check": check, "key": str(key or ""), "decision": decision}
        entry.update({name: str(value) for name, value in fields.items()})
        self.audit.append(entry)

    def _denial_reason(self, check: str) -> str:
        return "guardian_denied" if check == "automated-safety-precheck" else "user_declined"

    def _denial_message(self, check: str, fields: dict[str, str]) -> str:
        if check == "automated-safety-precheck":
            return AUTO_REVIEW_INCOMPLETE.format(name=fields.get("tool", ""))
        try:
            return denial_text(check, name=self.display_name, **fields)
        except KeyError:
            return (
                f"{self.display_name} cannot complete this browser action because "
                f"{check} is blocked."
            )

    def _grant(self, check: str, key: str, scope: str) -> None:
        if check == "browser-origin-access":
            self.remember_origin(key)
            self.note_turn_grant(key)
        self.remember(check, key, scope)

    def persisted_decision(self, check: str, key: str) -> str | None:
        """BR-17: official getOriginPermission / getPersistedHistoryPermission.

        Returns "approve" / "deny" / None. The history check reads the global
        history-approval mode; everything else reads the sectioned origin lists.
        """
        if self.store is None:
            return None
        if check == "browser-history-read":
            verdict = self.store.history_decision(iab=self.iab, scope="global")
            return verdict if verdict in {"approve", "deny"} else None
        section = section_for_check(check)
        if section is None:
            return None
        scopes = [("global", "")]
        if self.conversation_id:
            scopes.append(("session", self.conversation_id))
        # Official maybeAutoAnswerBrowserUseRequest: a conversation denial wins
        # over a global denial, and both win over any allow.
        for scope, conversation in reversed(scopes):
            if self.store.decision(
                section, key, scope=scope, conversation_id=conversation
            ) == "deny":
                return "deny"
        for scope, conversation in scopes:
            if self.store.decision(
                section, key, scope=scope, conversation_id=conversation
            ) == "approve":
                return "approve"
        # Official fallback: approval_mode == never_ask (persistent approval is
        # allowed by the deployment; DSH has no such enterprise gate, so the
        # marker alone is enough here -- documented divergence).
        mode_key = never_ask_mode_key(check)
        if mode_key and self.store.mode(mode_key) == NEVER_ASK:
            return "approve"
        return None

    def persist_decision(
        self, check: str, key: str, decision: str, scope: str, *, never_ask: bool = False
    ) -> None:
        """BR-17: official $w -> lJ / pJ (and handleHistoryPromptResult)."""
        if self.store is None:
            return
        if check == "browser-history-read":
            if scope == "always":
                self.store.record_history(decision, iab=self.iab, scope="global")
                self.store.save()
            return
        section = section_for_check(check)
        if section is None:
            return
        if never_ask and check == "browser-origin-access":
            self.store.record_never_ask_origin(scope="global")
        else:
            target = "global" if scope == "always" else ("session" if self.conversation_id else "")
            if not target:
                return
            self.store.record(
                section,
                key,
                decision,
                scope=target,
                conversation_id=self.conversation_id if target == "session" else "",
            )
        self.store.save()

    def turn_grant_active(self, check: str, key: str) -> bool:
        """Official wJ / yJ: a 300 s, one-turn origin grant."""
        if check != "browser-origin-access" or not self.conversation_id or not self.turn_id:
            return False
        return self.turn_grants.active(self.conversation_id, self.turn_id, key)

    def note_turn_grant(self, origin: str) -> None:
        """Official wJ(e): record the per-turn origin grant on accept."""
        if origin and self.conversation_id and self.turn_id:
            self.turn_grants.grant(self.conversation_id, self.turn_id, origin)

    def gate(self, check: str, key: str, *, approver: Any = None, **fields: str) -> str:
        """Ask for consent when the official flow asks, then record the outcome.

        Returns the outcome token. Raises BrowserUseSecurityError when denied.
        """
        if self.check_bypassed(check):
            self._record(check, key, "bypassed", fields)
            return "bypassed"
        persisted = self.persisted_decision(check, key)
        if persisted == "deny":
            self._record(check, key, "persisted-denied", fields)
            raise BrowserUseSecurityError(
                "persisted_user_denied", self._denial_message(check, fields)
            )
        if persisted == "approve":
            self._grant(check, key, "always")
            self._record(check, key, "granted-persisted", fields)
            return "granted-persisted"
        if self.turn_grant_active(check, key):
            self._grant(check, key, "session")
            self._record(check, key, "granted-turn", fields)
            return "granted-turn"
        if self.granted(check, key):
            return "granted"
        if not self.consent_required(check):
            self._record(check, key, "no-consent", fields)
            return "no-consent"
        request = consent_for(check, name=self.display_name, **fields)
        if request is None:
            self._record(check, key, "no-consent", fields)
            return "no-consent"
        decision = ""
        if approver is not None:
            decision = str(approver(request) or "").strip().lower()
        if decision in {"approve", "approved", "allow", "session", "always", "never"}:
            scope = "always" if decision in {"always", "never"} else "session"
            self._grant(check, key, scope)
            self.persist_decision(check, key, "approve", scope, never_ask=decision == "never")
            self._record(check, key, "approved", fields)
            return "approved"
        if decision in {"deny", "denied", "reject", "rejected", "cancel", "canceled", "cancelled"}:
            # Official lJ persists a decline too (default scope: conversation).
            self.persist_decision(check, key, "deny", "session")
            self._record(check, key, decision or "denied", fields)
            raise BrowserUseSecurityError(
                self._denial_reason(check), self._denial_message(check, fields)
            )
        if self.default_decision == "deny":
            self._record(check, key, "denied", fields)
            raise BrowserUseSecurityError(
                self._denial_reason(check), self._denial_message(check, fields)
            )
        # "ask" with no approval service wired, or "record": record and proceed.
        if check == "browser-origin-access":
            self.remember_origin(key)
        else:
            self.remember(check, key, "session")
        self._record(check, key, "recorded", fields)
        return "recorded"

    def assert_origin_allowed(self, origin: str) -> None:
        """Official browser-origin-access. Fails closed after the gate asked: an
        origin must be explicitly approved before a tab-scoped command touches it."""
        check = "browser-origin-access"
        if self.check_bypassed(check) or origin in self.approved_origins:
            return
        raise BrowserUseSecurityError(
            "persisted_user_denied",
            denial_text(check, name=self.display_name, origin=origin),
        )

    def assert_url_policy(self, url: str) -> None:
        """Official check-navigation-url-policy: blocked schemes fail closed."""
        from computer_use.policy import BLOCKED_URL_SCHEMES

        check = "check-navigation-url-policy"
        if self.check_bypassed(check):
            return
        lowered = url.strip().lower()
        for scheme in BLOCKED_URL_SCHEMES:
            if lowered.startswith(scheme):
                raise BrowserUseSecurityError(
                    "navigation_url_policy_blocked",
                    denial_text(check, name=self.display_name),
                )

    def assert_site_status_allowed(self, display_url: str, *, blocked_hosts: set[str] | None = None) -> None:
        """Official check-url-site-status. The live status service is not part of the
        DSH deployment, so only an explicit deny list is enforced; a missing service
        must fail open, like the official transport-error path (site_status_unavailable)."""
        check = "check-url-site-status"
        if self.check_bypassed(check):
            return
        host = _host_of(display_url)
        if host and host in (blocked_hosts or set()):
            raise BrowserUseSecurityError(
                "site_status_blocked",
                denial_text(check, name=self.display_name, display_url=display_url),
            )

    def assert_upload_allowed(self, url: str, *, key: str | None = None) -> None:
        check = "file-upload"
        if self.check_bypassed(check) or self.granted(check, url if key is None else key):
            return
        raise BrowserUseSecurityError(
            "user_declined",
            denial_text(check, name=self.display_name, origin=_origin_of(url)),
        )

    def assert_download_allowed(self, url: str, *, key: str | None = None) -> None:
        check = "file-download"
        if self.check_bypassed(check) or self.granted(check, url if key is None else key):
            return
        raise BrowserUseSecurityError(
            "user_declined",
            denial_text(check, name=self.display_name, origin=_origin_of(url)),
        )

    def assert_full_cdp_allowed(self, origin: str) -> None:
        """Official full-cdp: always high risk, never silently allowed."""
        check = "full-cdp"
        if self.check_bypassed(check):
            return
        if _origin_of(origin) == "":
            raise BrowserUseSecurityError(
                "browser_navigation_blocked",
                denial_text("raw-cdp-non-http"),
            )
        if self.granted(check, origin):
            return
        raise BrowserUseSecurityError(
            "user_declined",
            denial_text(check, name=self.display_name),
        )

    def assert_page_asset_download_allowed(self, url: str, *, cross_origin: bool = False) -> None:
        """Same-origin asset fetches are allowed silently (official behaviour)."""
        if not cross_origin:
            return
        check = "page-asset-cross-origin-fetch"
        key = _host_of(url) or url
        if self.check_bypassed(check) or self.granted(check, key):
            return
        raise BrowserUseSecurityError(
            "user_declined",
            denial_text(check, name=self.display_name, display_url=url),
        )


def _origin_of(url: str) -> str:
    """Scheme + host, or an empty string when the input is not an http(s) URL."""
    lowered = url.strip().lower()
    for scheme in ("http://", "https://"):
        if lowered.startswith(scheme):
            rest = lowered[len(scheme):]
            host = rest.split("/", 1)[0]
            return f"{scheme}{host}"
    return ""


def _host_of(display_url: str) -> str:
    origin = _origin_of(display_url)
    if not origin:
        return ""
    return origin.split("://", 1)[1]


__all__ = [
    "ALL_CHECKS",
    "BYPASSED_CHECKS",
    "CHECK_PERMISSION_NAMES",
    "CONSENT_DECISIONS",
    "NO_CONSENT_OPERATIONS",
    "SECURITY_MODES",
    "BrowserSecurityPolicy",
    "consent_for",
    "denial_text",
]
