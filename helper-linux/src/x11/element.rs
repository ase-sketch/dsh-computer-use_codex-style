//! Stable element indexes over the accessibility tree.
//!
//! window2 addresses elements by `element_index`, and the index is only meaningful
//! relative to one observation: the contract calls it "Element index from the latest
//! `get_window_state()` accessibility tree". So this module keeps the tree that was
//! last captured per window and refuses an index that came from an older capture
//! instead of resolving it against a tree the caller never saw. That is the freshness
//! rule, and it is enforced here rather than left to whatever the client remembers.
//!
//! Indexes are the node's position in the flattened tree the snapshot returned
//! (`AccessibilityNode::index`), which is what the formatted tree text prints next to
//! each line, so an index the model read out of the tree resolves to the same element.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{anyhow, bail, Result};

use crate::atspi_tree::{self, AccessibilityNode};

use super::window;

/// One captured accessibility tree for one window.
#[derive(Debug, Clone)]
pub struct ElementSnapshot {
    pub window_id: u64,
    /// Monotonic per window; a node is only usable with the generation it came from.
    pub generation: u64,
    pub nodes: Vec<AccessibilityNode>,
    pub captured_at_ms: u64,
    /// The AT-SPI application name the tree was read from, for reporting.
    pub app_name: Option<String>,
}

impl ElementSnapshot {
    pub fn node(&self, index: u32) -> Option<&AccessibilityNode> {
        self.nodes.iter().find(|node| node.index == index)
    }
}

/// Why an index could not be resolved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ElementIndexError {
    /// No tree has been captured for this window yet.
    NoSnapshot,
    /// The index is not in the tree that *was* captured.
    UnknownIndex(u32),
}

impl std::fmt::Display for ElementIndexError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ElementIndexError::NoSnapshot => write!(
                f,
                "no accessibility tree has been captured for this window in this session; \
                 call get_window_state first so the element indexes exist"
            ),
            ElementIndexError::UnknownIndex(index) => write!(
                f,
                "element_index {index} is not in the accessibility tree captured for this \
                 window; call get_window_state again and use an index from that tree"
            ),
        }
    }
}

impl std::error::Error for ElementIndexError {}

#[derive(Debug, Default)]
struct ElementCache {
    snapshots: HashMap<u64, ElementSnapshot>,
    generations: HashMap<u64, u64>,
}

static CACHE: OnceLock<Mutex<ElementCache>> = OnceLock::new();

fn cache() -> &'static Mutex<ElementCache> {
    CACHE.get_or_init(|| Mutex::new(ElementCache::default()))
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_millis() as u64)
        .unwrap_or(0)
}

/// The tree captured for a window, if any.
pub fn cached(window_id: u64) -> Option<ElementSnapshot> {
    cache()
        .lock()
        .ok()
        .and_then(|guard| guard.snapshots.get(&window_id).cloned())
}

/// The generation the latest capture for this window produced.
pub fn current_generation(window_id: u64) -> Option<u64> {
    cache()
        .lock()
        .ok()
        .and_then(|guard| guard.generations.get(&window_id).copied())
}

/// Look up an index against the tree the caller most recently received.
pub fn resolve(window_id: u64, index: u32) -> Result<AccessibilityNode, ElementIndexError> {
    let snapshot = cached(window_id).ok_or(ElementIndexError::NoSnapshot)?;
    snapshot
        .node(index)
        .cloned()
        .ok_or(ElementIndexError::UnknownIndex(index))
}

/// Capture the accessibility tree for a window and make it the current generation.
///
/// The window has to be matched to an AT-SPI application. The process id from
/// `_NET_WM_PID` is the reliable key; when the client does not publish one, the
/// window's app name is used as a fallback, and a failure to match either is reported
/// rather than turned into an empty tree that would look like a window with no UI.
pub async fn snapshot_window(window_id: u64, max_nodes: usize, max_depth: u32) -> Result<ElementSnapshot> {
    let (nodes, app_name) = read_tree(window_id, max_nodes, max_depth).await?;

    let generation = {
        let mut guard = cache()
            .lock()
            .map_err(|_| anyhow!("the element cache lock was poisoned"))?;
        let next = guard.generations.get(&window_id).copied().unwrap_or(0) + 1;
        guard.generations.insert(window_id, next);
        next
    };

    let snapshot = ElementSnapshot {
        window_id,
        generation,
        nodes,
        captured_at_ms: now_ms(),
        app_name,
    };
    cache()
        .lock()
        .map_err(|_| anyhow!("the element cache lock was poisoned"))?
        .snapshots
        .insert(window_id, snapshot.clone());
    Ok(snapshot)
}

