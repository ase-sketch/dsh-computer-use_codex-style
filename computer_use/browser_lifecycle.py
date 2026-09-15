"""Official tab lifecycle bookkeeping (BR-11).

`create_tab` calls `tabLifecycle.recordCreated(id)`, `get_tab` calls
`recordAcquired(id)`, and the extension dispatcher re-claims a tab when
`tabLifecycle.needsReclaim(id)` before any non-claim command
(browser-service.mjs ~1145842). Agent-created tabs close when the turn ends
unless they were marked (`docs/tab-cleanup-chrome.md:1`); claimed user tabs that
were never marked are released from browser-session control and left open
(`docs/tab-cleanup-chrome.md:7`).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TabLifecycle:
    created: set[str] = field(default_factory=set)
    acquired: set[str] = field(default_factory=set)
    marked: set[str] = field(default_factory=set)
    #: BR-21: the official pendingEvents queue. recordCreated pushes
    #: {type:"tab_created",tabId,origin:"agent"} and recordAcquired (default
    #: origin "external") pushes {type:"tab_acquired",tabId,origin}; the
    #: browser-notification contributor drains them with take_events().
    pending_events: list[dict[str, str]] = field(default_factory=list)

    def record_created(self, tab_id: str) -> None:
        if tab_id:
            key = str(tab_id)
            self.created.add(key)
            self.pending_events.append(
                {"type": "tab_created", "tabId": key, "origin": "agent"}
            )

    def record_acquired(self, tab_id: str, origin: str = "external") -> None:
        if not tab_id:
            return
        key = str(tab_id)
        if key not in self.acquired:
            self.pending_events.append(
                {"type": "tab_acquired", "tabId": key, "origin": str(origin or "external")}
            )
        self.acquired.add(key)

    def take_events(self) -> list[dict[str, str]]:
        """Official takeEvents(): pendingEvents.splice(0)."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events

    def record_marked(self, tab_id: str) -> None:
        if tab_id:
            self.marked.add(str(tab_id))

    def needs_reclaim(self, tab_id: str) -> bool:
        key = str(tab_id or "")
        if not key:
            return False
        # Official: a tab we do not currently hold must be (re)claimed before a
        # non-claim command can touch it.
        return key not in self.acquired

    def unmarked_created(self) -> list[str]:
        return sorted(self.created - self.marked)

    def released_acquired(self) -> list[str]:
        return sorted(self.acquired - self.marked)

    def end_turn(self) -> dict[str, list[str]]:
        """Agent-created unmarked tabs close; claimed unmarked tabs only lose the
        internal handle and stay open. Marks are cleared for the next turn."""
        closed = self.unmarked_created()
        released = self.released_acquired()
        self.created.clear()
        self.acquired.clear()
        self.marked.clear()
        return {"closed": closed, "released": released}


__all__ = ["TabLifecycle"]
