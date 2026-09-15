//! Model-facing prompt assembly.
//!
//! Single source of truth: the official plugin documents (byte-identical copies of
//! `openai-bundled/computer-use/<version>/docs/{guidance,api,confirmations}.md`)
//! live in `helper-rs/assets/prompts/` and are embedded at build time, so the
//! helper and the DSH plugin can never drift apart again.
//!
//! The DSH header below replaces the official `node_repl` bootstrap with this
//! session's first-class tool convention (decision D1) and carries the
//! non-negotiable Windows Automation Safety rules that the plugin path never
//! used to reach the model.

/// DSH session header (tool convention + the official safety/recovery rules),
/// shared verbatim with the DSH plugin so both planes emit identical text.
const DSH_HEADER: &str = include_str!("../assets/prompts/dsh-header.md");

/// Official runtime guidance, byte-identical to the plugin document.
// The reference documents are shipped verbatim in `assets/prompts/` and mirrored
// into the plugin skill bundle, which is where the model reads them from.
// `tests/test_parity.py` asserts they are present and byte-identical to the
// official plugin copies.
/// The always-on section: session contract, the two-cell loop, staleness, recovery
/// and the complete Windows Automation Safety block.
///
/// Official parity note: the official bundle keeps its skill body + guidance +
/// api + confirmations out of the per-call system prompt — SKILL.md is a skill and
/// the other three are read on demand. `api.md` and `confirmations.md` therefore
/// live in the skill bundle and are only pulled in when the model reads them;
/// loading them unconditionally cost ~4.2k extra tokens on every request.
pub fn native_prompt() -> String {
    DSH_HEADER.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prompt_carries_the_safety_and_recovery_sections() {
        let prompt = native_prompt();
        // The safety block that never used to reach the model.
        assert!(prompt.contains("Non-negotiable Windows Automation Safety"));
        assert!(prompt.contains("Do not use the Windows key or shortcuts involving the Windows key"));
        // The official recovery and interrupt guidance.
        assert!(prompt.contains("## Recovery"));
        assert!(prompt.contains("## Interrupted turns"));
        // The reference documents live in the skill bundle, so the always-on
        // section must point at them instead of inlining them.
        assert!(prompt.contains("references/guidance.md"));
        assert!(prompt.contains("references/api.md"));
        assert!(prompt.contains("references/confirmations.md"));
    }

    #[test]
    fn prompt_stays_within_the_always_on_budget() {
        // Official keeps the per-call prompt small: the skill body plus pointers.
        // Inlining guidance + api + confirmations cost ~9k tokens on every request.
        let prompt = native_prompt();
        assert!(
            prompt.chars().count() < 12_000,
            "always-on prompt grew to {} chars",
            prompt.chars().count()
        );
    }

    #[test]
    fn prompt_drops_the_invented_ttl_rule() {
        let prompt = native_prompt();
        // Official has no time-based observation expiry; the prompt must not
        // teach one.
        assert!(!prompt.contains("observation expired"));
        assert!(!prompt.contains("default 15s"));
        assert!(!prompt.contains("Stale/TTL"));
        // And it must not ban shell use for looking at the UI, which the official
        // prompt never does.
        assert!(!prompt.contains("Do not run pwsh, OCR, PrintWindow"));
    }

    #[test]
    fn prompt_states_the_official_staleness_rule() {
        let prompt = native_prompt();
        assert!(prompt.contains("valid only for the observation that produced them"));
    }
}
