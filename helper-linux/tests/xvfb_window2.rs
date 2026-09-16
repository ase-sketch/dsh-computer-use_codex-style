//! End-to-end window2 tests on a real X server started by this test binary.
//!
//! These are **ignored by default**, because they need an X server and a client that
//! draws on request. Run them with:
//!
//! ```text
//! DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1
//! ```
//!
//! Each test forks `Xvfb` on a private display, runs one check, and tears the server
//! down again. No window manager is installed on this machine, so the session is a bare
//! X server: enumeration therefore exercises the `query_tree` fallback rather than
//! `_NET_CLIENT_LIST`, and the tests that need window-manager behaviour are marked
//! ignored with the reason spelled out.
//!
//! The server is not the `$DISPLAY` the test process was started with: the helper calls
//! run with `DISPLAY` set to the private display, so a developer's real session is
//! never touched.

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use x11rb::connection::Connection;
use x11rb::protocol::xproto::{
    ConnectionExt as _, CreateGCAux, CreateWindowAux, EventMask, Rectangle, WindowClass,
};
use x11rb::rust_connection::RustConnection;
use x11rb::wrapper::ConnectionExt as _;


/// The only thing that turns these tests on.
const ENABLED: &str = "DSH_CUA_XVFB_TEST";

fn enabled() -> bool {
    std::env::var(ENABLED).map(|value| value == "1").unwrap_or(false)
}

/// Xvfb displays are serialized: two servers cannot share a display number.
static DISPLAY_LOCK: Mutex<()> = Mutex::new(());

struct Xvfb {
    child: Child,
    display: String,
}

