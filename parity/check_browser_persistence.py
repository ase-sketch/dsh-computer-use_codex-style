"""Gate: BR-17 prompt-result persistence matches the official bundle.

Every token, the section mapping, the history mode and the 300 s turn-grant TTL
are re-extracted from the packaged browser-service.mjs and compared with
computer_use/browser_persistence.py. The store itself is then round-tripped
through a temp file and exercised through BrowserSecurityPolicy.

Usage:  python parity/check_browser_persistence.py
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: official token -> our module attribute
TOKENS = {
    "fB": "APPROVAL_MODE",
    "JX": "HISTORY_APPROVAL_MODE",
    "YX": "IAB_HISTORY_APPROVAL_MODE",
    "qm": "NEVER_ASK",
    "ZX": "DISABLED",
    "QX": "DISABLE_AUTO_REVIEW",
    "eJ": "ORIGINS",
    "tJ": "FULL_CDP",
    "rJ": "DOWNLOADS",
    "nJ": "UPLOADS",
    "Um": "ALLOWED",
    "jm": "DENIED",
    "oJ": "DOWNLOAD_APPROVAL_MODE",
    "iJ": "UPLOAD_APPROVAL_MODE",
}

#: the evidence offsets the module docstring must cite (documentation gate).
REQUIRED_EVIDENCE = ("@1103469", "@1106166", "@1108855", "@1111389")

#: official "name=value" pairs inside the token block.
PAIR_RE = re.compile(r'([A-Za-z_$][A-Za-z0-9_$]*)=("(?:[^"\\]|\\.)*"|\d+\*1e3)')


def official_root() -> Path | None:
    hits = sorted(glob.glob(os.path.expanduser("~/.codex/plugins/cache/openai-bundled/browser/*")))
    return Path(hits[-1]) if hits else None


def official_tokens(service: str) -> dict[str, str]:
    anchor = service.find('var fB="approval_mode"')
    if anchor == -1:
        return {}
    window = service[anchor:anchor + 600]
    found: dict[str, str] = {}
    for match in PAIR_RE.finditer(window):
        name, raw = match.group(1), match.group(2)
        if name in TOKENS:
            found[name] = raw.strip('"') if raw.startswith('"') else "300000"
    return found


def main() -> int:
    from computer_use import browser_persistence as p
    from computer_use.browser_checks import BrowserSecurityPolicy

    failures: list[str] = []
    root = official_root()
    if root is None:
        print("SKIP official browser package not found")
        return 0
    service = (root / "scripts" / "browser-service.mjs").read_text(
        encoding="utf-8", errors="replace"
    )
    tokens = official_tokens(service)
    print(f"official tokens extracted: {len(tokens)}/{len(TOKENS)}")
    if len(tokens) != len(TOKENS):
        failures.append(f"could not extract every official token: {sorted(set(TOKENS) - set(tokens))}")
    for name, attribute in sorted(TOKENS.items()):
        expected = tokens.get(name)
        actual = getattr(p, attribute)
        marker = "OK " if actual == expected else "FAIL"
        print(f"  [{marker}] {name} -> {attribute} = {actual!r}")
        if expected is not None and actual != expected:
            failures.append(f"{attribute} is {actual!r}, official {expected!r}")

    # sJ = 300 * 1e3 (the turn-grant TTL).
    ttl_ok = "sJ=300*1e3" in service
    print(f"  [{'OK ' if ttl_ok else 'FAIL'}] sJ=300*1e3 present")
    if not ttl_ok or p.TURN_GRANT_TTL_MS != 300_000:
        failures.append("turn-grant TTL is not the official 300000 ms")

    # The official zw()/Hw() switch must resolve to the same sections.
    zw = ('case"origin":return eJ' in service
          and 'e.transferKind==="download"?rJ:nJ' in service
          and 'case"fullCdp":return tJ' in service)
    print(f"  [{'OK ' if zw else 'FAIL'}] official zw() switch extracted")
    if not zw:
        failures.append("official section switch zw() not found")
    expected_sections = {
        "origin": tokens.get("eJ", "origins"),
        "fileTransfer:download": tokens.get("rJ", "downloads"),
        "fileTransfer:upload": tokens.get("nJ", "uploads"),
        "fullCdp": tokens.get("tJ", "full_cdp"),
    }
    actual_sections = {
        "origin": p.section_for("origin"),
        "fileTransfer:download": p.section_for("fileTransfer", transfer_kind="download"),
        "fileTransfer:upload": p.section_for("fileTransfer", transfer_kind="upload"),
        "fullCdp": p.section_for("fullCdp"),
    }
    for key, expected in expected_sections.items():
        actual = actual_sections.get(key)
        marker = "OK " if actual == expected else "FAIL"
        print(f"  [{marker}] section {key} -> {actual!r}")
        if actual != expected:
            failures.append(f"section {key} is {actual!r}, official {expected!r}")

    # Official Hw(): iab -> iab_history_approval_mode, else history_approval_mode.
    hw = (p.history_section(iab=True) == tokens.get("YX", "iab_history_approval_mode")
          and p.history_section(iab=False) == tokens.get("JX", "history_approval_mode"))
    print(f"  [{'OK ' if hw else 'FAIL'}] official Hw() history section mapping")
    if not hw:
        failures.append("history_section does not match Hw()")

    # Official fJ(): never_ask -> approve, disabled -> deny, else always_ask.
    fJ = (p.history_decision_for(tokens.get("qm", "never_ask")) == "approve"
          and p.history_decision_for(tokens.get("ZX", "disabled")) == "deny"
          and p.history_decision_for(None) == "always_ask")
    print(f"  [{'OK ' if fJ else 'FAIL'}] official fJ() mode mapping")
    if not fJ:
        failures.append("history_decision_for does not match fJ()")

    # Official pJ(): approve -> allowed, decline -> denied, opposite list cleared.
    store = p.PersistedConsentStore()
    store.record(p.ORIGINS, "https://a.test", "approve", scope="global")
    if store.decision(p.ORIGINS, "https://a.test") != "approve":
        failures.append("pJ() approve did not land in the allowed list")
    store.record(p.ORIGINS, "https://a.test", "deny", scope="global")
    if store.decision(p.ORIGINS, "https://a.test") != "deny":
        failures.append("pJ() decline did not move the key into the denied list")
    bucket = store.mode(p.ORIGINS)
    if isinstance(bucket, dict) and bucket.get(p.ALLOWED):
        failures.append("pJ() left the key in the opposite list")
    print("  [OK ] official pJ() allowed/denied move")

    # Official lJ(): a global origin never-ask writes approval_mode.
    store2 = p.PersistedConsentStore()
    store2.record_never_ask_origin(scope="global")
    if store2.mode(p.APPROVAL_MODE) != tokens.get("qm", "never_ask"):
        failures.append("lJ() never-ask did not write approval_mode")
    else:
        print("  [OK ] official lJ() never-ask marker")

    # Disk round trip + policy wiring (a real write, in a temp dir).
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "browser-consent.json"
        writer = p.PersistedConsentStore(path=path)
        writer.record(p.ORIGINS, "https://persist.test", "approve", scope="global")
        writer.save()
        document = json.loads(path.read_text(encoding="utf-8"))
        stored = document.get("global", {}).get(p.ORIGINS, {}).get(p.ALLOWED)
        if stored != ["https://persist.test"]:
            failures.append("the persisted document does not carry the official sections")
        else:
            print("  [OK ] persisted document carries the official sections")
        asks: list[int] = []
        policy = BrowserSecurityPolicy.from_disk(path)
        policy.gate(
            "browser-origin-access",
            "https://persist.test",
            approver=lambda request: asks.append(1) or "deny",
            origin="https://persist.test",
        )
        if asks:
            failures.append("a persisted approval asked the user again")
        else:
            print("  [OK ] persisted approval is not asked again")
        denied_path = Path(tmp) / "denied.json"
        denied = p.PersistedConsentStore(path=denied_path)
        denied.record(p.ORIGINS, "https://blocked.test", "deny", scope="global")
        denied.save()
        blocked = BrowserSecurityPolicy.from_disk(denied_path)
        try:
            blocked.gate(
                "browser-origin-access",
                "https://blocked.test",
                approver=lambda request: "approve",
                origin="https://blocked.test",
            )
        except Exception as error:
            if getattr(error, "reason", "") != "persisted_user_denied":
                failures.append(f"persisted deny raised {error!r}")
            else:
                print("  [OK ] persisted denial fails closed as persisted_user_denied")
        else:
            failures.append("persisted denial was not enforced")

    # Official maybeAutoAnswerBrowserUseRequest fallback: approval_mode ==
    # never_ask auto-approves a fresh origin without asking.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "never.json"
        marker = p.PersistedConsentStore(path=path)
        marker.record_never_ask_origin()
        marker.save()
        asks: list[int] = []
        policy = BrowserSecurityPolicy.from_disk(path)
        policy.gate(
            "browser-origin-access",
            "https://brand-new.test",
            approver=lambda request: asks.append(1) or "deny",
            origin="https://brand-new.test",
        )
        if asks:
            failures.append("approval_mode=never_ask did not suppress the prompt")
        else:
            print("  [OK ] approval_mode=never_ask auto-approves a fresh origin")

    # Official precedence: a conversation denial beats a global allow.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "precedence.json"
        store3 = p.PersistedConsentStore(path=path)
        store3.record(p.ORIGINS, "https://x.test", "approve", scope="global")
        store3.record(
            p.ORIGINS, "https://x.test", "deny", scope="session", conversation_id="conv-1"
        )
        store3.save()
        policy = BrowserSecurityPolicy.from_disk(path, conversation_id="conv-1")
        verdict = policy.persisted_decision("browser-origin-access", "https://x.test")
        if verdict != "deny":
            failures.append(f"conversation denial did not beat the global allow: {verdict!r}")
        else:
            print("  [OK ] conversation denial beats a global allow")

    # Documentation gate: the module must still cite its official evidence.
    doc = p.__doc__ or ""
    missing = [offset for offset in REQUIRED_EVIDENCE if offset not in doc]
    print(f"  [{'OK ' if not missing else 'FAIL'}] official evidence offsets cited")
    if missing:
        failures.append(f"browser_persistence docstring lost the evidence offsets: {missing}")

    api = (ROOT / "computer_use" / "browser_api.py").read_text(encoding="utf-8")
    if "enable_persistence" not in api or "set_turn_context" not in api:
        failures.append("BrowserSurface has no persistence wiring hook")
    else:
        print("  [OK ] BrowserSurface exposes enable_persistence + set_turn_context")

    for line in failures:
        print("FAIL " + line)
    print("browser persistence: " + ("PASS" if not failures else "RED"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
