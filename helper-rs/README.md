# dsh-computer-use

Native Computer Use helper (`windows` crate 0.61). Speaks the same stdio JSON lines as the Python sidecar:

- Official: `{"id","method","params","meta"}` → `{"id","ok","result"|"error"}`
- jsonrpc 2.0: `health` / `tools` / `call` / `interrupt` / `shutdown` / `prompt` / `end_turn`
- `call` returns `{ok,name,value,images}` with screenshot data-URLs detached for DSH vision

Build:

```
cargo build --release
```

Binary: `target/release/dsh-computer-use.exe`

The DSH plugin prefers this exe when present, then falls back to Python.
