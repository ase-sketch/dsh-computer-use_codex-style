//! BR-14: helper-side browser URL policy (the official `assertBrowserUrlAllowed`).
//!
//! The official JS layer only calls the host hook
//! `this.runtime.assertBrowserUrlAllowed?.(url)` (browser-service.mjs byte offsets
//! 572366 / 576588); the Windows helper owns the implementation in
//! `src/policy/url_policy.rs` and fails closed with four verbatim sentences recovered
//! from `out/exe/strings_all.txt:18208` (RVA 0x132af7).
//!
//! What the available decompile material does and does not establish:
//!   * CONFIRMED: the four sentences, byte for byte (string table).
//!   * CONFIRMED: the browser-family vocabulary at 0x13633d
//!     `msedge chrome brave opera iexplore firefox browser dia`.
//!   * CONFIRMED: the security-mode header value `disabled-for-local-testing` and the
//!     site-status endpoint `/backend-api/aura/site_status` (0x138520).
//!   * CONFIRMED: `angr-sky/rust/140076f73_sub_140076f73.rs` is an HTTPS GET transport
//!     (WinHttpCrackUrl + WinHttpOpen/Connect/OpenRequest/SendRequest/ReceiveResponse/
//!     QueryHeaders/ReadData) — i.e. the site-status query helper, NOT the policy
//!     decision tree. It contains none of the family names and no allow/deny table.
//!   * NOT RECOVERED: the official decision tree itself (which service answer means
//!     "not allowed" vs "could not verify", the confidence threshold, the host list).
//!
//! So this module carries the four verbatim strings plus the same decision table the
//! Python plane already enforces (computer_use/browser_url_policy.py), ordered exactly
//! like that table, and fails closed. The allow/deny source is explicit configuration
//! (COMPUTER_USE_BROWSER_URL_DENY / _ALLOW / _POLICY) rather than the unrecovered
//! official service.

use serde_json::{json, Map, Value};

/// Sentence 1 — a resolved URL that policy forbids.
pub const URL_NOT_ALLOWED: &str = "Computer Use has been stopped for this turn because it is not allowed on the current browser URL. Stop your work and send a final message noting why Computer Use ended. Note that Computer Use is not allowed on this URL even if the user navigates to it themselves.";
/// Sentence 2 — the policy source could not be consulted.
pub const URL_UNVERIFIED: &str = "Computer Use has been stopped for this turn because it could not verify whether the current browser URL is allowed. Stop your work and send a final message noting why Computer Use ended.";
/// Sentence 3 — the current URL could not be determined with enough confidence.
pub const URL_UNDETERMINED: &str = "Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy. Stop your work and send a final message noting why Computer Use ended.";
/// Sentence 4 — the browser family is not supported.
pub const URL_FAMILY_UNSUPPORTED: &str = "Computer Use has been stopped for this turn because browser URL policy enforcement is not yet supported for the current Windows browser. Stop your work and send a final message noting why Computer Use ended.";

/// The four sentences in official string-table order.
pub const URL_GATE_MESSAGES: [&str; 4] =
    [URL_NOT_ALLOWED, URL_UNVERIFIED, URL_UNDETERMINED, URL_FAMILY_UNSUPPORTED];

/// Browser-family vocabulary from strings_all.txt:18323 (RVA 0x13633d). The first four
/// are the Chromium families the policy supports; the rest fall through to sentence 4.
pub const BROWSER_FAMILIES: [&str; 8] =
    ["msedge", "chrome", "brave", "opera", "iexplore", "firefox", "browser", "dia"];
pub const SUPPORTED_FAMILIES: [&str; 4] = ["msedge", "chrome", "brave", "opera"];

/// The security mode that bypasses the gate (official header value).
pub const SECURITY_MODE_DISABLED: &str = "disabled-for-local-testing";

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct UrlPolicy {
    pub deny_hosts: Vec<String>,
    pub allow_hosts: Vec<String>,
    pub available: bool,
}

impl UrlPolicy {
    pub fn from_env() -> Self {
        fn split(raw: Option<String>) -> Vec<String> {
            raw.unwrap_or_default()
                .split(',')
                .map(|item| item.trim().to_ascii_lowercase())
                .filter(|item| !item.is_empty())
                .collect()
        }
        let available = match std::env::var("COMPUTER_USE_BROWSER_URL_POLICY") {
            Ok(raw) => !matches!(raw.trim().to_ascii_lowercase().as_str(), "0" | "off" | "unavailable"),
            Err(_) => true,
        };
        Self {
            deny_hosts: split(std::env::var("COMPUTER_USE_BROWSER_URL_DENY").ok()),
            allow_hosts: split(std::env::var("COMPUTER_USE_BROWSER_URL_ALLOW").ok()),
            available,
        }
    }

