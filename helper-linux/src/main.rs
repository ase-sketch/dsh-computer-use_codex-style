#[cfg(target_os = "linux")]
use mimalloc::MiMalloc;

#[cfg(target_os = "linux")]
#[global_allocator]
static GLOBAL: MiMalloc = MiMalloc;

// The binary is a thin front end over the library: both the JSONL helper and the
// original MCP/CLI entry points come from the same crate, so there is exactly one
// definition of every backend rather than a second module tree compiled into the bin.
use dsh_computer_use::{
    abs_pointer, atspi_tree, diagnostics, gnome_extension, helper, screenshot, server, windows,
};

use anyhow::{Context, Result};

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<()> {
    diagnostics::hydrate_session_bus_env();

    match std::env::args().nth(1).as_deref() {
        // The plugin's stdio JSONL helper protocol. This is the default entry point
        // because the plugin's JS sidecar spawns the binary with no subcommand.
        Some("helper") | None => {
            let result = helper::serve().await;
            helper::flush_stdout();
            result
        }
        Some("mcp") => server::serve_mcp().await,
        Some("doctor") => {
            let report = diagnostics::doctor_report();
            println!(
                "{}",
                serde_json::to_string_pretty(&report)
                    .context("failed to serialize doctor report")?
            );
            Ok(())
        }
        Some("setup") => {
            let report = diagnostics::setup_accessibility_report();
            println!(
                "{}",
                serde_json::to_string_pretty(&report)
                    .context("failed to serialize setup report")?
            );
            Ok(())
        }
        Some("apps") => {
            let apps = atspi_tree::list_accessible_apps(50).await?;
            println!(
                "{}",
                serde_json::to_string_pretty(&apps)
                    .context("failed to serialize accessible apps")?
            );
            Ok(())
        }
        Some("state") => {
            let app_name_or_bundle_identifier = std::env::args().nth(2);
            let (max_nodes, max_depth) = atspi_tree::snapshot_limits(None, None);
            let nodes = atspi_tree::snapshot_tree(
                app_name_or_bundle_identifier.as_deref(),
                None,
                max_nodes,
                max_depth,
            )
            .await?;
            println!(
                "{}",
                serde_json::to_string_pretty(&nodes)
                    .context("failed to serialize accessibility tree")?
            );
            Ok(())
        }
        // Hidden dev command: empirically test the absolute pointer.
        // `abs-test X Y` moves to logical (X,Y) and left-clicks, sizing the
        // device to the live screenshot dimensions.
        Some("abs-test") => {
            let x: i32 = std::env::args()
                .nth(2)
                .and_then(|s| s.parse().ok())
                .unwrap_or(0);
            let y: i32 = std::env::args()
                .nth(3)
                .and_then(|s| s.parse().ok())
                .unwrap_or(0);
            let cap = screenshot::capture_screenshot_raw().await?;
            eprintln!("desktop logical size: {}x{}", cap.width, cap.height);
            let mut p = abs_pointer::AbsPointer::create(cap.width as i32, cap.height as i32)?;
            p.click(x, y, abs_pointer::PointerButton::Left, 1)?;
            println!(
                "{}",
                serde_json::json!({"ok": true, "x": x, "y": y, "w": cap.width, "h": cap.height})
            );
            Ok(())
        }
        Some("screenshot") => {
            let capture = screenshot::capture_screenshot().await?;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "mime_type": capture.mime_type,
                    "source": capture.source,
                    "width": capture.width,
                    "height": capture.height,
                    "coordinate_width": capture.coordinate_width,
                    "coordinate_height": capture.coordinate_height,
                    "scale": capture.scale,
                    "resized": capture.resized,
                    "bytes": capture.bytes,
                    "original_bytes": capture.original_bytes,
                    "max_bytes": capture.max_bytes,
                    "format": capture.format,
                    "quality": capture.quality,
                    "data_url_length": capture.data_url.len()
                }))
                .context("failed to serialize screenshot report")?
            );
            Ok(())
        }
        Some("windows") => {
            let report = match windows::list_windows().await {
                Ok(windows) => {
                    let backend = windows
                        .first()
                        .map(|window| window.backend.as_str())
                        .unwrap_or(windows::GNOME_SHELL_INTROSPECT_BACKEND);
                    serde_json::json!({
                        "backend": backend,
                        "windows": windows,
                        "error": null,
                        "permissions_hint": null,
                    })
                }
                Err(error) => {
                    let error = format!("{error:#}");
                    serde_json::json!({
                        "backend": "unavailable",
                        "windows": [],
                        "error": error,
                        "permissions_hint": windows::window_permission_hint(&error),
                    })
                }
            };
            println!("{}", serde_json::to_string_pretty(&report)?);
            Ok(())
        }
        Some("setup-window-targeting") => {
            let report = gnome_extension::setup_window_targeting_report().await;
            println!(
                "{}",
                serde_json::to_string_pretty(&report)
                    .context("failed to serialize window targeting setup report")?
            );
            Ok(())
        }
        Some("--help") | Some("-h") => {
            print_help();
            Ok(())
        }
        Some(command) => {
            anyhow::bail!(
                "unknown command '{command}'. Expected one of: helper (default), mcp, doctor, setup, apps, state, screenshot, windows, setup-window-targeting"
            );
        }
    }
}

fn print_help() {
    println!(
        "dsh-computer-use (Linux)\n\nThe plugin spawns this binary with no arguments to speak the stdio JSONL helper protocol;\n  dsh-computer-use helper  is the explicit form of the same thing.\n\nUsage:\n  dsh-computer-use [helper]\n  dsh-computer-use mcp\n  dsh-computer-use doctor\n  dsh-computer-use setup\n  dsh-computer-use setup-window-targeting\n  dsh-computer-use apps\n  dsh-computer-use state [APP_NAME]\n  dsh-computer-use screenshot\n  dsh-computer-use windows"
    );
}
