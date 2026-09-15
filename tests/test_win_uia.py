from __future__ import annotations

import unittest

from computer_use.recovered import SECONDARY_ACTIONS
from computer_use.tree_format import format_node_line
from computer_use.models import Bounds, UINode
from computer_use.win_uia import (
    CACHE_PATTERNS,
    CACHE_PROPERTIES,
    COINIT_MULTITHREADED,
    CONTROL_TYPES,
    DUMP_CACHE_PATTERNS,
    DUMP_CACHE_PROPERTIES,
    EVENT_CACHE_PATTERNS,
    EVENT_CACHE_PROPERTIES,
    ExpandCollapseState_Collapsed,
    INTEGRITY_MESSAGE,
    PATTERN_EXPAND,
    PATTERN_INVOKE,
    PATTERN_SCROLL,
    PATTERN_TOGGLE,
    PATTERN_VALUE,
    PROCESS_MISMATCH,
    PROP_LOCALIZED_CONTROL_TYPE,
    PROP_PROCESS_ID,
    RUNTIME_ID_MISMATCH,
    TreeScope_Element,
    dump_tree,
    truncated_label,
)


class InProcessUiaTests(unittest.TestCase):
    def test_dump_tree_never_raises(self) -> None:
        nodes = dump_tree(0, "gone")
        self.assertGreaterEqual(len(nodes), 1)
        self.assertEqual(nodes[0].role, "window")

    def test_integrity_message_constant(self) -> None:
        self.assertIn("higher Windows integrity", INTEGRITY_MESSAGE)

    def test_cache_request_covers_official_patterns(self) -> None:
        self.assertIn(PATTERN_INVOKE, CACHE_PATTERNS)
        self.assertIn(PATTERN_VALUE, CACHE_PATTERNS)
        self.assertIn(PATTERN_SCROLL, CACHE_PATTERNS)
        self.assertIn(PATTERN_TOGGLE, CACHE_PATTERNS)
        self.assertIn(PATTERN_EXPAND, CACHE_PATTERNS)
        self.assertIn(30001, CACHE_PROPERTIES)
        self.assertIn(30005, CACHE_PROPERTIES)
        self.assertIn(50000, CONTROL_TYPES)

    def test_accessibility_note_and_selected_list(self) -> None:
        from computer_use.tree_format import SELECTED_NOTE, format_accessibility

        node = UINode(0, "window", "App", Bounds(0, 0, 10, 10))
        text = format_accessibility(
            [node],
            "App",
            "app.exe",
            focused='The focused UI element is [0] window "App".',
            selected_text="hello",
            selected_elements=['[1] text "hi"'],
            document_text="doc",
        )
        self.assertIn("Selected:", text)
        self.assertIn("Selected text:", text)
        self.assertIn("Document text:", text)
        self.assertIn(SELECTED_NOTE[:40], text)

    def test_tree_line_uses_the_official_field_order(self) -> None:
        # AX-19: role (states) name ... -- the three lines the official helper
        # printed for Word. The old DSH order was role name (states).
        from computer_use.tree_format import format_node_line

        cases = [
            (
                UINode(1, "窗格", "DropShadowTop", Bounds(0, 0, 1, 1), states=["disabled"]),
                "\t1 窗格 (disabled) DropShadowTop",
            ),
            (
                UINode(
                    11, "SplitButton", "无法撤消", Bounds(0, 0, 1, 1),
                    states=["disabled"], automation_id="Undo",
                ),
                "\t11 SplitButton (disabled) 无法撤消 ID: Undo",
            ),
            (
                UINode(
                    30, "选项卡项目", "开始", Bounds(0, 0, 1, 1),
                    states=["selectable"], automation_id="TabHome",
                ),
                "\t30 选项卡项目 (selectable) 开始 ID: TabHome",
            ),
        ]
        for node, expected in cases:
            self.assertEqual(format_node_line(node), expected)
        # The pre-AX-17 order must NOT come back.
        self.assertNotEqual(format_node_line(cases[0][0]), "\t1 窗格 DropShadowTop (disabled)")
        self.assertNotEqual(format_node_line(cases[1][0]), "\t11 SplitButton 无法撤消 (disabled) ID: Undo")

    def test_tree_line_collapses_name_whitespace_and_keeps_role_verbatim(self) -> None:
        from computer_use.tree_format import collapse_whitespace, format_node_line

        self.assertEqual(collapse_whitespace("a  b\tc"), "a b c")
        # AX-21: the localized control type survives with its trailing space.
        trailing = UINode(1, "切换关闭 ", "自动保存", Bounds(0, 0, 1, 1), states=["disabled"])
        self.assertEqual(format_node_line(trailing), "\t1 切换关闭  (disabled) 自动保存")
        # AX-22: the name is whitespace-normalised.
        spaced = UINode(2, "Text", "a  b\tc", Bounds(0, 0, 1, 1))
        self.assertEqual(format_node_line(spaced), "\t2 Text a b c")

    def test_focused_sentence_and_document_text_are_mutually_exclusive(self) -> None:
        from computer_use.tree_format import format_accessibility, format_tree

        node = UINode(0, "窗口", "App", Bounds(0, 0, 1, 1))
        both = format_accessibility(
            [node], "App", "word.exe", focused="0 窗口 App", document_text="doc\r\nbody"
        )
        self.assertIn("Document text:", both)
        self.assertNotIn("The focused UI element is", both)
        self.assertIn("\n\nDocument text:", both)
        self.assertNotIn("\r", both)
        only_focus = format_accessibility([node], "App", "app.exe", focused="0 窗口 App")
        self.assertIn("The focused UI element is", only_focus)
        self.assertIn("\n\nThe focused UI element is", only_focus)
        # AX-22: the header title is collapsed too.
        self.assertTrue(format_tree([node], "a  b", "app.exe").startswith('Window: "a b", App: app.exe.'))

    def test_tree_line_uses_official_secondary_action_labels(self) -> None:
        node = UINode(
            2,
            "Button",
            "OK",
            Bounds(1, 2, 3, 4),
            value="1",
            actions=["Raise", "Expand"],
            automation_id="okButton",
        )
        line = format_node_line(node)
        self.assertIn("Secondary Actions: Raise, Expand", line)
        self.assertIn("Value: 1", line)
        self.assertIn("ID: okButton", line)
        for name in SECONDARY_ACTIONS:
            self.assertTrue(name)

    def test_logical_bounds_are_window_relative(self) -> None:
        nodes = dump_tree(0, "gone", origin=(100.0, 200.0), scale=1.5)
        self.assertEqual(nodes[0].role, "window")
        self.assertLessEqual(nodes[0].bounds.x, 0.0)

    def test_value_pattern_slots(self) -> None:
        import inspect

        from computer_use import win_uia

        src = inspect.getsource(win_uia._value_of)
        self.assertIn("get_CurrentValue", src)

    def test_official_lowercase_roles_and_truncation(self) -> None:
        self.assertEqual(CONTROL_TYPES[50000], "button")
        self.assertEqual(CONTROL_TYPES[50004], "text field")
        self.assertEqual(CONTROL_TYPES[50024], "tree item")
        self.assertEqual(CONTROL_TYPES[50025], "custom")
        line = truncated_label("list", "Inbox", 12)
        self.assertIn("(truncated: list \"Inbox\"", line)
        self.assertIn("omitted 12 children)", line)

    def test_official_dump_versus_event_cache(self) -> None:
        self.assertEqual(COINIT_MULTITHREADED, 0)
        self.assertEqual(TreeScope_Element, 1)
        self.assertIn(PROP_PROCESS_ID, DUMP_CACHE_PROPERTIES)
        self.assertIn(PROP_LOCALIZED_CONTROL_TYPE, DUMP_CACHE_PROPERTIES)
        self.assertEqual(EVENT_CACHE_PROPERTIES, (30003, 30005, 30020, 30002))
        self.assertEqual(EVENT_CACHE_PATTERNS, ())
        self.assertIn(PATTERN_VALUE, DUMP_CACHE_PATTERNS)
        self.assertIn(PATTERN_INVOKE, CACHE_PATTERNS)
        self.assertIn(30001, CACHE_PROPERTIES)

    def test_expand_state_and_mismatch_strings(self) -> None:
        self.assertEqual(ExpandCollapseState_Collapsed, 0)
        self.assertEqual(RUNTIME_ID_MISMATCH, "no longer matches the cached runtime ID")
        self.assertEqual(PROCESS_MISMATCH, "no longer belongs to the cached target process")
        self.assertEqual(f"element 3 {RUNTIME_ID_MISMATCH}", "element 3 no longer matches the cached runtime ID")


if __name__ == "__main__":
    unittest.main()
