"""P6 browser-URL policy gate (BR-14) recovered from the Windows helper.

The official JS layer only calls the host hook
`this.runtime.assertBrowserUrlAllowed?.(url)` (browser-service.mjs, byte offsets
572366 in runNavigation and 576588 in ensureUrlPolicyAllowed). The Windows helper
implements it as `src/policy/url_policy.rs` and fails closed with four verbatim
sentences, recovered from `out/exe/strings_all.txt:18208` (RVA 0x132af7).

The reference implementation lives in the Rust helper; this module carries the
same decision table and the same four sentences on the Python side so the engine
that actually serves DSH screens enforces the gate instead of failing open.
Ghidra never recovered the helper function; the angr pass
(`angr-sky/rust/140076f73_sub_140076f73.rs`) shows WinHttpCrackUrl + the family
list, and the string table fixes the wording.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# --- Verbatim official sentences (strings_all.txt:18208, RVA 0x132af7) ------

URL_NOT_ALLOWED = (
    "Computer Use has been stopped for this turn because it is not allowed on the current "
    "browser URL. Stop your work and send a final message noting why Computer Use ended. "
    "Note that Computer Use is not allowed on this URL even if the user navigates to it "
    "themselves."
)
URL_UNVERIFIED = (
    "Computer Use has been stopped for this turn because it could not verify whether the "
    "current browser URL is allowed. Stop your work and send a final message noting why "
    "Computer Use ended."
)
URL_UNDETERMINED = (
    "Computer Use has been stopped for this turn because it could not determine the current "
    "browser URL on Windows with enough confidence to enforce policy. Stop your work and "
    "send a final message noting why Computer Use ended."
)
URL_FAMILY_UNSUPPORTED = (
    "Computer Use has been stopped for this turn because browser URL policy enforcement is "
    "not yet supported for the current Windows browser. Stop your work and send a final "
    "message noting why Computer Use ended."
)

#: The four sentences in official string-table order.
URL_GATE_MESSAGES = (
    URL_NOT_ALLOWED,
    URL_UNVERIFIED,
    URL_UNDETERMINED,
    URL_FAMILY_UNSUPPORTED,
)

#: Browser family list from strings_all.txt:18323 (RVA 0x13633d). The first four
#: are the Chromium families the policy supports; the rest fall through to the
#: fourth sentence.
BROWSER_FAMILIES = ("msedge", "chrome", "brave", "opera", "iexplore", "firefox", "browser", "dia")
SUPPORTED_FAMILIES = frozenset({"msedge", "chrome", "brave", "opera"})
UNSUPPORTED_FAMILIES = frozenset(BROWSER_FAMILIES) - SUPPORTED_FAMILIES


class BrowserUrlPolicyError(RuntimeError):
    """The official `assertBrowserUrlAllowed` failure.

    The sentence is the contract: it tells the model to stop the turn, so it must
    surface byte-for-byte without the BrowserUseSecurityError wrapper.
    """

    name = "BrowserUrlPolicyError"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class UrlPolicy:
    """Configurable allow/deny host lists.

    Official policy is server-side; DSH makes it explicit and fail closed. A
    missing policy source is the transport-error path and fails closed with the
    second sentence (the official path only fails open when the *status service*
    is unreachable, not the URL policy itself).
    """

    deny_hosts: tuple[str, ...] = field(default_factory=tuple)
    allow_hosts: tuple[str, ...] = field(default_factory=tuple)
    available: bool = True

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "UrlPolicy":
        env = environ if environ is not None else dict(os.environ)
        deny = _split(env.get("COMPUTER_USE_BROWSER_URL_DENY"))
        allow = _split(env.get("COMPUTER_USE_BROWSER_URL_ALLOW"))
        available = str(env.get("COMPUTER_USE_BROWSER_URL_POLICY") or "1").strip().lower() not in {
            "0",
            "off",
            "unavailable",
        }
        return cls(deny_hosts=deny, allow_hosts=allow, available=available)

    def host_allowed(self, url: str) -> bool | None:
        """True/False when the host is decided, None when the policy is silent."""
        host = _host_of(url)
        if not host:
            return False
        lowered = host.lower()
        for item in self.deny_hosts:
            if lowered == item or lowered.endswith("." + item):
                return False
        if self.allow_hosts:
            for item in self.allow_hosts:
                if lowered == item or lowered.endswith("." + item):
                    return True
            return False
        return None


def _split(raw: str | None) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in str(raw or "").split(",") if item.strip())


def _host_of(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"}:
        return ""
    return parts.hostname or ""


def assert_browser_url_allowed(
    url: str | None,
    *,
    family: str = "",
    security_mode: str = "",
    policy: UrlPolicy | None = None,
) -> None:
    """Fail closed exactly like the official helper callback.

    Order (mirrors the four official sentences):
      1. policy denies the URL          -> URL_NOT_ALLOWED
      2. policy source unavailable      -> URL_UNVERIFIED
      3. URL could not be determined    -> URL_UNDETERMINED
      4. browser family is unsupported  -> URL_FAMILY_UNSUPPORTED
    """
    if security_mode == "disabled-for-local-testing":
        return
    resolved = policy or UrlPolicy.from_env()
    fam = (family or "").strip().lower()
    if fam in UNSUPPORTED_FAMILIES:
        raise BrowserUrlPolicyError(URL_FAMILY_UNSUPPORTED)
    if not url:
        raise BrowserUrlPolicyError(URL_UNDETERMINED)
    if not resolved.available:
        raise BrowserUrlPolicyError(URL_UNVERIFIED)
    decision = resolved.host_allowed(url)
    if decision is False:
        raise BrowserUrlPolicyError(URL_NOT_ALLOWED)
    if decision is None and _host_of(url) == "":
        # A URL we cannot parse to an http(s) host is not "determined".
        raise BrowserUrlPolicyError(URL_UNDETERMINED)


__all__ = [
    "BROWSER_FAMILIES",
    "SUPPORTED_FAMILIES",
    "UNSUPPORTED_FAMILIES",
    "URL_FAMILY_UNSUPPORTED",
    "URL_GATE_MESSAGES",
    "URL_NOT_ALLOWED",
    "URL_UNDETERMINED",
    "URL_UNVERIFIED",
    "BrowserUrlPolicyError",
    "UrlPolicy",
    "assert_browser_url_allowed",
]
