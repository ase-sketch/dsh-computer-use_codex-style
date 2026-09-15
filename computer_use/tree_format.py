from __future__ import annotations

import re

from computer_use.models import Bounds, UINode
from computer_use.recovered import (
    DOCUMENT_PREFIX,
    FOCUSED_PREFIX,
    SELECTED_PREFIX,
    TREE_WINDOW_PREFIX,
)

SELECTED_LIST_PREFIX = "Selected:"
SELECTED_NOTE = (
    "Note: Pay special attention to the content selected by the user. If the user asks a question "
    "or refers to the content they are looking at on-screen, they might be referring to the selected "
    "content (but they might be referring to something else that's visible, too)."
)
_PRE_STATES = {
    "selectable",
    "selected",
    "disabled",
    "collapsed",
    "expanded",
    "partially expanded",
    "settable",
    "settable, string",
    "settable, float",
}
_TOGGLE_STATES = {"off", "on", "indeterminate"}


def collapse_whitespace(text: str) -> str:
    """AX-22: mirror of helper-rs/src/uia.rs:1837.

    Word's raw UIA name is full of double spaces while the official tree prints
    single ones, so every printed name/title is whitespace-normalised.
    """
    return " ".join(str(text).split())


def normalize_newlines(text: str) -> str:
    """AX-5: mirror of helper-rs/src/uia.rs:2221 (CRLF/CR -> LF)."""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def format_node_line(node: UINode) -> str:
    """Official window2 grammar, byte-for-byte with helper-rs/src/uia.rs:2453.

    AX-19: the primary state list sits between the role and the name --
    "1 Pane (disabled) DropShadowTop", not "1 Pane DropShadowTop (disabled)".
    Then, in this exact order: Description / Value / toggle / other /
    Secondary Actions / ID. The name is whitespace-collapsed (AX-22), unquoted
    and omitted entirely when empty; the role is printed verbatim (AX-21:
    "SplitButton", and even a trailing space survives); one TAB per depth with
    the root indented one tab too; no bounding box (the official prints none).
    """
    indent = "\t" * (node.depth + 1)
    pre = [state for state in node.states if state in _PRE_STATES]
    toggle = [state for state in node.states if state in _TOGGLE_STATES]
    other = [state for state in node.states if state not in _PRE_STATES and state not in _TOGGLE_STATES]
    # AX-19 / AX-21: role verbatim, then the parenthesised state block, then name.
    state_block = (" (" + ", ".join(pre) + ")") if pre else ""
    extras: list[str] = []
    if node.description:
        extras.append(f"Description: {node.description}")
    if node.value:
        extras.append(f"Value: {node.value}")
    if toggle:
        extras.append(", ".join(toggle))
    if other:
        extras.append(", ".join(other))
    if node.actions:
        extras.append("Secondary Actions: " + ", ".join(node.actions))
    if node.automation_id:
        extras.append(f"ID: {node.automation_id}")
    suffix = (" " + " ".join(extras)) if extras else ""
    collapsed = collapse_whitespace(node.name)
    name = f" {collapsed}" if collapsed else ""
    return f"{indent}{node.index} {node.role}{state_block}{name}{suffix}"


def format_tree(nodes: list[UINode], window_title: str, app: str) -> str:
    # AX-22: the header title is whitespace-normalised too (the official Word
    # tree header prints single spaces while the raw Win32 title keeps doubles).
    header = f'{TREE_WINDOW_PREFIX}{collapse_whitespace(window_title)}", App: {app}.'
    body = [format_node_line(node) for node in nodes]
    return "\n".join([header, *body])


def focused_line(node: UINode | None) -> str:
    """The bare formatted line for the focused element (official api.md:
    "Formatted line for the focused element"). The sentence is added once, at
    the end of the tree, by format_accessibility."""
    if node is None:
        return ""
    return format_node_line(node).lstrip("\t")


def selected_block(text: str) -> str:
    if not text:
        return ""
    return f"{SELECTED_PREFIX} ```\n{text}\n```"


def document_block(text: str) -> str:
    if not text:
        return ""
    return f"{DOCUMENT_PREFIX} ```\n{text}\n```"


