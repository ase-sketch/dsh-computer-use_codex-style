"""Playwright-shaped locators. Uses playwright.connect_over_cdp when possible."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PwLocator:
    id: str
    tab_id: str
    kind: str
    query: str
    exact: bool = False
    name: str | None = None
    frame: str | None = None
    nth: int | None = None
    chain: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LocatorStore:
    locators: dict[str, PwLocator] = field(default_factory=dict)
    n: int = 0
    page: Any = None
    playwright: Any = None
    downloads: list[dict[str, Any]] = field(default_factory=list)

    def put(self, tab_id: str, kind: str, query: str, **extra: Any) -> PwLocator:
        self.n += 1
        allowed = {key: extra[key] for key in extra if key in {"exact", "name", "frame", "nth", "hasText", "chain"}}
        loc = PwLocator(id=f"loc-{self.n}", tab_id=tab_id, kind=kind, query=query, **allowed)
        if not loc.chain:
            loc.chain = [{"kind": kind, "query": query, "name": loc.name, "exact": loc.exact}]
        self.locators[loc.id] = loc
        return loc

    def extend(self, parent: PwLocator, kind: str, query: str, **extra: Any) -> PwLocator:
        step = {"kind": kind, "query": query, "name": extra.get("name"), "exact": extra.get("exact") is True}
        chain = list(parent.chain) + [step]
        return self.put(parent.tab_id, kind, query, frame=parent.frame, nth=parent.nth, chain=chain, **extra)

    def get(self, locator_id: str) -> PwLocator:
        if locator_id not in self.locators:
            raise KeyError(f"unknown locator {locator_id}")
        return self.locators[locator_id]

    def attach_cdp(self, port: int) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False
        try:
            self.playwright = sync_playwright().start()
            browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            pages = [page for ctx in browser.contexts for page in ctx.pages]
            live = [page for page in pages if page.url and "about:blank" not in page.url]
            if live:
                self.page = live[-1]
            elif pages:
                self.page = pages[-1]
            elif browser.contexts:
                self.page = browser.contexts[0].new_page()
            else:
                self.page = browser.new_context().new_page()
            self.page.on("download", self._on_download)
            return True
        except Exception:
            self.close()
            return False

    def _on_download(self, download: Any) -> None:
        import tempfile
        from pathlib import Path

        record: dict[str, Any] = {
            "handle": download,
            "url": getattr(download, "url", ""),
            "suggestedFilename": getattr(download, "suggested_filename", "") or "download.bin",
            "cancelled": False,
            "failure": None,
            "path": None,
        }
        try:
            saved = download.path()
            if saved:
                record["path"] = str(saved)
        except Exception:
            dest = Path(tempfile.gettempdir()) / str(record["suggestedFilename"])
            try:
                download.save_as(str(dest))
                record["path"] = str(dest)
            except Exception as exc:
                record["failure"] = str(exc)
        self.downloads.append(record)

    def last_download(self) -> dict[str, Any] | None:
        return self.downloads[-1] if self.downloads else None

    def cancel_last(self) -> dict[str, Any]:
        last = self.last_download()
        if last is None:
            return {"cancelled": False, "error": "no download"}
        handle = last.get("handle")
        if handle is not None:
            try:
                handle.cancel()
            except Exception as exc:
                last["failure"] = str(exc)
        last["cancelled"] = True
        last["failure"] = last.get("failure") or "cancelled"
        return {"cancelled": True, "suggestedFilename": last.get("suggestedFilename"), "url": last.get("url")}

    def resolve(self, loc: PwLocator) -> Any:
        if self.page is None:
            return None
        handle: Any = self.page.frame_locator(loc.frame) if loc.frame else self.page
        steps = loc.chain or [{"kind": loc.kind, "query": loc.query, "name": loc.name, "exact": loc.exact}]
        for step in steps:
            handle = self._step(handle, step)
        if loc.nth == 0:
            return handle.first
        if loc.nth == -1:
            return handle.last
        if loc.nth is not None:
            return handle.nth(loc.nth)
        return handle

    def _step(self, root: Any, step: dict[str, Any]) -> Any:
        kind = str(step.get("kind") or "css")
        query = str(step.get("query") or "")
        exact = step.get("exact") is True
        name = step.get("name")
        if kind == "css":
            return root.locator(query)
        if kind == "role":
            kwargs: dict[str, Any] = {}
            if name:
                kwargs["name"] = name
            if exact:
                kwargs["exact"] = True
            return root.get_by_role(query, **kwargs)
        if kind == "text":
            return root.get_by_text(query, exact=exact)
        if kind == "label":
            return root.get_by_label(query, exact=exact)
        if kind == "placeholder":
            return root.get_by_placeholder(query, exact=exact)
        if kind == "testid":
            return root.get_by_test_id(query)
        return root.locator(query)

    def close(self) -> None:
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.playwright = None
        self.page = None
