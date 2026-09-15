"""Parse official plugin:// tab mentions (IAB vs Chrome extension)."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse


def parse_tab_mention(link: str) -> dict[str, str | None]:
    parsed = urlparse(link)
    query = {key: values[0] if values else None for key, values in parse_qs(parsed.query).items()}
    host = (parsed.netloc or "").lower()
    source = query.get("source")
    family = "extension" if source == "extension" or "chrome" in host else "iab"
    return {
        "family": family,
        "browser_id": query.get("browserId"),
        "tab_id": query.get("tabId") or query.get("providerTabId"),
        "title": unquote(query.get("title") or ""),
        "url": unquote(query.get("url") or ""),
        "source": source,
    }


def same_tab(info: dict[str, object], mention: dict[str, str | None]) -> bool:
    return (
        str(info.get("providerTabId") or info.get("id") or "") == str(mention.get("tab_id") or "")
        and str(info.get("title") or "") == str(mention.get("title") or "")
        and str(info.get("url") or "") == str(mention.get("url") or "")
    )
