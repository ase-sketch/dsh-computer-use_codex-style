const PORTS = [8765, 8766, 8767];
const instanceId = crypto.randomUUID();
let base = "http://127.0.0.1:8765";

function mapTab(tab) {
  return {
    providerTabId: String(tab.id),
    id: String(tab.id),
    title: tab.title || "",
    url: tab.url || "",
    windowId: tab.windowId,
    active: !!tab.active,
    lastOpened: tab.lastAccessed || Date.now(),
    backend: "extension",
    favIconUrl: tab.favIconUrl || "",
  };
}

async function findServer() {
  for (const port of PORTS) {
    try {
      const url = `http://127.0.0.1:${port}/health`;
      const res = await fetch(url);
      if (res.ok) {
        base = `http://127.0.0.1:${port}`;
        return true;
      }
    } catch (e) {}
  }
  return false;
}

async function handle(cmd) {
  const tabId = Number(cmd.tabId);
  if (cmd.op === "claim") {
    await chrome.debugger.attach({ tabId }, "1.3");
    return { claimed: true, tabId, loginState: true, type: "extension" };
  }
  if (cmd.op === "detach") {
    try { await chrome.debugger.detach({ tabId }); } catch (e) {}
    return { ok: true };
  }
  if (cmd.op === "cdp") {
    const result = await chrome.debugger.sendCommand({ tabId }, cmd.method, cmd.params || {});
    return { result };
  }
  if (cmd.op === "capture") {
    const dataUrl = await chrome.tabs.captureVisibleTab(cmd.windowId, { format: "png" });
    return { dataUrl };
  }
  if (cmd.op === "context") {
    const injected = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const text = (document.body && document.body.innerText) || "";
        return {
          kind: "text",
          title: document.title,
          url: location.href,
          text: text.slice(0, 8000),
          truncated: text.length > 8000,
          claimed: false,
        };
      },
    });
    return injected[0]?.result || { unavailable: true, claimed: false };
  }
  if (cmd.op === "fetch") {
    const injected = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: async (targetUrl) => {
        const res = await fetch(targetUrl, { credentials: "include" });
        const buf = await res.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let bin = "";
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return { ok: res.ok, status: res.status, contentType: res.headers.get("content-type"), b64: btoa(bin) };
      },
      args: [cmd.url],
    });
    return injected[0]?.result || { error: "fetch failed" };
  }
  if (cmd.op === "history") {
    const query = { text: cmd.query || "", maxResults: cmd.limit || 20 };
    if (cmd.from) query.startTime = Date.parse(cmd.from);
    if (cmd.to) query.endTime = Date.parse(cmd.to);
    const items = await chrome.history.search(query);
    return { entries: items.map((h) => ({ url: h.url, title: h.title, dateVisited: new Date(h.lastVisitTime).toISOString() })) };
  }
  return { error: "unknown op" };
}

async function tick() {
  const ok = await findServer();
  if (!ok) return;
  const tabs = (await chrome.tabs.query({})).map(mapTab);
  await fetch(`${base}/ingest`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      type: "hello",
      instanceId,
      family: "chrome",
      tabs,
    }),
  });
  const pending = await fetch(`${base}/pending`).then((r) => r.json());
  for (const cmd of pending.commands || []) {
    let payload = {};
    try {
      payload = await handle(cmd);
    } catch (err) {
      payload = { error: String(err) };
    }
    await fetch(`${base}/ingest`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "result", id: cmd.id, result: payload }),
    });
  }
}

setInterval(tick, 800);
tick();

try {
  const native = chrome.runtime.connectNative("com.computeruse.tabbridge");
  native.onMessage.addListener((msg) => {
    const cmds = (msg && msg.commands) || [];
    cmds.forEach(async (cmd) => {
      let payload = {};
      try { payload = await handle(cmd); } catch (err) { payload = { error: String(err) }; }
      native.postMessage({ type: "result", id: cmd.id, result: payload });
    });
  });
  chrome.tabs.query({}).then((tabs) => {
    native.postMessage({ type: "hello", instanceId, family: "chrome", tabs: tabs.map(mapTab) });
  });
} catch (e) {}
