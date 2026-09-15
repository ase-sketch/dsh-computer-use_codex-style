from __future__ import annotations

import unittest

from computer_use.browser_url_policy import (
    UNSUPPORTED_FAMILIES,
    URL_FAMILY_UNSUPPORTED,
    URL_NOT_ALLOWED,
    URL_UNDETERMINED,
    URL_UNVERIFIED,
    BrowserUrlPolicyError,
    UrlPolicy,
    assert_browser_url_allowed,
)


class BrowserUrlPolicyTests(unittest.TestCase):
    """BR-14: the official fail-closed URL gate, sentence by sentence."""

    def test_denied_host_uses_the_first_sentence(self) -> None:
        policy = UrlPolicy(deny_hosts=("evil.test",))
        with self.assertRaises(BrowserUrlPolicyError) as raised:
            assert_browser_url_allowed("https://evil.test/x", policy=policy)
        self.assertEqual(str(raised.exception), URL_NOT_ALLOWED)

    def test_missing_policy_source_uses_the_second_sentence(self) -> None:
        policy = UrlPolicy(available=False)
        with self.assertRaises(BrowserUrlPolicyError) as raised:
            assert_browser_url_allowed("https://ok.test/", policy=policy)
        self.assertEqual(str(raised.exception), URL_UNVERIFIED)

    def test_unresolved_url_uses_the_third_sentence(self) -> None:
        policy = UrlPolicy()
        for bad in ("", None):
            with self.assertRaises(BrowserUrlPolicyError) as raised:
                assert_browser_url_allowed(bad, policy=policy)
            self.assertEqual(str(raised.exception), URL_UNDETERMINED)

    def test_unsupported_browser_family_uses_the_fourth_sentence(self) -> None:
        policy = UrlPolicy()
        for family in sorted(UNSUPPORTED_FAMILIES):
            with self.assertRaises(BrowserUrlPolicyError) as raised:
                assert_browser_url_allowed(
                    "https://ok.test/", family=family, policy=policy
                )
            self.assertEqual(str(raised.exception), URL_FAMILY_UNSUPPORTED)

    def test_supported_host_is_allowed(self) -> None:
        policy = UrlPolicy(deny_hosts=("evil.test",))
        for url in ("https://good.test/x", "http://good.test"):
            assert_browser_url_allowed(url, family="chrome", policy=policy)

    def test_local_testing_mode_bypasses_the_gate(self) -> None:
        policy = UrlPolicy(available=False)
        assert_browser_url_allowed(
            None, security_mode="disabled-for-local-testing", policy=policy
        )

    def test_allow_list_denies_unlisted_hosts(self) -> None:
        policy = UrlPolicy(allow_hosts=("good.test",))
        assert_browser_url_allowed("https://good.test/", policy=policy)
        with self.assertRaises(BrowserUrlPolicyError):
            assert_browser_url_allowed("https://other.test/", policy=policy)


if __name__ == "__main__":
    unittest.main()