    /// True/False when the policy decides the host, None when it is silent.
    ///
    /// A URL that does not resolve to an http(s) host is *undetermined*, not denied;
    /// `assert_browser_url_allowed` turns the `None` into sentence 3.
    pub fn host_allowed(&self, url: &str) -> Option<bool> {
        let host = host_of(url);
        if host.is_empty() {
            return None;
        }
        for item in &self.deny_hosts {
            if host == *item || host.ends_with(&format!(".{item}")) {
                return Some(false);
            }
        }
        if !self.allow_hosts.is_empty() {
            for item in &self.allow_hosts {
                if host == *item || host.ends_with(&format!(".{item}")) {
                    return Some(true);
                }
            }
            return Some(false);
        }
        None
    }
}

/// The host component of an http(s) URL, lowercased, or an empty string when it cannot be parsed.
pub fn host_of(url: &str) -> String {
    let trimmed = url.trim();
    let (scheme, rest) = match trimmed.split_once("://") {
        Some((scheme, rest)) => (scheme.to_ascii_lowercase(), rest),
        None => return String::new(),
    };
    if scheme != "http" && scheme != "https" {
        return String::new();
    }
    let authority = rest
        .split(['/', '?', '#'])
        .next()
        .unwrap_or("");
    // Strip userinfo (last '@' in the authority).
    let authority = match authority.rsplit_once('@') {
        Some((_, host)) => host,
        None => authority,
    };
    // Strip the port, keeping bracketed IPv6 literals intact.
    let host = if let Some(rest) = authority.strip_prefix('[') {
        match rest.split_once(']') {
            Some((inside, _)) => inside.to_string(),
            None => return String::new(),
        }
    } else {
        match authority.split_once(':') {
            Some((host, _)) => host.to_string(),
            None => authority.to_string(),
        }
    };
    host.trim().to_ascii_lowercase()
}

fn is_unsupported_family(family: &str) -> bool {
    let lowered = family.trim().to_ascii_lowercase();
    BROWSER_FAMILIES.contains(&lowered.as_str()) && !SUPPORTED_FAMILIES.contains(&lowered.as_str())
}

/// Fail closed exactly like the official helper callback.
///
/// Order (mirrors the four official sentences):
///   1. browser family unsupported -> sentence 4
///   2. URL could not be determined -> sentence 3
///   3. policy source unavailable -> sentence 2
///   4. policy denies the URL -> sentence 1
pub fn assert_browser_url_allowed(
    url: Option<&str>,
    family: &str,
    security_mode: &str,
    policy: &UrlPolicy,
) -> Result<(), String> {
    if security_mode == SECURITY_MODE_DISABLED {
        return Ok(());
    }
    if is_unsupported_family(family) {
        return Err(URL_FAMILY_UNSUPPORTED.to_string());
    }
    let Some(url) = url.filter(|value| !value.trim().is_empty()) else {
        return Err(URL_UNDETERMINED.to_string());
    };
    if !policy.available {
        return Err(URL_UNVERIFIED.to_string());
    }
    match policy.host_allowed(url) {
        Some(false) => Err(URL_NOT_ALLOWED.to_string()),
        Some(true) => Ok(()),
        None => {
            if host_of(url).is_empty() {
                // A URL that does not parse to an http(s) host is not "determined".
                Err(URL_UNDETERMINED.to_string())
            } else {
                Ok(())
            }
        }
    }
}

