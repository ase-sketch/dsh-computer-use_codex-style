from __future__ import annotations

import os
from pathlib import Path


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def locate_helper() -> Path | None:
    override = (os.environ.get("COMPUTER_USE_HELPER") or os.environ.get("SKY_HELPER") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    here = Path(__file__).resolve().parents[1]
    native = here / "helper-rs" / "target" / "release" / "dsh-computer-use.exe"
    if native.is_file():
        return native
    # The tracked, shipped helper (`scripts/ship-helper.ps1` copies the release build here).
    # Kept after the build output so a local `cargo build` wins during development, and it is
    # what keeps a fresh checkout runnable without a Rust toolchain.
    for shipped in sorted((here / "helper-rs" / "bin").glob("*/dsh-computer-use.exe")):
        if shipped.is_file():
            return shipped
    sky = _local_appdata() / "OpenAI" / "Codex" / "runtimes" / "cua_node"
    if sky.is_dir():
        matches = list(sky.glob("**/codex-computer-use.exe"))
        if matches:
            return matches[0]
    return None


def locate_codex_cli() -> Path | None:
    override = (os.environ.get("CODEX_CLI_PATH") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    root = _local_appdata() / "OpenAI" / "Codex" / "bin"
    if root.is_dir():
        matches = list(root.glob("**/codex.exe"))
        if matches:
            return matches[0]
    return None


def helper_env() -> dict[str, str]:
    env = os.environ.copy()
    cli = locate_codex_cli()
    if cli is not None:
        env.setdefault("CODEX_CLI_PATH", str(cli))
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    if env.get("SKY_CUA_NATIVE_PIPE", "").strip() == "":
        flag = os.environ.get("COMPUTER_USE_PIPE_SPAWN", "").strip().lower()
        if flag in {"1", "true", "yes"}:
            env["SKY_CUA_NATIVE_PIPE"] = "1"
    return env
