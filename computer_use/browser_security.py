"""Official browser security layer: consent prompts and the BrowserUseSecurityError taxonomy.

Recovered from `browser-service.mjs` (security class `Hd`, ~:20539-20847) and the
error classes at ~:7964-8065. The consent prompts follow decision D2: geometry and
wording match the official form, with DeepSeek Harness as the display name.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Consent prompts -------------------------------------------------------

#: Official display name for the browser approval surface ("Browser use" for the
#: codex-app environment).
DEFAULT_DISPLAY_NAME = "DeepSeek Harness"


@dataclass(frozen=True)
class ConsentRequest:
    """One browser consent prompt, mirroring the official elicitation payload."""

    message: str
    tool_name: str
    tool_title: str
    risk_level: str = "low"
    persist: tuple[str, ...] = ("session", "always")
    sensitive_data: str | None = None
    full_cdp_access: bool = False

    def to_elicitation(self, extra: dict[str, object] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "message": self.message,
            "codex_approval_kind": "mcp_tool_call",
            "connector_id": "browser-use",
            "connector_name": "Browser Use",
            "tool_name": self.tool_name,
            "tool_title": self.tool_title,
            "riskLevel": self.risk_level,
            "persist": list(self.persist),
        }
        if self.sensitive_data:
            payload["sensitive_data"] = self.sensitive_data
        if self.full_cdp_access:
            payload["full_cdp_access"] = True
        if extra:
            payload.update(extra)
        return payload


def origin_consent(origin: str, display_name: str = DEFAULT_DISPLAY_NAME) -> ConsentRequest:
    """Official: `Allow <name> to access <origin>?` (tool `access_browser_origin`)."""
    return ConsentRequest(
        message=f"Allow {display_name} to access {origin}?",
        tool_name="access_browser_origin",
        tool_title="Access browser origin",
    )


def history_consent(display_name: str = DEFAULT_DISPLAY_NAME) -> ConsentRequest:
    """Official: `Allow <name> to use your browsing history for this task?`"""
    return ConsentRequest(
        message=f"Allow {display_name} to use your browsing history for this task?",
        tool_name="read_browsing_history",
        tool_title="Use browsing history",
        sensitive_data="browsing_history",
    )


def upload_consent(url: str, display_name: str = DEFAULT_DISPLAY_NAME) -> ConsentRequest:
    """Official: `Allow upload to <url>?` (tool `upload_browser_files`)."""
    return ConsentRequest(
        message=f"Allow upload to {url}?",
        tool_name="upload_browser_files",
        tool_title="Upload browser files",
    )


def download_consent(url: str, display_name: str = DEFAULT_DISPLAY_NAME) -> ConsentRequest:
    """Official: download consent, tool `download_browser_files`."""
    return ConsentRequest(
        message=f"Allow download from {url}?",
        tool_name="download_browser_files",
        tool_title="Download browser files",
    )


def full_cdp_consent(origin: str, display_name: str = DEFAULT_DISPLAY_NAME) -> ConsentRequest:
    """Official: full CDP access is always `riskLevel: high`."""
    return ConsentRequest(
        message=f"Allow {display_name} to use full CDP access on {origin}",
        tool_name="access_browser_origin_with_raw_cdp",
        tool_title="Use full CDP access",
        risk_level="high",
        full_cdp_access=True,
    )


# --- Automated safety precheck (BR-10, `automated-safety-precheck`) ----------

#: Verbatim official sentences for the GaaS auto-review gate (browser-service.mjs
#: `vh(runtime)`, ~offset 20050 and the guardian error paths).
AUTO_REVIEW_INCOMPLETE = (
    "Auto-review could not complete the required safety review for this {name} action."
)
AUTO_REVIEW_UNSUPPORTED = (
    "The required auto-review functionality for this {name} feature is not supported in "
    "this environment."
)
AUTO_REVIEW_NEEDS_TOOL = "Auto-review safety precheck requires a tool name"


def auto_review_error(task: str, *, unsupported: bool = False) -> str:
    template = AUTO_REVIEW_UNSUPPORTED if unsupported else AUTO_REVIEW_INCOMPLETE
    return template.format(name=task)


# --- Error taxonomy --------------------------------------------------------

#: reason -> (decision source, retryable). Exactly the official table.
REASONS: dict[str, tuple[str, bool]] = {
    "approval_cancelled": ("approval", True),
    "approval_failed_closed": ("approval", True),
    "approval_unavailable": ("approval", True),
    "browser_capability_blocked": ("browser", False),
    "browser_capability_unavailable": ("browser", True),
    "browser_context_unavailable": ("browser", True),
    "browser_navigation_blocked": ("browser", False),
    "enterprise_policy_blocked": ("enterprise", False),
    "enterprise_policy_unavailable": ("enterprise", True),
    "guardian_denied": ("guardian", False),
    "navigation_url_policy_blocked": ("browser", False),
    "persisted_user_denied": ("user_persisted_setting", False),
    "site_status_blocked": ("site_status", False),
    "site_status_unavailable": ("site_status", True),
    "user_declined": ("user_decision", False),
}

RETRYABLE_WRAPPER = (
    "Browser Use could not complete this action because a browser security check was "
    "unavailable. Reason: {message} {detail} This failure may be temporary. The agent may "
    "retry after the issue is resolved, but must not bypass browser security controls or "
    "use an indirect workaround."
)

NON_RETRYABLE_WRAPPER = (
    "Browser Use rejected this action due to browser security policy. Reason: {message} "
    "{detail} The agent must not attempt to achieve the same outcome via workaround, "
    "indirect execution, raw CDP or browser commands, alternate browser surfaces, or "
    "policy circumvention. Proceed only with a materially safer alternative that does not "
    "require this blocked browser action; if none exists, stop and request user input."
)

#: Official reason phrases used by the approval-mediated failure sentence.
REASON_PHRASES: dict[str, str] = {
    "persisted_user_denied": "the user has a saved preference that blocks it.",
    "codex-history-policy": "the Browser Use history-access policy blocks it.",
    "codex-network-policy": "the admin-enforced policy blocks it.",
    "codex-network-policy-unavailable":
        "the admin-enforced policy could not be verified. Please try again later.",
    "user_decision": "the user denied permission for this request.",
    "guardian-auto-review": "Auto-review denied permission for this request.",
    "cancel": "the permission request was dismissed; no explicit denial was made.",
    "unknown": "the permission request returned an unrecognized action; no explicit denial was made.",
}


class BrowserUseSecurityError(PermissionError):
    """Official `yt extends Error` with `name = "BrowserUseSecurityError"`."""

    name = "BrowserUseSecurityError"

    def __init__(self, reason: str, message: str = "", detail: str = "") -> None:
        if reason not in REASONS:
            raise ValueError(f"unknown browser security reason: {reason}")
        source, retryable = REASONS[reason]
        self.reason = reason
        self.decision_source = source
        self.retryable = retryable
        self.reason_message = message
        self.detail = detail
        template = RETRYABLE_WRAPPER if retryable else NON_RETRYABLE_WRAPPER
        super().__init__(template.format(message=message, detail=detail).strip())

    def __str__(self) -> str:
        return self.args[0] if self.args else self.name


def approval_failure(task: str, reason: str, display_name: str = DEFAULT_DISPLAY_NAME) -> str:
    """Official approval-mediated failure sentence:
    `<name> cannot <task> because <reason phrase>.`"""
    phrase = REASON_PHRASES.get(reason, REASON_PHRASES["user_decision"])
    return f"{display_name} cannot {task} because {phrase}"


__all__ = [
    "AUTO_REVIEW_INCOMPLETE",
    "AUTO_REVIEW_NEEDS_TOOL",
    "AUTO_REVIEW_UNSUPPORTED",
    "DEFAULT_DISPLAY_NAME",
    "ConsentRequest",
    "auto_review_error",
    "origin_consent",
    "history_consent",
    "upload_consent",
    "download_consent",
    "full_cdp_consent",
    "BrowserUseSecurityError",
    "REASONS",
    "REASON_PHRASES",
    "RETRYABLE_WRAPPER",
    "NON_RETRYABLE_WRAPPER",
    "approval_failure",
]