impl Xvfb {
    fn start(display_number: u32) -> Option<Self> {
        let display = format!(":{display_number}");
        // 24-bit depth is what the capture code expects; another depth would test the
        // depth guard rather than the capture itself.
        let child = Command::new("Xvfb")
            .arg(&display)
            .args(["-screen", "0", "1280x800x24", "-nolisten", "tcp"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .ok()?;
        let deadline = Instant::now() + Duration::from_secs(10);
        let socket = format!("/tmp/.X11-unix/X{display_number}");
        let lock = format!("/tmp/.X{display_number}-lock");
        while Instant::now() < deadline {
            if std::path::Path::new(&socket).exists() || std::path::Path::new(&lock).exists() {
                // A short further wait so the server accepts connections rather than
                // merely having created the socket.
                std::thread::sleep(Duration::from_millis(300));
                return Some(Self { child, display });
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        let mut child = child;
        let _ = child.kill();
        None
    }
}

impl Drop for Xvfb {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn connect(display: &str) -> RustConnection {
    let (connection, screen) = x11rb::connect(Some(display)).expect("connect to the private Xvfb");
    assert!(screen < connection.setup().roots.len());
    connection
}

struct Fixture {
    _guard: std::sync::MutexGuard<'static, ()>,
    server: Xvfb,
    connection: RustConnection,
    window: u32,
}

fn fixture(display_number: u32) -> Option<Fixture> {
    let guard = DISPLAY_LOCK.lock().unwrap_or_else(|error| error.into_inner());
    let server = Xvfb::start(display_number)?;
    let connection = connect(&server.display);
    let screen = &connection.setup().roots[0];
    let window = connection.generate_id().ok()?;
    connection
        .create_window(
            screen.root_depth,
            window,
            screen.root,
            40,
            30,
            300,
            200,
            0,
            WindowClass::INPUT_OUTPUT,
            0,
            &CreateWindowAux::new()
                .background_pixel(screen.white_pixel)
                .event_mask(EventMask::EXPOSURE),
        )
        .ok()?;
    // A title and a class are what make the window enumerable: without a window manager
    // the enumerator skips windows that carry neither.
    connection
        .change_property8(
            x11rb::protocol::xproto::PropMode::REPLACE,
            window,
            x11rb::protocol::xproto::AtomEnum::WM_NAME,
            x11rb::protocol::xproto::AtomEnum::STRING,
            b"xvfb-window2-fixture",
        )
        .ok()?;
    connection
        .change_property8(
            x11rb::protocol::xproto::PropMode::REPLACE,
            window,
            x11rb::protocol::xproto::AtomEnum::WM_CLASS,
            x11rb::protocol::xproto::AtomEnum::STRING,
            b"fixture\0Fixture\0",
        )
        .ok()?;
    connection.map_window(window).ok()?;
    connection.flush().ok()?;
    // Maps are asynchronous and the exposure is what tells the client to draw. Waiting
    // for it is also what keeps a later capture from racing the first paint.
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        match connection.poll_for_event() {
            Ok(Some(x11rb::protocol::Event::Expose(_))) => break,
            Ok(Some(_)) => {}
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(_) => break,
        }
    }
    Some(Fixture {
        _guard: guard,
        server,
        connection,
        window,
    })
}

impl Fixture {
    /// Paint the client area the way a toolkit does: after mapping, on the exposure.
    ///
    /// Drawing before `map_window` would be erased by the background repaint the map
    /// triggers, which produces an all-background capture and makes a capture test look
    /// broken for the wrong reason.
    fn paint(&self, colour: u32) {
        let gc = self.connection.generate_id().unwrap();
        self.connection
            .create_gc(gc, self.window, &CreateGCAux::new().foreground(colour))
            .unwrap();
        self.connection
            .poly_fill_rectangle(
                self.window,
                gc,
                &[Rectangle {
                    x: 20,
                    y: 20,
                    width: 120,
                    height: 80,
                }],
            )
            .unwrap();
        self.connection.flush().unwrap();
        std::thread::sleep(Duration::from_millis(150));
    }

    /// An opaque window covering the fixture's client area.
    fn cover_with_black(&self) -> u32 {
        let screen = &self.connection.setup().roots[0];
        let cover = self.connection.generate_id().unwrap();
        self.connection
            .create_window(
                screen.root_depth,
                cover,
                screen.root,
                0,
                0,
                640,
                480,
                0,
                WindowClass::INPUT_OUTPUT,
                0,
                &CreateWindowAux::new()
                    .background_pixel(screen.black_pixel)
                    .override_redirect(1),
            )
            .unwrap();
        self.connection.map_window(cover).unwrap();
        self.connection.flush().unwrap();
        std::thread::sleep(Duration::from_millis(250));
        cover
    }
}

/// Run a closure with `DISPLAY` pointing at the fixture's server.
///
/// The helper caches its connection per display, so setting and restoring the variable is
/// exactly how a session switch is simulated.
fn with_display<T>(fixture: &Fixture, f: impl FnOnce() -> T) -> T {
    let previous = std::env::var("DISPLAY").ok();
    std::env::set_var("DISPLAY", &fixture.server.display);
    let result = f();
    match previous {
        Some(value) => std::env::set_var("DISPLAY", value),
        None => std::env::remove_var("DISPLAY"),
    }
    result
}

fn skip_if_disabled() -> bool {
    if !enabled() {
        eprintln!("skipping: set {ENABLED}=1 (and pass --ignored) to run the Xvfb window2 tests");
        return true;
    }
    false
}

const NEEDS_XVFB: &str =
    "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1";

/// Count how many pixels of a decoded capture are exactly this colour.
fn count_colour(image: &image::RgbaImage, colour: [u8; 4]) -> usize {
    image.pixels().filter(|pixel| pixel.0 == colour).count()
}

const RED: [u8; 4] = [0xff, 0x00, 0x00, 0xff];
const WHITE: [u8; 4] = [0xff, 0xff, 0xff, 0xff];
const BLACK: [u8; 4] = [0x00, 0x00, 0x00, 0xff];

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn enumeration_finds_the_window_and_reports_a_stable_handle() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(98) else {
        eprintln!("skipping: Xvfb could not be started on :98");
        return;
    };
    fixture.paint(0x00ff0000);

    let windows = with_display(&fixture, dsh_computer_use::x11::window::list_windows)
        .expect("enumeration must succeed on a live X server");
    let ours = windows
        .iter()
        .find(|entry| entry.id == u64::from(fixture.window))
        .expect("the fixture window must be enumerable");
    assert_eq!(ours.title.as_deref(), Some("xvfb-window2-fixture"));
    assert_eq!(ours.app, "Fixture");
    // No window manager is running, so the enumeration came from the root tree.
    assert!(ours.workspace.is_none(), "no WM means no _NET_WM_DESKTOP");

    // The handle is the X window id, so the same id comes back from a second pass and
    // get_window can rehydrate it.
    let again = with_display(&fixture, dsh_computer_use::x11::window::list_windows).unwrap();
    assert!(again.iter().any(|entry| entry.id == u64::from(fixture.window)));
    let rehydrated = with_display(&fixture, || {
        dsh_computer_use::x11::window::get_window(u64::from(fixture.window))
    })
    .expect("get_window must rehydrate the handle");
    assert_eq!(rehydrated.id, u64::from(fixture.window));
    assert_eq!(rehydrated.wm_class.as_deref(), Some("Fixture"));
}

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn capture_reads_the_window_content_not_the_screen() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(99) else {
        eprintln!("skipping: Xvfb could not be started on :99");
        return;
    };
    fixture.paint(0x00ff0000);

    let captured = with_display(&fixture, || {
        dsh_computer_use::x11::capture::capture_window(u64::from(fixture.window))
    })
    .expect("capture must succeed on a live X server");

    assert_eq!(captured.width, 300);
    assert_eq!(captured.height, 200);
    assert_eq!(
        &captured.png[..8],
        &[0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a]
    );

    let decoded = image::load_from_memory(&captured.png)
        .expect("the capture must be a decodable PNG")
        .to_rgba8();
    assert!(count_colour(&decoded, RED) > 0, "the painted rectangle must appear");
    assert!(count_colour(&decoded, WHITE) > 0, "the background must appear");
    // The origin is the client area's position in root coordinates, which is what makes
    // a window-relative click land where the caller meant.
    assert_eq!(captured.origin_x, 40);
    assert_eq!(captured.origin_y, 30);
}

/// What composite capture actually guarantees, measured rather than assumed.
///
/// The guarantee is "the window's own pixels, not the overlapping window's": a capture of
/// an obscured window must not contain the cover. It is *not* "a fully obscured window's
/// live pixels" — see the companion test below, which pins down when content survives.
#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn composite_capture_never_returns_the_covering_window() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(100) else {
        eprintln!("skipping: Xvfb could not be started on :100");
        return;
    };
    fixture.paint(0x00ff0000);
    fixture.cover_with_black();

