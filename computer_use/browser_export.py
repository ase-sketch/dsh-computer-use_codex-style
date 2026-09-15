"""Login-state GSuite/YouTube export, pageAssets inventory, WebMCP probe (page JS)."""

from __future__ import annotations

import re

GSUITE_FORMATS = {"pdf", "md", "xlsx", "csv", "docx", "pptx"}


def gsuite_export_url(page_url: str, fmt: str) -> str | None:
    kind = fmt.lower()
    if kind not in GSUITE_FORMATS:
        kind = "pdf"
    doc = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", page_url)
    if doc:
        mapped = {"md": "txt", "docx": "docx", "pdf": "pdf"}.get(kind, "pdf")
        return f"https://docs.google.com/document/d/{doc.group(1)}/export?format={mapped}"
    sheet = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", page_url)
    if sheet:
        mapped = {"csv": "csv", "xlsx": "xlsx", "pdf": "pdf"}.get(kind, "xlsx")
        return f"https://docs.google.com/spreadsheets/d/{sheet.group(1)}/export?format={mapped}"
    slide = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", page_url)
    if slide:
        mapped = {"pptx": "pptx", "pdf": "pdf"}.get(kind, "pdf")
        return f"https://docs.google.com/presentation/d/{slide.group(1)}/export/{mapped}"
    return None


FETCH_AS_B64_JS = """async (url) => {
  const res = await fetch(url, { credentials: 'include' });
  const buf = await res.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return { ok: res.ok, status: res.status, contentType: res.headers.get('content-type'), b64: btoa(bin) };
}"""

YOUTUBE_TRANSCRIPT_JS = """() => {
  const nodes = [...document.querySelectorAll('ytd-transcript-segment-renderer, .ytd-transcript-segment-renderer, [class*="transcript"]')];
  const lines = nodes.map((n) => (n.innerText || '').trim()).filter(Boolean);
  if (lines.length) return { text: lines.join('\\n'), tracks: [] };
  const html = document.documentElement.innerHTML;
  const blob = html.match(/"captionTracks":(\\[[\\s\\S]*?\\])/);
  if (blob) {
    try {
      const tracks = JSON.parse(blob[1]);
      if (tracks.length) return { text: '', tracks: tracks.map((t) => ({ baseUrl: t.baseUrl, languageCode: t.languageCode, kind: t.kind })) };
    } catch (e) {}
  }
  const player = window.ytInitialPlayerResponse || window.ytplayer?.config?.args?.player_response;
  let parsed = player;
  if (typeof parsed === 'string') { try { parsed = JSON.parse(parsed); } catch (e) { parsed = {}; } }
  const tracks = parsed?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  return { text: '', tracks: tracks.map((t) => ({ baseUrl: t.baseUrl, languageCode: t.languageCode, kind: t.kind, name: t.name?.simpleText })) };
}"""

ASSETS_JS = """() => {
  const abs = (u) => { try { return new URL(u, location.href).href; } catch (e) { return u; } };
  const seen = new Set();
  const assets = [];
  const add = (url, kind, source) => {
    if (!url || url.startsWith('data:')) return;
    const href = abs(url);
    if (seen.has(href)) return;
    seen.add(href);
    assets.push({ id: 'a' + (assets.length + 1), kind, name: (href.split('/').pop() || kind).split('?')[0], url: href, sources: [source] });
  };
  document.querySelectorAll('img').forEach((el) => {
    add(el.currentSrc || el.src, 'image', { kind: 'attribute', property: 'src' });
    add(el.getAttribute('data-src'), 'image', { kind: 'attribute', property: 'data-src' });
    (el.getAttribute('srcset') || '').split(',').forEach((part) => add(part.trim().split(' ')[0], 'image', { kind: 'srcset' }));
  });
  document.querySelectorAll('link[rel="stylesheet"][href]').forEach((el) => add(el.href, 'stylesheet', { kind: 'attribute', property: 'href' }));
  document.querySelectorAll('script[src]').forEach((el) => add(el.src, 'script', { kind: 'attribute', property: 'src' }));
  document.querySelectorAll('video, source').forEach((el) => add(el.currentSrc || el.src, 'video', { kind: 'attribute', property: 'src' }));
  [...document.styleSheets].forEach((sheet) => {
    let rules = [];
    try { rules = [...(sheet.cssRules || [])]; } catch (e) { return; }
    rules.forEach((rule) => {
      if (rule instanceof CSSFontFaceRule) {
        const m = String(rule.cssText).match(/url\\((['\"]?)(.*?)\\1\\)/);
        if (m) add(m[2], 'font', { kind: 'font-face' });
      }
    });
  });
  const svgs = [...document.querySelectorAll('svg')].slice(0, 20).map((el, i) => ({ id: 'svg' + i, name: 'inline-' + i + '.svg', markup: el.outerHTML.slice(0, 4000) }));
  const byKind = {};
  assets.forEach((a) => { byKind[a.kind] = (byKind[a.kind] || 0) + 1; });
  return { id: 'inv-' + Date.now(), pageUrl: location.href, assets, inlineSvgs: svgs, summary: { totalCount: assets.length, inlineSvgCount: svgs.length, byKind } };
}"""

VIEWPORT_JS = """() => ({
  dpr: window.devicePixelRatio || 1,
  scale: (window.visualViewport && window.visualViewport.scale) || 1,
  offsetLeft: (window.visualViewport && window.visualViewport.offsetLeft) || 0,
  offsetTop: (window.visualViewport && window.visualViewport.offsetTop) || 0,
  width: window.innerWidth,
  height: window.innerHeight
})"""

WEBMCP_JS = """() => {
  const tools = [];
  const desc = [];
  if (navigator.modelContext) desc.push('navigator.modelContext');
  if (window.__webmcp) desc.push('window.__webmcp');
  document.querySelectorAll('script[type="application/json"][data-mcp], script[type="application/mcp+json"]').forEach((el) => {
    try { const data = JSON.parse(el.textContent || '{}'); (data.tools || []).forEach((t) => tools.push(t)); } catch (e) {}
  });
  return { tools, description: tools.length ? tools.map((t) => t.name || t).join(', ') : (desc.join(', ') || 'No page-defined WebMCP tools on this tab.') };
}"""

def is_login_wall(raw: bytes, content_type: str = "") -> bool:
    ctype = content_type.lower()
    if "json" in ctype or "pdf" in ctype or "officedocument" in ctype or "spreadsheet" in ctype:
        return False
    head = raw[:1200].lower()
    if b"<html" not in head and b"<!doctype" not in head:
        return False
    return any(token in head for token in (b"sign in", b"accounts.google", b"servicelogin", "登录".encode("utf-8")))


def parse_timedtext_xml(xml: str) -> str:
    chunks = re.findall(r"<text[^>]*>(.*?)</text>", xml, flags=re.I | re.S)
    if not chunks:
        chunks = re.findall(r"<p[^>]*>(.*?)</p>", xml, flags=re.I | re.S)
    lines = []
    for chunk in chunks:
        text = re.sub(r"<[^>]+>", "", chunk)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
        text = text.replace("\n", " ").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


BOUNDED_TEXT_JS = """() => {
  const text = (document.body && document.body.innerText) || '';
  return { title: document.title, url: location.href, text: text.slice(0, 8000), truncated: text.length > 8000, kind: 'text' };
}"""
