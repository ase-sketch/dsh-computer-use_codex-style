"""Official tab.dom_cua helpers: visible DOM snapshot + node_id actions."""

VISIBLE_DOM_JS = """(() => {
  const sel = 'a,button,input,textarea,select,summary,[role="button"],[role="link"],[role="textbox"]';
  return [...document.querySelectorAll(sel)].map((el) => {
    const r = el.getBoundingClientRect();
    return {el, r};
  }).filter((item) => item.r.width > 0 && item.r.height > 0).slice(0, 120).map((item, i) => ({
    node_id: i + 1,
    tag: item.el.tagName.toLowerCase(),
    role: item.el.getAttribute('role') || item.el.tagName.toLowerCase(),
    name: (item.el.innerText || item.el.getAttribute('aria-label') || item.el.getAttribute('placeholder') || item.el.name || '').trim().slice(0, 80),
    selector: item.el.id ? ('#' + item.el.id) : item.el.tagName.toLowerCase(),
    x: Math.round(item.r.left + item.r.width / 2),
    y: Math.round(item.r.top + item.r.height / 2)
  }));
})()"""


def click_js(selector: str, count: int = 1) -> str:
    n = max(int(count), 1)
    return f"""(() => {{
      const el = document.querySelector({selector!r});
      if (!el) return false;
      el.focus();
      for (let i = 0; i < {n}; i++) el.click();
      return true;
    }})()"""


def type_js(text: str) -> str:
    return f"""(() => {{
      const el = document.activeElement;
      if (!el) return false;
      el.focus();
      if ('value' in el) {{
        el.value = (el.value || '') + {text!r};
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
      }}
      return true;
    }})()"""


def scroll_js(x: float, y: float, node_id: int | None) -> str:
    if node_id is None:
        return f"window.scrollBy({int(x)}, {int(y)});"
    return f"""(() => {{
      const nodes = {VISIBLE_DOM_JS};
      const hit = nodes.find((n) => n.node_id === {int(node_id)});
      if (!hit) {{ window.scrollBy({int(x)}, {int(y)}); return; }}
      const el = document.querySelector(hit.selector);
      if (el) el.scrollBy({int(x)}, {int(y)});
    }})()"""