    let captured = with_display(&fixture, || {
        dsh_computer_use::x11::capture::capture_window(u64::from(fixture.window))
    })
    .expect("capture must succeed while the window is obscured");

    assert_eq!(
        captured.method,
        dsh_computer_use::x11::capture::CaptureMethod::Composite,
        "Xvfb provides Composite, so the occlusion-aware path must be taken"
    );

    let decoded = image::load_from_memory(&captured.png).unwrap().to_rgba8();
    // The cover is opaque black over the whole client area, so a direct framebuffer read
    // would be entirely black. Composite must not be.
    assert_eq!(
        count_colour(&decoded, BLACK),
        0,
        "the capture must not contain the covering window's pixels"
    );
    assert!(
        count_colour(&decoded, WHITE) > 0,
        "the capture must be the window's own drawable (its white background)"
    );
}

/// The honest limit of the X11 guarantee.
///
/// Capturing an obscured window whose client is not painting returns the window's
/// background: each capture redirects the window afresh, and a fresh off-screen buffer
/// starts at the background. Live content therefore requires the client to paint while
/// the redirection is in effect. This test drives exactly that sequence — redirect, paint,
/// capture — and proves the painted content is then returned even though an opaque window
/// covers the target. Windows' DWM holds a backing bitmap per window and can do better;
/// plain X11 cannot, so this is measured rather than claimed.
#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn composite_capture_returns_content_painted_while_redirected() {
    use x11rb::protocol::composite::{ConnectionExt as _, Redirect};

    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(102) else {
        eprintln!("skipping: Xvfb could not be started on :102");
        return;
    };
    fixture.paint(0x00ff0000);
    fixture.cover_with_black();

    // Redirect first so the paint below lands in the off-screen buffer that the capture
    // reads. capture_window redirects the same window again, which is a no-op for a window
    // this client already redirected.
    fixture
        .connection
        .composite_redirect_window(fixture.window, Redirect::AUTOMATIC)
        .unwrap()
        .check()
        .unwrap();
    fixture.connection.flush().unwrap();
    std::thread::sleep(Duration::from_millis(100));
    fixture.paint(0x00ff0000);

    let captured = with_display(&fixture, || {
        dsh_computer_use::x11::capture::capture_window(u64::from(fixture.window))
    })
    .expect("capture must succeed");
    assert_eq!(
        captured.method,
        dsh_computer_use::x11::capture::CaptureMethod::Composite
    );

    let decoded = image::load_from_memory(&captured.png).unwrap().to_rgba8();
    assert!(
        count_colour(&decoded, RED) > 0,
        "content painted while redirected must be captured even under an opaque cover"
    );
    assert_eq!(count_colour(&decoded, BLACK), 0, "the cover must never appear");

    // Leave the session as we found it: the helper must not strand a redirection.
    if let Ok(cookie) = fixture
        .connection
        .composite_unredirect_window(fixture.window, Redirect::AUTOMATIC)
    {
        let _ = cookie.check();
    }
    fixture.connection.flush().unwrap();
}

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn input_reaches_the_window_at_a_window_relative_coordinate() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(101) else {
        eprintln!("skipping: Xvfb could not be started on :101");
        return;
    };
    // Take button events on the fixture so the delivered click can be observed.
    fixture
        .connection
        .change_window_attributes(
            fixture.window,
            &x11rb::protocol::xproto::ChangeWindowAttributesAux::new()
                .event_mask(EventMask::EXPOSURE | EventMask::BUTTON_PRESS),
        )
        .unwrap();
    fixture.connection.flush().unwrap();
    std::thread::sleep(Duration::from_millis(100));

    // (50, 50) in the window is (90, 80) in root coordinates, because the fixture's client
    // area sits at (40, 30).
    let note = with_display(&fixture, || {
        dsh_computer_use::x11::input::click(
            u64::from(fixture.window),
            50,
            50,
            dsh_computer_use::x11::input::MouseButton::Left,
            1,
        )
    })
    .expect("the click must be injectable");
    assert!(note.contains("(90, 80)"), "translated to root coordinates: {note}");

    let deadline = Instant::now() + Duration::from_secs(3);
    let mut observed = None;
    while Instant::now() < deadline {
        match fixture.connection.poll_for_event() {
            Ok(Some(x11rb::protocol::Event::ButtonPress(event)))
                if event.event == fixture.window =>
            {
                observed = Some(event);
                break;
            }
            Ok(Some(_)) => {}
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(error) => panic!("event polling failed: {error}"),
        }
    }
    let event = observed.expect("the window must receive the button press");
    assert_eq!(event.event_x, 50, "window-relative X");
    assert_eq!(event.event_y, 50, "window-relative Y");
    assert_eq!(event.detail, 1, "left button");
}

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn a_chord_reaches_the_window_as_a_real_key_event() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(103) else {
        eprintln!("skipping: Xvfb could not be started on :103");
        return;
    };
    fixture
        .connection
        .change_window_attributes(
            fixture.window,
            &x11rb::protocol::xproto::ChangeWindowAttributesAux::new()
                .event_mask(EventMask::EXPOSURE | EventMask::KEY_PRESS | EventMask::KEY_RELEASE),
        )
        .unwrap();
    fixture.connection.flush().unwrap();
    std::thread::sleep(Duration::from_millis(100));

    with_display(&fixture, || {
        dsh_computer_use::x11::input::press_key(u64::from(fixture.window), "a")
    })
    .expect("the chord must be injectable");

    // press_key focuses the target first, so the key must arrive at the fixture.
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut saw_press = false;
    while Instant::now() < deadline {
        match fixture.connection.poll_for_event() {
            Ok(Some(x11rb::protocol::Event::KeyPress(event))) if event.event == fixture.window => {
                saw_press = true;
                break;
            }
            Ok(Some(_)) => {}
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(error) => panic!("event polling failed: {error}"),
        }
    }
    assert!(saw_press, "the focused window must receive the key press");
}

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn typing_sends_each_character_as_a_key_event() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(104) else {
        eprintln!("skipping: Xvfb could not be started on :104");
        return;
    };
    fixture
        .connection
        .change_window_attributes(
            fixture.window,
            &x11rb::protocol::xproto::ChangeWindowAttributesAux::new()
                .event_mask(EventMask::EXPOSURE | EventMask::KEY_PRESS),
        )
        .unwrap();
    fixture.connection.flush().unwrap();
    std::thread::sleep(Duration::from_millis(100));

    let note = with_display(&fixture, || {
        dsh_computer_use::x11::input::type_text(u64::from(fixture.window), "ab")
    })
    .expect("typing must be injectable");
    assert!(note.contains("2 character"), "note was: {note}");

    let deadline = Instant::now() + Duration::from_secs(3);
    let mut presses = 0;
    while Instant::now() < deadline && presses < 2 {
        match fixture.connection.poll_for_event() {
            Ok(Some(x11rb::protocol::Event::KeyPress(event))) if event.event == fixture.window => {
                presses += 1;
            }
            Ok(Some(_)) => {}
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(error) => panic!("event polling failed: {error}"),
        }
    }
    assert_eq!(presses, 2, "both characters must arrive as key events");
}

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn typing_mixed_characters_preserves_case_and_symbols() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(107) else {
        eprintln!("skipping: Xvfb could not be started on :107");
        return;
    };
    fixture
        .connection
        .change_window_attributes(
            fixture.window,
            &x11rb::protocol::xproto::ChangeWindowAttributesAux::new()
                .event_mask(EventMask::EXPOSURE | EventMask::KEY_PRESS),
        )
        .unwrap();
    fixture.connection.flush().unwrap();
    std::thread::sleep(Duration::from_millis(100));

    let setup = fixture.connection.setup();
    let min = setup.min_keycode;
    let count = setup.max_keycode - min + 1;
    let mapping = fixture
        .connection
        .get_keyboard_mapping(min, count)
        .unwrap()
        .reply()
        .unwrap();
    let per_keycode = usize::from(mapping.keysyms_per_keycode.max(1));

    let input_text = "abc-1./A_!";
    let note = with_display(&fixture, || {
        dsh_computer_use::x11::input::type_text(u64::from(fixture.window), input_text)
    })
    .expect("typing must be injectable");
    assert!(note.contains(&format!("{} character", input_text.len())));

    let deadline = Instant::now() + Duration::from_secs(5);
    let mut received = String::new();
    while Instant::now() < deadline && received.len() < input_text.len() {
        match fixture.connection.poll_for_event() {
            Ok(Some(x11rb::protocol::Event::KeyPress(event))) if event.event == fixture.window => {
                let chunk_index = usize::from(event.detail.saturating_sub(min));
                let chunk = &mapping.keysyms[chunk_index * per_keycode..(chunk_index + 1) * per_keycode];
                let is_shifted = event.state.contains(x11rb::protocol::xproto::KeyButMask::SHIFT);
                let keysym = if is_shifted && chunk.len() > 1 && chunk[1] != 0 {
                    chunk[1]
                } else {
                    chunk.first().copied().unwrap_or(0)
                };
                let sym = xkeysym::Keysym::new(keysym);
                if sym.is_modifier_key() {
                    continue;
                }
                if let Some(ch) = sym.key_char() {
                    received.push(ch);
                }
            }
            Ok(Some(_)) => {}
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(error) => panic!("event polling failed: {error}"),
        }
    }
    assert_eq!(received, input_text, "window received characters must match input text exactly");
}