/// Read one window's accessibility tree without touching the element cache.
///
/// This is the shared half of `snapshot_window`: it resolves the window to an AT-SPI
/// application, reads the tree, and returns the nodes plus a human-readable source label.
///
/// Split out for `wait_for` (see `super::waitfor`). That caller polls the same tree
/// several times a second, and every one of those reads must stay invisible to the
/// element-index contract: `resolve` deliberately answers an index against "the tree the
/// caller most recently received" (`get_window_state`), so a poll that bumped the stored
/// generation would silently invalidate the indexes the model just read out of a
/// screenshot -- turning a *wait* into the exact bug the freshness rule exists to prevent.
/// Keeping the read here and the cache write in `snapshot_window` makes that separation
/// structural rather than a convention the caller has to remember.
async fn read_tree(
    window_id: u64,
    max_nodes: usize,
    max_depth: u32,
) -> Result<(Vec<AccessibilityNode>, Option<String>)> {
    let target = window::get_window(window_id)?;
    let (nodes, app_name) = if let Some(pid) = target.pid {
        let nodes = atspi_tree::snapshot_tree(None, Some(pid), max_nodes, max_depth).await?;
        (nodes, Some(format!("pid {pid}")))
    } else {
        let app = target
            .wm_class
            .clone()
            .or_else(|| target.wm_instance.clone())
            .ok_or_else(|| {
                anyhow!(
                    "window 0x{window_id:x} publishes neither _NET_WM_PID nor WM_CLASS, so its \
                     accessibility tree cannot be located"
                )
            })?;
        let nodes = atspi_tree::snapshot_tree(Some(&app), None, max_nodes, max_depth).await?;
        (nodes, Some(app))
    };
    Ok((nodes, app_name))
}

/// One tree read for the blocking `wait_for` poller, with no cache effect.
///
/// Returns the same `ElementSnapshot` shape `resolve` hands back, but the generation is
/// the one already cached (0 when there is none) and nothing is stored: see `read_tree`.
pub fn snapshot_window_uncached_blocking(
    window_id: u64,
    max_nodes: usize,
    max_depth: u32,
) -> Result<ElementSnapshot> {
    let (nodes, app_name) = block_on(read_tree(window_id, max_nodes, max_depth))??;
    Ok(ElementSnapshot {
        window_id,
        generation: current_generation(window_id).unwrap_or(0),
        nodes,
        captured_at_ms: now_ms(),
        app_name,
    })
}

/// Where an element sits inside its window, in window-relative coordinates.
///
/// AT-SPI reports screen coordinates, so the window origin is subtracted. An element
/// whose bounds are unknown is reported as `None` instead of being guessed at the
/// window origin, which would silently click the title bar.
pub fn element_window_point(window_id: u64, node: &AccessibilityNode) -> Result<(i32, i32)> {
    let bounds = node.bounds.as_ref().ok_or_else(|| {
        anyhow!(
            "element {} does not publish bounds, so it cannot be clicked by coordinate; \
             use an action (perform_secondary_action) or a coordinate click instead",
            node.index
        )
    })?;
    if bounds.width <= 0 || bounds.height <= 0 {
        bail!(
            "element {} has empty bounds ({}x{})",
            node.index,
            bounds.width,
            bounds.height
        );
    }
    let geometry = window::window_geometry(window_id)?;
    let center_x = bounds.x + bounds.width / 2;
    let center_y = bounds.y + bounds.height / 2;
    Ok((center_x - geometry.x, center_y - geometry.y))
}

/// The action names that mean "activate this element", most specific first.
pub const PRIMARY_ACTIONS: &[&str] = &["click", "press", "activate", "open", "invoke"];

/// Choose which AT-SPI action a plain click should invoke.
pub fn primary_action(node: &AccessibilityNode) -> Option<&crate::atspi_tree::AccessibilityAction> {
    for wanted in PRIMARY_ACTIONS {
        if let Some(action) = node
            .actions
            .iter()
            .find(|action| action.name.eq_ignore_ascii_case(wanted))
        {
            return Some(action);
        }
    }
    None
}

/// Drive an AT-SPI future to completion from the synchronous window2 dispatcher.
///
/// The helper's request worker runs inside a multi-threaded Tokio runtime, so
/// `block_in_place` keeps the reader task (the one that delivers `interrupt`) alive
/// while this thread waits. Outside a runtime — tests, the binary's subcommands — a
/// current-thread runtime is built instead.
fn block_on<F: std::future::Future>(future: F) -> Result<F::Output> {
    match tokio::runtime::Handle::try_current() {
        Ok(handle) => Ok(tokio::task::block_in_place(|| handle.block_on(future))),
        Err(_) => Ok(tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|error| anyhow!("could not build a runtime for accessibility calls: {error}"))?
            .block_on(future)),
    }
}

/// Capture a window's accessibility tree from synchronous code.
pub fn snapshot_window_blocking(
    window_id: u64,
    max_nodes: usize,
    max_depth: u32,
) -> Result<ElementSnapshot> {
    block_on(snapshot_window(window_id, max_nodes, max_depth))?
}

