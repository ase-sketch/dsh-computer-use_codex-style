"""BR-17: official browser consent (prompt-result) persistence.

The official browser service persists the outcome of every approval prompt. The
whole contract is recoverable from the packaged bundle
(~/.codex/plugins/cache/openai-bundled/browser/26.903.61454/scripts/browser-service.mjs,
1,307,011 B). Byte offsets below are 0-based offsets in that file and are the
evidence this module is gated against.

Writers (all four funnel into '$w'):

* 'handleOriginPromptResult'         @1106166 -> resource {kind:"origin", origin}
* 'handleFileTransferPromptResult'   @1106319 -> {kind:"fileTransfer", origin, transferKind}
* 'handleFullCdpPromptResult'        @1106501 -> resource {kind:"fullCdp", origin}
* 'handleHistoryPromptResult'        @1106656 -> global history mode only
* decision writer '$w' / 'uJ' / 'lJ' @1108855
* list writer 'pJ' @1110030, read 'fJ' / section key 'zw' @1111389
* section + value tokens @1103469
  (fB, JX, YX, qm, ZX, QX, eJ, tJ, rJ, nJ, Um, jm, sJ)
* per-turn origin grant 'wJ' / 'yJ' / 'bJ' and the 300 s TTL 'sJ' @1103469

Official semantics reproduced here:

1. two scopes -- 'config.global' survives the conversation,
   'config.session(conversationId)' lives with it. The elicitation 'persist'
   meta chooses: "always" -> global, "session" -> conversation, absent ->
   nothing is written ('wB').
2. the section key is a function of the resource kind ('zw'):
   origin -> 'origins', download -> 'downloads', upload -> 'uploads',
   fullCdp -> 'full_cdp'.
3. list values are 'allowed' / 'denied' and the opposite list is cleared
   ('pJ': [p, m] = approve ? [allowed, denied] : [denied, allowed]).
   The stored key is the origin with '*' and backslash escaped ('AJ' @1114431);
   both the raw and the escaped form are removed from the opposite list.
4. a *global* origin approval that also carries the never-ask marker writes
   'approval_mode = "never_ask"' instead of touching the origin list.
5. history permission read ('getPersistedHistoryPermission' / 'fJ'):
   'never_ask' -> approve, 'disabled' -> deny, anything else asks. The key is
   'iab_history_approval_mode' for the IAB backend and 'history_approval_mode'
   otherwise ('Hw' @1111389).
6. a per-turn, in-memory origin grant ('wJ', kept in the 'Ps' map) expires after
   'sJ = 300_000' ms and is invalidated by a new turn id or a different origin
   ('yJ' / 'bJ').

Container vs. semantics (documented divergence): the official container is
Codex's own config / session store (TOML + session state). DSH has no such
store, so this module keeps the *official section and value tokens verbatim* in
a dedicated JSON document. The document path is therefore DSH-specific and the
host must point at it explicitly with 'DSH_BROWSER_CONSENT_PATH' or
'BrowserSurface(consent_path=...)'; nothing is written into the user's home
directory unless the host asks for it (workspace rule 5).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- Official tokens (browser-service.mjs @1103469) -------------------------

APPROVAL_MODE = "approval_mode"
HISTORY_APPROVAL_MODE = "history_approval_mode"
IAB_HISTORY_APPROVAL_MODE = "iab_history_approval_mode"
NEVER_ASK = "never_ask"
DISABLED = "disabled"
DISABLE_AUTO_REVIEW = "disable_auto_review"
ORIGINS = "origins"
FULL_CDP = "full_cdp"
DOWNLOADS = "downloads"
UPLOADS = "uploads"
ALLOWED = "allowed"
DENIED = "denied"
DOWNLOAD_APPROVAL_MODE = "download_approval_mode"
UPLOAD_APPROVAL_MODE = "upload_approval_mode"

#: 'sJ = 300 * 1e3' -- the per-turn origin grant lifetime.
TURN_GRANT_TTL_MS = 300_000

#: The section keys in the official declaration order.
SECTION_KEYS = (
    APPROVAL_MODE,
    HISTORY_APPROVAL_MODE,
    IAB_HISTORY_APPROVAL_MODE,
    ORIGINS,
    FULL_CDP,
    DOWNLOADS,
    UPLOADS,
    DOWNLOAD_APPROVAL_MODE,
    UPLOAD_APPROVAL_MODE,
)

#: Official mode token for the always-ask default (not stored).
ALWAYS_ASK = "always_ask"

#: History mode tokens -> decision ('fJ').
HISTORY_MODE_DECISIONS = {NEVER_ASK: "approve", DISABLED: "deny", "": ALWAYS_ASK}

#: DSH store container (the official container is Codex's config/session store).
ENV_CONSENT_PATH = "DSH_BROWSER_CONSENT_PATH"
DEFAULT_CONSENT_DIRECTORY = ".dsh"
DEFAULT_CONSENT_FILENAME = "browser-consent.json"
STORE_VERSION = 1


def default_consent_path() -> Path:
    """'$DSH_BROWSER_CONSENT_PATH' or '~/.dsh/browser-consent.json'."""
    override = (os.environ.get(ENV_CONSENT_PATH) or "").strip()
    if override:
        return Path(override)
    return Path.home() / DEFAULT_CONSENT_DIRECTORY / DEFAULT_CONSENT_FILENAME


def section_for(kind: str, *, transfer_kind: str = "") -> str | None:
    """Official 'zw(resource)' @1111389."""
    if kind == "origin":
        return ORIGINS
    if kind == "fileTransfer":
        return DOWNLOADS if transfer_kind == "download" else UPLOADS
    if kind == "fullCdp":
        return FULL_CDP
    return None


def escape_origin(origin: str) -> str:
    """Official 'AJ' @1114431: escape the glob metacharacters. The stored value is
    used as a plain map key downstream, so only the escaping matters."""
    out: list[str] = []
    for char in str(origin):
        if char == "*":
            out.append("\\*")
        elif char == "\\":
            out.append("\\\\")
        else:
            out.append(char)
    return "".join(out)


#: Our check ids -> the official resource kind they persist as. Checks absent
#: from this map have no persisted state ('hJ(resource) == false').
CHECK_RESOURCE_KINDS: dict[str, str] = {
    "browser-origin-access": "origin",
    "file-download": "fileTransfer",
    "file-upload": "fileTransfer",
    "full-cdp": "fullCdp",
    "raw-cdp-destination-url": "fullCdp",
    "page-asset-download": "fileTransfer",
    "page-asset-cross-origin-fetch": "fileTransfer",
}

#: fileTransfer resources that are downloads rather than uploads.
DOWNLOAD_CHECKS = frozenset(
    {"file-download", "page-asset-download", "page-asset-cross-origin-fetch"}
)


def resource_for_check(check: str) -> tuple[str, str] | None:
    """(kind, transfer_kind) for a DSH check id, or None when not persisted."""
    kind = CHECK_RESOURCE_KINDS.get(str(check))
    if kind is None:
        return None
    if kind == "fileTransfer":
        return kind, ("download" if check in DOWNLOAD_CHECKS else "upload")
    return kind, ""


def section_for_check(check: str) -> str | None:
    resource = resource_for_check(check)
    if resource is None:
        return None
    return section_for(resource[0], transfer_kind=resource[1])


def never_ask_mode_key(check: str) -> str | None:
    """Official yB(resource): which approval_mode section governs a check.

    origin -> approval_mode, download -> download_approval_mode,
    upload -> upload_approval_mode, fullCdp -> None (never_ask cannot apply).
    """
    resource = resource_for_check(check)
    if resource is None:
        return None
    kind, transfer_kind = resource
    if kind == "origin":
        return APPROVAL_MODE
    if kind == "fileTransfer":
        return DOWNLOAD_APPROVAL_MODE if transfer_kind == "download" else UPLOAD_APPROVAL_MODE
    return None


def history_section(*, iab: bool = False) -> str:
    """Official 'Hw' @1111389."""
    return IAB_HISTORY_APPROVAL_MODE if iab else HISTORY_APPROVAL_MODE


def history_decision_for(mode: Any) -> str:
    """Official 'fJ': stored mode -> 'approve' / 'deny' / 'always_ask'."""
    if mode == NEVER_ASK:
        return "approve"
    if mode == DISABLED:
        return "deny"
    return ALWAYS_ASK


# --- Document store ---------------------------------------------------------


@dataclass
class PersistedConsentStore:
    """The official 'config.global' + 'config.session(id)' document.

    'path=None' keeps the store in memory only (still with a real global/session
    split); a path enables the on-disk round trip.
    """

    path: Path | None = None
    global_sections: dict[str, Any] = field(default_factory=dict)
    session_sections: dict[str, dict[str, Any]] = field(default_factory=dict)

    # -- container -----------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str | None = None) -> "PersistedConsentStore":
        store = cls(path=Path(path) if path else None)
        if store.path is None or not store.path.is_file():
            return store
        try:
            data = json.loads(store.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return store
        if isinstance(data, dict):
            global_sections = data.get("global")
            if isinstance(global_sections, dict):
                store.global_sections = dict(global_sections)
            sessions = data.get("sessions")
            if isinstance(sessions, dict):
                store.session_sections = {
                    str(cid): dict(sections)
                    for cid, sections in sessions.items()
                    if isinstance(sections, dict)
                }
        return store

    def to_document(self) -> dict[str, Any]:
        return {
            "version": STORE_VERSION,
            "global": self.global_sections,
            "sessions": self.session_sections,
        }

    def save(self) -> bool:
        """Atomic write. No path -> in-memory only, returns False."""
        if self.path is None:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(self.to_document(), indent=2, sort_keys=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(blob, encoding="utf-8")
        os.replace(temporary, self.path)
        return True

    # -- scopes --------------------------------------------------------------

    def sections(self, scope: str = "global", *, conversation_id: str = "") -> dict[str, Any]:
        if scope == "global":
            return self.global_sections
        if not conversation_id:
            return {}
        return self.session_sections.setdefault(str(conversation_id), {})

    # -- reads ---------------------------------------------------------------

    def decision(
        self,
        section: str | None,
        origin: str,
        *,
        scope: str = "global",
        conversation_id: str = "",
    ) -> str | None:
        """Official 'fJ'-style read for a resource-list section."""
        if section is None:
            return None
        bucket = self.sections(scope, conversation_id=conversation_id).get(section)
        if not isinstance(bucket, dict):
            return None
        key = escape_origin(origin)
        if key in _as_list(bucket.get(ALLOWED)):
            return "approve"
        if key in _as_list(bucket.get(DENIED)):
            return "deny"
        return None

    def mode(self, section: str, *, scope: str = "global", conversation_id: str = "") -> Any:
        return self.sections(scope, conversation_id=conversation_id).get(section)

    def history_decision(
        self, *, iab: bool = False, scope: str = "global", conversation_id: str = ""
    ) -> str:
        return history_decision_for(
            self.mode(history_section(iab=iab), scope=scope, conversation_id=conversation_id)
        )

    # -- writes --------------------------------------------------------------

    def record(
        self,
        section: str | None,
        origin: str,
        decision: str,
        *,
        scope: str = "global",
        conversation_id: str = "",
    ) -> bool:
        """Official 'pJ': move the key into the approved or denied list and clear
        it from the opposite one. 'approve' -> allowed, anything else -> denied."""
        if section is None or not _scope_available(scope, conversation_id):
            return False
        sections = self.sections(scope, conversation_id=conversation_id)
        bucket = sections.get(section)
        if not isinstance(bucket, dict):
            bucket = {ALLOWED: [], DENIED: []}
        else:
            bucket = {
                ALLOWED: list(_as_list(bucket.get(ALLOWED))),
                DENIED: list(_as_list(bucket.get(DENIED))),
            }
        key = escape_origin(origin)
        target, opposite = (ALLOWED, DENIED) if decision == "approve" else (DENIED, ALLOWED)
        # Official removes both the escaped ('h') and the raw ('Lm') form.
        for candidate in {key, str(origin)}:
            if candidate in bucket[opposite]:
                bucket[opposite].remove(candidate)
        if key not in bucket[target]:
            bucket[target].append(key)
        sections[section] = bucket
        return True

    def record_never_ask_origin(
        self, *, scope: str = "global", conversation_id: str = ""
    ) -> bool:
        """Official 'lJ': a global origin approval with the never-ask marker writes
        'approval_mode = "never_ask"' and returns."""
        if not _scope_available(scope, conversation_id):
            return False
        self.sections(scope, conversation_id=conversation_id)[APPROVAL_MODE] = NEVER_ASK
        return True

    def record_history(
        self,
        decision: str,
        *,
        iab: bool = False,
        scope: str = "global",
        conversation_id: str = "",
    ) -> bool:
        """Official 'handleHistoryPromptResult': only a global 'never_ask'."""
        if decision != "approve" or scope != "global":
            return False
        self.sections("global")[history_section(iab=iab)] = NEVER_ASK
        return True


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _scope_available(scope: str, conversation_id: str) -> bool:
    """Official: r==="global" ? global : Vw(conversationId) ? session : undefined."""
    if scope == "global":
        return True
    return bool(conversation_id)


# --- Per-turn origin grant (official 'Ps' map) ------------------------------


@dataclass
class TurnGrant:
    origin: str
    turn_id: str
    expires_at: float


class TurnGrants:
    """Official 'wJ' / 'yJ' / 'bJ': a one-turn, 300 s origin grant."""

    def __init__(self, ttl_ms: int = TURN_GRANT_TTL_MS) -> None:
        self.ttl_ms = int(ttl_ms)
        self._entries: dict[str, TurnGrant] = {}

    def grant(self, session_id: str, turn_id: str, origin: str) -> None:
        if not session_id or not turn_id or not origin:
            return
        self._entries[str(session_id)] = TurnGrant(
            origin=str(origin),
            turn_id=str(turn_id),
            expires_at=time.time() + self.ttl_ms / 1000.0,
        )

    def active(self, session_id: str, turn_id: str, origin: str) -> bool:
        entry = self._entries.get(str(session_id))
        if entry is None:
            return False
        if entry.expires_at <= time.time():
            self._entries.pop(str(session_id), None)
            return False
        if entry.turn_id != str(turn_id) or entry.origin != str(origin):
            self._entries.pop(str(session_id), None)
            return False
        return True

    def clear(self) -> None:
        self._entries.clear()


__all__ = [
    "ALLOWED",
    "ALWAYS_ASK",
    "APPROVAL_MODE",
    "CHECK_RESOURCE_KINDS",
    "DEFAULT_CONSENT_DIRECTORY",
    "DEFAULT_CONSENT_FILENAME",
    "DENIED",
    "DISABLE_AUTO_REVIEW",
    "DISABLED",
    "DOWNLOAD_APPROVAL_MODE",
    "DOWNLOAD_CHECKS",
    "DOWNLOADS",
    "ENV_CONSENT_PATH",
    "FULL_CDP",
    "HISTORY_APPROVAL_MODE",
    "HISTORY_MODE_DECISIONS",
    "IAB_HISTORY_APPROVAL_MODE",
    "NEVER_ASK",
    "ORIGINS",
    "PersistedConsentStore",
    "SECTION_KEYS",
    "STORE_VERSION",
    "TURN_GRANT_TTL_MS",
    "TurnGrant",
    "TurnGrants",
    "UPLOADS",
    "UPLOAD_APPROVAL_MODE",
    "default_consent_path",
    "escape_origin",
    "history_decision_for",
    "history_section",
    "never_ask_mode_key",
    "resource_for_check",
    "section_for",
    "section_for_check",
]