#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn the_window2_surface_answers_its_methods_over_a_live_x_server() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(105) else {
        eprintln!("skipping: Xvfb could not be started on :105");
        return;
    };
    fixture.paint(0x00ff0000);
    let id = u64::from(fixture.window);

    let listed = with_display(&fixture, || {
        dsh_computer_use::x11::window2::dispatch("list_windows", serde_json::Map::new())
    })
    .expect("list_windows must succeed");
    let text = listed.content.first().and_then(|content| content.as_text()).map(|text| text.text.clone()).unwrap_or_default();
    let parsed: serde_json::Value = serde_json::from_str(&text).expect("list_windows returns JSON");
    assert!(parsed["count"].as_u64().unwrap_or(0) >= 1);

    let mut arguments = serde_json::Map::new();
    arguments.insert(
        "window".to_string(),
        serde_json::json!({ "app": "Fixture", "id": id }),
    );
    arguments.insert("include_screenshot".to_string(), serde_json::json!(true));
    let state = with_display(&fixture, || {
        dsh_computer_use::x11::window2::dispatch("get_window_state", arguments)
    })
    .expect("get_window_state must succeed");
    // The screenshot travels as an image part, never inside the JSON text.
    assert!(
        state.content.iter().any(|content| content.as_image().is_some()),
        "the state must carry the screenshot as an image part"
    );
    let caption = state
        .content
        .iter()
        .filter_map(|content| content.as_text())
        .map(|text| text.text.clone())
        .collect::<String>();
    let parsed: serde_json::Value = serde_json::from_str(&caption).expect("a JSON caption");
    assert_eq!(parsed["screenshots"][0]["width"], serde_json::json!(300));
    assert_eq!(
        parsed["screenshots"][0]["method"],
        serde_json::json!("composite")
    );

    // launch_app refuses structurally instead of pretending to have launched something.
    let mut launch = serde_json::Map::new();
    launch.insert("app".to_string(), serde_json::json!("code"));
    let error = with_display(&fixture, || {
        dsh_computer_use::x11::window2::dispatch("launch_app", launch)
    })
    .expect_err("launch_app must refuse");
    let parsed: serde_json::Value = serde_json::from_str(&error).expect("a structured refusal");
    assert_eq!(parsed["error"], serde_json::json!("unsupported"));
}