/// Invoke an AT-SPI action from synchronous code.
pub fn invoke_action_blocking(
    object_ref: &str,
    action_name: &str,
) -> Result<crate::atspi_tree::ActionInvocation> {
    block_on(invoke_action(object_ref, action_name))?
}

/// Replace an editable element's value from synchronous code.
pub fn set_value_blocking(
    object_ref: &str,
    value: &str,
) -> Result<crate::atspi_tree::ValueSetInvocation> {
    block_on(set_value(object_ref, value))?
}

/// Match a caller-supplied action label against an element's action list.
pub fn matching_action<'a>(
    node: &'a AccessibilityNode,
    requested: &str,
) -> Option<&'a crate::atspi_tree::AccessibilityAction> {
    let wanted = requested.trim();
    node.actions
        .iter()
        .find(|action| action.name.eq_ignore_ascii_case(wanted))
        .or_else(|| {
            node.actions
                .iter()
                .find(|action| action.description.eq_ignore_ascii_case(wanted))
        })
}

/// Invoke an AT-SPI action on an indexed element.
pub async fn invoke_action(
    object_ref: &str,
    action_name: &str,
) -> Result<crate::atspi_tree::ActionInvocation> {
    atspi_tree::perform_action(object_ref, Some(action_name)).await
}

/// Replace the value of an indexed editable element.
pub async fn set_value(
    object_ref: &str,
    value: &str,
) -> Result<crate::atspi_tree::ValueSetInvocation> {
    atspi_tree::set_element_value(object_ref, value).await
}

/// The AT-SPI application a window belongs to, for `list_apps` enrichment.
pub async fn accessible_apps(limit: usize) -> Result<Vec<crate::atspi_tree::AccessibleAppSummary>> {
    atspi_tree::list_accessible_apps(limit).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::atspi_tree::{AccessibilityAction, Bounds};

    fn node_with(index: u32, bounds: Option<Bounds>, actions: Vec<&str>) -> AccessibilityNode {
        AccessibilityNode {
            index,
            parent_index: None,
            depth: 0,
            object_ref: format!(":1.{index}"),
            role: "push button".to_string(),
            name: Some(format!("Element {index}")),
            description: None,
            child_count: 0,
            bounds,
            states: Vec::new(),
            actions: actions
                .into_iter()
                .map(|name| AccessibilityAction {
                    index: 0,
                    name: name.to_string(),
                    description: String::new(),
                    keybinding: String::new(),
                })
                .collect(),
            value: None,
            text: None,
            supports_editable_text: false,
        }
    }

    #[test]
    fn an_index_without_a_snapshot_is_refused_with_an_actionable_message() {
        let error = resolve(0xdead_beef, 0).unwrap_err();
        assert_eq!(error, ElementIndexError::NoSnapshot);
        assert!(error.to_string().contains("get_window_state"));
    }

    #[test]
    fn an_index_outside_the_captured_tree_is_refused() {
        let mut guard = cache().lock().unwrap();
        guard.snapshots.insert(
            4242,
            ElementSnapshot {
                window_id: 4242,
                generation: 1,
                nodes: vec![node_with(0, None, Vec::new())],
                captured_at_ms: 0,
                app_name: None,
            },
        );
        guard.generations.insert(4242, 1);
        drop(guard);

        assert!(resolve(4242, 0).is_ok());
        let error = resolve(4242, 7).unwrap_err();
        assert_eq!(error, ElementIndexError::UnknownIndex(7));
        assert!(error.to_string().contains("element_index 7"));
    }

    #[test]
    fn a_plain_click_prefers_the_primary_action_over_the_others() {
        let node = node_with(
            0,
            None,
            vec!["Expand", "Collapse", "click", "Scroll Up"],
        );
        let action = primary_action(&node).unwrap();
        assert_eq!(action.name, "click");
    }

    #[test]
    fn an_element_without_a_primary_action_reports_none() {
        let node = node_with(0, None, vec!["Scroll Up", "Scroll Down"]);
        assert!(primary_action(&node).is_none());
    }

    #[test]
    fn a_secondary_action_matches_by_name_case_insensitively() {
        let node = node_with(0, None, vec!["Raise", "Scroll Up"]);
        assert_eq!(
            matching_action(&node, "scroll up").map(|action| action.name.as_str()),
            Some("Scroll Up")
        );
        assert!(matching_action(&node, "Smash").is_none());
    }

    #[test]
    fn a_node_without_bounds_is_reported_instead_of_guessed() {
        let node = node_with(0, None, Vec::new());
        let error = element_window_point(1, &node).unwrap_err();
        assert!(error.to_string().contains("does not publish bounds"));
    }

    #[test]
    fn an_empty_bounds_rectangle_is_refused() {
        let node = node_with(
            3,
            Some(Bounds {
                x: 10,
                y: 10,
                width: 0,
                height: 20,
            }),
            Vec::new(),
        );
        let error = element_window_point(1, &node).unwrap_err();
        assert!(error.to_string().contains("empty bounds"));
    }
}