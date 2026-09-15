# Computer Use Tab Bridge (Chrome/Edge)

Load unpacked from `chrome://extensions` → Developer mode → Load unpacked → this folder.

Python side:

```python
from computer_use.extension_hub import ExtensionHub
hub = ExtensionHub()
hub.start(8765)
# extension polls /pending and posts tabs to /ingest
tabs = hub.tabs  # real profile tabs, cookies intact
hub.claim(tab_id, title, url)  # chrome.debugger.attach
```

This is the login-state path: the extension runs inside your existing Chrome/Edge profile, then attaches the debugger to a tab you already opened.

Native messaging: `com.computeruse.tabbridge` (`computer_use/native_host.py`). HTTP poll on 8765 still works; set `COMPUTER_USE_EXTENSION=1` to auto-start the hub.