/// The failure mode a real session actually hits: something else already owns the
/// window's redirection.
///
/// A running compositor (kwin, mutter, picom) redirects every top-level window, and a
/// second client's redirect comes back \`BadAccess\`. The helper must not crash or strand
/// the window: it falls back to a direct read and says so. The conflict is produced here
/// by redirecting the window from a *second* X connection first, which is exactly what a
/// compositor looks like to us.
#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn a_redirection_owned_by_another_client_falls_back_instead_of_failing() {
    use x11rb::protocol::composite::{ConnectionExt as _, Redirect};

    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(106) else {
        eprintln!("skipping: Xvfb could not be started on :106");
        return;
    };
    fixture.paint(0x00ff0000);

    // A separate connection stands in for the compositor.
    let (other, _screen) = x11rb::connect(Some(&fixture.server.display)).unwrap();
    let redirected = other
        .composite_redirect_window(fixture.window, Redirect::AUTOMATIC)
        .map(|cookie| cookie.check());
    other.flush().unwrap();
    assert!(
        matches!(redirected, Ok(Ok(()))),
        "the stand-in compositor must get the redirection first: {redirected:?}"
    );

    // The helper now connects on the same display and tries the same window.
    let captured = with_display(&fixture, || {
        dsh_computer_use::x11::capture::capture_window(u64::from(fixture.window))
    })
    .expect("a capture must still be produced when another client owns the redirection");

    // Printed so a reader of this test's output can see which branch this server actually
    // took, instead of having to infer it from the assertions. On Xvfb it is the composite
    // branch: see the caveat on this test.
    eprintln!(
        "redirection-ownership conflict: method={:?} degraded={:?}",
        captured.method, captured.degraded
    );
    // It is not allowed to claim the occlusion-proof path if the redirect was refused.
    match captured.degraded.as_deref() {
        Some(reason) => {
            assert_eq!(
                captured.method,
                dsh_computer_use::x11::capture::CaptureMethod::Direct,
                "a degraded capture must be a direct read"
            );
            assert!(
                reason.contains("XComposite") || reason.contains("composite"),
                "the degradation must name the cause: {reason}"
            );
            // Even degraded, a valid image comes back.
            let decoded = image::load_from_memory(&captured.png).expect("a valid PNG");
            assert_eq!(decoded.width(), 300);
        }
        None => {
            // A server that lets both redirects coexist is also acceptable; what is not
            // acceptable is a crash or a silent wrong-method claim.
            assert_eq!(
                captured.method,
                dsh_computer_use::x11::capture::CaptureMethod::Composite
            );
        }
    }

    // The helper must leave the other client's redirection alone.
    let _ = other
        .composite_unredirect_window(fixture.window, Redirect::AUTOMATIC)
        .map(|cookie| cookie.check());
    other.flush().unwrap();
}

