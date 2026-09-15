"""Official src/codex/notify_config.rs — DSH analog of Codex notify hook + feature_status."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

NOTIFY_HOOK_FAILED = "failed to update Windows Computer Use Codex notify hook: "
PREVIOUS_NOTIFY_MISSING = "missing value for --previous-notify"
TURN_ENDED_MISSING = "missing turn-ended payload"
PREVIOUS_NOTIFY_FAILED = "computer-use previous notify hook failed: "
SKIPPED_MISSING_COMMAND = "computer-use previous notify hook skipped: missing command"
SKIPPED_INVALID_ARGS = "computer-use previous notify hook skipped: invalid arguments"


def config_home() -> Path:
    raw = os.environ.get("DSH_HOME") or os.environ.get("CODEX_HOME") or str(Path.home() / ".dsh")
    return Path(raw)


def feature_status() -> dict[str, Any]:
    from computer_use.policy import default_app_access

    return {
        "allowBrowserAndComputerUse": True,
        "allow_browser_and_computer_use": True,
        "featureRequirements": {"computerUse": True},
        "features": {"computerUse": True, "computer_use": True},
        "allow_persistent_approval": True,
        "allowPersistentApproval": True,
        "defaultAppAccess": default_app_access(),
        "default_app_access": default_app_access(),
    }


def notify_approval(app: str, display_name: str, *, risk_level: str = "low", allow_persistent: bool = True) -> dict[str, Any]:
    level = risk_level if risk_level in {"high", "low"} else "low"
    return {
        "AppApprovalRequest": True,
        "riskLevel": level,
        "allowPersistentApproval": bool(allow_persistent),
        "notify": True,
        "app": app,
        "displayName": display_name or app,
    }


def write_notify_config(session_id: str, turn_id: str, *, previous_notify: str | None = None) -> Path:
    """write Codex notify config analog: computer-use/config.json under DSH_HOME."""
    root = config_home() / "computer-use"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"{NOTIFY_HOOK_FAILED}create Codex config directory") from exc
    payload: dict[str, Any] = {
        "notify": True,
        "notify=": True,
        "feature_status": feature_status(),
        "turn-ended": {"session_id": session_id, "turn_id": turn_id, "conversation": session_id},
        "previous-notify": previous_notify,
    }
    path = root / "config.json"
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        raise OSError(f"{NOTIFY_HOOK_FAILED}write Codex notify config") from exc
    toml = config_home() / "config.toml"
    try:
        if not toml.exists():
            toml.write_text("[computer-use]\nnotify = true\n", encoding="utf-8")
    except OSError:
        pass
    return path


def apply_previous_notify(argv: list[str] | None = None) -> dict[str, Any]:
    args = list(argv or [])
    if "--previous-notify" in args:
        idx = args.index("--previous-notify")
        if idx + 1 >= len(args) or not str(args[idx + 1]).strip():
            raise TypeError(PREVIOUS_NOTIFY_MISSING)
        previous = str(args[idx + 1])
        return {"ok": True, "previous-notify": previous}
    if "turn-ended" in args and args.count("turn-ended") and len(args) < 2:
        raise TypeError(TURN_ENDED_MISSING)
    if not args:
        raise TypeError(SKIPPED_MISSING_COMMAND)
    if any(item is None for item in args):
        raise TypeError(SKIPPED_INVALID_ARGS)
    return {"ok": True}