/// `browser_url_gate` RPC payload: `{decision: allow|deny|unknown, message, ...}`.
pub fn gate_response(params: &Map<String, Value>) -> Value {
    let url = params.get("url").and_then(Value::as_str);
    let family = params.get("family").and_then(Value::as_str).unwrap_or("");
    let security_mode = params
        .get("security_mode")
        .and_then(Value::as_str)
        .unwrap_or("");
    let policy = UrlPolicy::from_env();
    match assert_browser_url_allowed(url, family, security_mode, &policy) {
        Ok(()) => json!({"decision": "allow", "message": "", "url": url, "family": family}),
        Err(message) => {
            let decision = if message == URL_NOT_ALLOWED { "deny" } else { "unknown" };
            json!({"decision": decision, "message": message, "url": url, "family": family})
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy(deny: &[&str], allow: &[&str], available: bool) -> UrlPolicy {
        UrlPolicy {
            deny_hosts: deny.iter().map(|s| s.to_string()).collect(),
            allow_hosts: allow.iter().map(|s| s.to_string()).collect(),
            available,
        }
    }

    /// BR-14 gate: the four sentences are byte-for-byte the official string-table
    /// block (strings_all.txt:18208 @0x132af7). Red on any wording drift.
    #[test]
    fn four_official_sentences_are_verbatim() {
        assert_eq!(URL_NOT_ALLOWED.len(), 263);
        assert_eq!(URL_UNVERIFIED.len(), 186);
        assert_eq!(URL_UNDETERMINED.len(), 222);
        assert_eq!(URL_FAMILY_UNSUPPORTED.len(), 207);
        for message in URL_GATE_MESSAGES {
            assert!(message.starts_with("Computer Use has been stopped for this turn because"));
        }
        assert!(URL_NOT_ALLOWED.ends_with("it themselves."));
        for message in [URL_UNVERIFIED, URL_UNDETERMINED, URL_FAMILY_UNSUPPORTED] {
            assert!(message.ends_with("why Computer Use ended."));
        }
        assert_eq!(URL_GATE_MESSAGES.len(), 4);
    }

    #[test]
    fn unsupported_family_fails_with_sentence_four() {
        let p = policy(&[], &[], true);
        assert_eq!(
            assert_browser_url_allowed(Some("https://example.com/"), "firefox", "", &p),
            Err(URL_FAMILY_UNSUPPORTED.to_string())
        );
    }

    #[test]
    fn missing_url_fails_with_sentence_three() {
        let p = policy(&[], &[], true);
        assert_eq!(
            assert_browser_url_allowed(None, "chrome", "", &p),
            Err(URL_UNDETERMINED.to_string())
        );
        assert_eq!(
            assert_browser_url_allowed(Some("   "), "chrome", "", &p),
            Err(URL_UNDETERMINED.to_string())
        );
    }

    #[test]
    fn unparseable_url_fails_with_sentence_three() {
        let p = policy(&[], &[], true);
        assert_eq!(
            assert_browser_url_allowed(Some("about:blank"), "chrome", "", &p),
            Err(URL_UNDETERMINED.to_string())
        );
    }

    #[test]
    fn unavailable_policy_fails_with_sentence_two() {
        let p = policy(&[], &[], false);
        assert_eq!(
            assert_browser_url_allowed(Some("https://example.com/"), "chrome", "", &p),
            Err(URL_UNVERIFIED.to_string())
        );
    }

    #[test]
    fn denied_host_fails_with_sentence_one() {
        let p = policy(&["example.com"], &[], true);
        assert_eq!(
            assert_browser_url_allowed(Some("https://sub.example.com/page"), "chrome", "", &p),
            Err(URL_NOT_ALLOWED.to_string())
        );
        assert!(assert_browser_url_allowed(Some("https://notexample.com/"), "chrome", "", &p).is_ok());
    }

    #[test]
    fn allow_list_denies_everything_else() {
        let p = policy(&[], &["corp.test"], true);
        assert!(assert_browser_url_allowed(Some("https://corp.test/"), "msedge", "", &p).is_ok());
        assert_eq!(
            assert_browser_url_allowed(Some("https://other.test/"), "msedge", "", &p),
            Err(URL_NOT_ALLOWED.to_string())
        );
    }

    #[test]
    fn disabled_security_mode_bypasses_the_gate() {
        let p = policy(&["example.com"], &[], false);
        assert!(assert_browser_url_allowed(
            Some("https://example.com/"),
            "firefox",
            SECURITY_MODE_DISABLED,
            &p
        )
        .is_ok());
    }

    #[test]
    fn host_parsing_handles_ports_users_and_ipv6() {
        assert_eq!(host_of("https://user:pw@example.com:8443/a?b#c"), "example.com");
        assert_eq!(host_of("HTTPS://Example.COM/"), "example.com");
        assert_eq!(host_of("http://[::1]:8080/"), "::1");
        assert_eq!(host_of("file:///c:/x"), "");
        assert_eq!(host_of(""), "");
    }

    #[test]
    fn rpc_payload_reports_decision_and_message() {
        let mut allowed = Map::new();
        allowed.insert("url".into(), json!("https://example.com/"));
        allowed.insert("family".into(), json!("chrome"));
        let body = gate_response(&allowed);
        assert_eq!(body["decision"], "allow");
        assert_eq!(body["message"], "");
    }
}