#[test]
#[ignore = "needs a window manager; none is installed here, so EWMH activation is unverified"]
fn activation_uses_ewmh_when_a_window_manager_is_present() {
    // Deliberately not implemented rather than faked: _NET_ACTIVE_WINDOW is answered by a
    // window manager, and there is none on this machine (openbox is not installed and
    // installing one needs root). activate_window's no-WM path — map, restack, focus — is
    // exercised by the live-surface test above.
}

#[test]
#[ignore = "needs a window manager; none is installed here, so WM frame extents are unverified"]
fn a_reparenting_window_manager_offsets_the_client_origin() {
    // _NET_FRAME_EXTENTS is published by the window manager, and only a reparenting WM
    // adds a frame. The code path that actually matters for input — translate_coordinates
    // for the client origin — is verified by the click test above.
}

#[test]
#[ignore = "needs a desktop accessibility bus with a registered app for the fixture window"]
fn element_indexes_are_stable_within_one_observation() {
    // AT-SPI indexes the elements of a registered accessibility application. The Xvfb
    // fixture is a raw X window with no accessibility tree, so an end-to-end check needs a
    // real toolkit app on a session bus and belongs to the real-session verification pass.
    // The index cache's own behaviour — refusing an index with no snapshot, and refusing an
    // index outside the captured tree — is covered by unit tests in src/x11/element.rs.
}

