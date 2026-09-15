# dsh-computer-use (macOS Swift)

Native macOS Computer Use helper for DeepSeek Harness.

Official dump note: `bin-swift/codex-computer-use-swift.exe` is a **Windows PE** Swift build
(`ComputerUse_Windows_Swift_…_main`). The Mac **API surface** is `sky.window`
(`computer_use/prompts/sky-window-api.md`): app-string targeting, AX tree text,
`paste` / `select_text`, default do not steal focus.

This binary is original code (AX + CGEvent + NSWorkspace). It does not ship official EXEs.

## Build (on a Mac)

```bash
cd helper-swift
swift build -c release
# .build/release/dsh-computer-use
```

Grant Accessibility in System Settings → Privacy & Security.

## Protocol

Same stdio JSONL as the Windows helper:

- jsonrpc 2.0: `health` / `tools` / `call` / `interrupt` / `cancel` / `shutdown`
- official: `{id,method,params,meta}`
- CLI: `--parent-pid` `--ttl-ms` `--allowed-app` `serve`

Overlay banner: **DeepSeek Harness is using your computer**.