def format_accessibility(
    nodes: list[UINode],
    window_title: str,
    app: str,
    *,
    focused: str = "",
    selected_text: str = "",
    selected_elements: list[str] | None = None,
    document_text: str = "",
) -> str:
    selected_body = normalize_newlines(selected_text)
    document_body = normalize_newlines(document_text)
    # AX-26: the official never prints both. Word reports a focused_element but
    # prints only the Document text block; ParityTarget/Explorer print the
    # sentence and have no document text.
    show_focused = bool(focused) and not document_body
    has_tail = show_focused or bool(selected_elements) or bool(selected_body) or bool(document_body)
    parts = [format_tree(nodes, window_title, app)]
    if has_tail:
        # AX-06: every section literal carries its own leading newline, so the
        # tree body is always followed by exactly one blank line. The blank line
        # must not depend on the focused branch (suppressing the sentence used to
        # drop the separator).
        parts.append("")
    if show_focused:
        # Official: the field is the bare line; the tree carries the sentence.
        text = focused if focused.startswith(FOCUSED_PREFIX) else f"{FOCUSED_PREFIX} {focused}."
        parts.append(text)
    if selected_elements:
        parts.append(SELECTED_LIST_PREFIX)
        parts.extend(selected_elements)
    selected = selected_block(selected_body)
    if selected:
        parts.append(selected)
    document = document_block(document_body)
    if document:
        parts.append(document)
    if selected_body or selected_elements:
        parts.append(SELECTED_NOTE)
    return "\n".join(parts)


#: Legacy DSH grammar (`[i] role "name" {{x: ..}}`). KEPT ON PURPOSE: both the
#: helper protocol fixtures (tests/test_helper_protocol.py) and the AX-04 old
#: fixtures still feed it, and dropping it would turn a legacy-shaped capture
#: into a silent empty tree. The official grammar below is what we now emit.
_LEGACY_NODE_RE = re.compile(
    r'^(\s*)\[(\d+)\]\s+(.+?)\s+"([^"]*)"(?:\s+\{\{x:\s*([-\d.]+),\s*y:\s*([-\d.]+),\s*width:\s*([-\d.]+),\s*height:\s*([-\d.]+)\}\})?'
)
#: Official window2 grammar: TAB indent, bare index, role, then the parenthesised
#: state block, the name, and finally Description: / Value: / toggle / other /
#: Secondary Actions: / ID: (AX-19 order, helper-rs/src/uia.rs:2453).
_OFFICIAL_NODE_RE = re.compile(r"^(\t*)(\d+) (\S+)(?: (.*))?$")
_EXTRA_MARKERS = ("Description: ", "Value: ", "Secondary Actions: ", "ID: ")
_TOGGLE_TAIL_RE = re.compile(r"(?:^| )(off|on|indeterminate)$")


def _split_official_rest(rest: str) -> tuple[str, tuple[str, ...]]:
    """Split the post-AX-19 tail: `(states) name Description: .. Value: ..`.

    The state block now leads (it sits between the role and the name), so it is
    consumed first; the name is whatever precedes the first trailing field.
    """
    states: list[str] = []
    text = rest
    if text.startswith("(") and ")" in text:
        close = text.index(")")
        states = [part for part in text[1:close].split(", ") if part]
        text = text[close + 1:].lstrip(" ")
    cut = len(text)
    for marker in _EXTRA_MARKERS:
        position = text.find(marker)
        if position != -1 and position < cut:
            cut = position
    toggle = _TOGGLE_TAIL_RE.search(text)
    if toggle and toggle.start() < cut:
        cut = toggle.start()
    return text[:cut].strip(), tuple(states)


def parse_tree_nodes(tree_text: str) -> list[UINode]:
    nodes: list[UINode] = []
    for line in tree_text.splitlines():
        legacy = _LEGACY_NODE_RE.match(line)
        if legacy:
            indent, index, role, name, x, y, w, h = legacy.groups()
            bounds = Bounds(float(x or 0), float(y or 0), float(w or 0), float(h or 0))
            nodes.append(UINode(int(index), role, name, bounds, depth=len(indent) // 2))
            continue
        official = _OFFICIAL_NODE_RE.match(line)
        if not official:
            continue
        indent, index, role, rest = official.groups()
        name, states = _split_official_rest(rest or "")
        nodes.append(
            UINode(
                int(index),
                role,
                name,
                Bounds(0.0, 0.0, 0.0, 0.0),
                depth=len(indent),
                states=list(states),
            )
        )
    return nodes