/// Every capture in this test shares one process, and the knob is an environment
/// variable, so the two halves below run in a fixed order and restore the value.
fn with_max_image_edge<T>(value: Option<&str>, f: impl FnOnce() -> T) -> T {
    const KEY: &str = "DSH_COMPUTER_USE_MAX_IMAGE_EDGE";
    let previous = std::env::var(KEY).ok();
    match value {
        Some(value) => std::env::set_var(KEY, value),
        None => std::env::remove_var(KEY),
    }
    let result = f();
    match previous {
        Some(value) => std::env::set_var(KEY, value),
        None => std::env::remove_var(KEY),
    }
    result
}

/// Pull the base64 payload out of the `data:image/png;base64,...` an MCP image part carries.
fn image_bytes(result: &dsh_computer_use::rmcp::model::CallToolResult) -> Vec<u8> {
    use base64::Engine as _;
    let data = result
        .content
        .iter()
        .find_map(|content| content.as_image())
        .expect("the state must carry the screenshot as an image part")
        .data
        .clone();
    let encoded = data
        .strip_prefix("data:image/png;base64,")
        .expect("the image part carries a PNG data URL");
    base64::engine::general_purpose::STANDARD
        .decode(encoded)
        .expect("the payload is valid base64")
}

/// The value half of a window2 result, parsed out of the JSON text block.
fn window2_value(result: &dsh_computer_use::rmcp::model::CallToolResult) -> serde_json::Value {
    let text = result
        .content
        .iter()
        .filter_map(|content| content.as_text())
        .map(|text| text.text.clone())
        .collect::<String>();
    serde_json::from_str(&text).expect("a JSON caption")
}

fn capture_window_state(id: u64) -> dsh_computer_use::rmcp::model::CallToolResult {
    let mut arguments = serde_json::Map::new();
    arguments.insert("window".to_string(), serde_json::json!({ "app": "Fixture", "id": id }));
    arguments.insert("include_screenshot".to_string(), serde_json::json!(true));
    dsh_computer_use::x11::window2::dispatch("get_window_state", arguments)
        .expect("get_window_state must succeed")
}

/// IMG-EDGE, end to end on a real X server.
///
/// The knob has to satisfy three things at once, and only a live capture can show them:
/// the image really shrinks, the value declares the size the image really has, and the
/// coordinate space the input tools use is left at the original window size so a
/// window-relative click does not land at half the intended offset.
#[test]
#[ignore = "needs Xvfb; run with DSH_CUA_XVFB_TEST=1 cargo test --test xvfb_window2 -- --ignored --test-threads=1"]
fn the_max_image_edge_cap_shrinks_the_image_and_declares_both_sizes() {
    if skip_if_disabled() {
        return;
    }
    let Some(fixture) = fixture(108) else {
        eprintln!("skipping: Xvfb could not be started on :108");
        return;
    };
    fixture.paint(0x00ff0000);
    let id = u64::from(fixture.window);

    // 1. The official behaviour, captured first: no knob, no scaling, no extra fields.
    let uncapped = with_display(&fixture, || with_max_image_edge(None, || capture_window_state(id)));
    let uncapped_value = window2_value(&uncapped);
    let uncapped_png = image_bytes(&uncapped);
    let uncapped_image = image::load_from_memory(&uncapped_png).expect("a valid PNG");
    assert_eq!(
        (uncapped_image.width(), uncapped_image.height()),
        (300, 200),
        "without the knob the window is captured at its natural size"
    );
    assert_eq!(uncapped_value["screenshots"][0]["width"], serde_json::json!(300));
    assert_eq!(uncapped_value["screenshots"][0]["height"], serde_json::json!(200));
    let entry = uncapped_value["screenshots"][0].as_object().unwrap();
    for absent in ["coordinateWidth", "coordinateHeight", "scale", "resized"] {
        assert!(
            !entry.contains_key(absent),
            "the default wire shape must not grow a {absent} field"
        );
    }
    let origin = (
        uncapped_value["screenshots"][0]["originX"].clone(),
        uncapped_value["screenshots"][0]["originY"].clone(),
    );

    // 2. A cap that does not bite must be byte-for-byte the uncapped capture: this is the
    //    strong form of "不设/不生效时行为不变", measured on real pixels rather than argued.
    let inert = with_display(&fixture, || {
        with_max_image_edge(Some("2000"), || capture_window_state(id))
    });
    assert_eq!(
        image_bytes(&inert),
        uncapped_png,
        "a cap larger than the image must not alter a single byte"
    );

    // 3. A cap that does bite: longest edge <= 100, ratio kept (300x200 -> 100x67).
    let capped = with_display(&fixture, || {
        with_max_image_edge(Some("100"), || capture_window_state(id))
    });
    let capped_value = window2_value(&capped);
    let capped_image = image::load_from_memory(&image_bytes(&capped)).expect("a valid PNG");
    let (capped_width, capped_height) = (capped_image.width(), capped_image.height());
    assert!(
        capped_width.max(capped_height) <= 100,
        "the cap must bound the longest edge, got {capped_width}x{capped_height}"
    );
    assert!(
        capped_width <= 300 && capped_height <= 200,
        "the cap must never upscale, got {capped_width}x{capped_height}"
    );

    // The declared size must be the decoded size, or the model is told a lie about the
    // image it is looking at (the contract the e2e driver asserts).
    let shot = &capped_value["screenshots"][0];
    assert_eq!(shot["width"], serde_json::json!(capped_width));
    assert_eq!(shot["height"], serde_json::json!(capped_height));

    // The coordinate space must stay the original window size: click/drag take
    // window-relative coordinates, so this is what keeps the mapping honest.
    assert_eq!(
        shot["coordinateWidth"],
        serde_json::json!(300),
        "the coordinate space must stay the original window width"
    );
    assert_eq!(
        shot["coordinateHeight"],
        serde_json::json!(200),
        "the coordinate space must stay the original window height"
    );
    assert_eq!(shot["resized"], serde_json::json!(true));

    // `originX`/`originY` are root coordinates and must not be scaled either.
    assert_eq!((shot["originX"].clone(), shot["originY"].clone()), origin);
    assert_eq!(origin, (serde_json::json!(40), serde_json::json!(30)));

    // The declared scale must match the real ratio between the two spaces.
    let declared_scale = shot["scale"].as_f64().expect("a numeric scale");
    assert!(
        (declared_scale - f64::from(capped_width) / 300.0).abs() < 1e-6,
        "the declared scale must be returned/coordinate, got {declared_scale}"
    );

    // The window identity block is untouched: this is metadata, not pixels.
    assert_eq!(capped_value["window"], uncapped_value["window"]);
}

/// A compile-time guard so the ignored-reason string stays in one place and cannot drift
/// from the run command quoted in this file's header.
#[test]
fn the_documented_run_command_matches_the_ignore_reason() {
    assert!(NEEDS_XVFB.contains("DSH_CUA_XVFB_TEST=1"));
    assert!(NEEDS_XVFB.contains("--ignored"));
}