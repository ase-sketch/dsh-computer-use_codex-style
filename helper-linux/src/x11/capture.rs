//! Window capture over MIT-SHM, with the XComposite path that survives occlusion.
//!
//! Two capture modes exist and they are not equivalent:
//!
//! * **direct** - `ShmGetImage` on the window drawable. Works everywhere, but on an
//!   unredirected (non-composited) window the X server reads the *framebuffer*, so
//!   anything overlapping the window is captured instead of the window.
//! * **composite** - redirect the window off-screen with XComposite, take the
//!   server-named pixmap, and read that. This returns the window's *own* pixels,
//!   so an occluded window is captured correctly.
//!
//! Composite is the mode window2 wants, and it is what the helper tries first. Its
//! limits are measured, not assumed (see `tests/xvfb_window2.rs`), and they are reported
//! in [`WindowCapture::degraded`] rather than hidden:
//!
//! * It needs the Composite extension. Without it the helper reads the window directly
//!   and says so.
//! * If another client already owns the window's redirection — the normal situation when
//!   a compositor such as kwin, mutter or picom is running — the redirect comes back
//!   `BadAccess` and the helper falls back to a direct read, naming the cause. It never
//!   claims the occlusion-proof path it did not take.
//! * **The guarantee is "the window's own pixels, never the overlapping window's", not
//!   "live pixels of a covered window".** Each capture redirects the window afresh, and a
//!   fresh off-screen buffer is initialised to the window's background. So an obscured
//!   window whose client is not painting yields its background — not its last painted
//!   content, which is what this module previously claimed. Content painted *while* the
//!   redirection is in effect *is* captured, even under an opaque cover.
//!
//!   Windows' DWM holds a backing bitmap per window and can do better in both cases;
//!   plain X11 cannot. The difference is stated here, in health, and in the window2
//!   response rather than papered over, because a model that believes it is looking at
//!   live pixels of a covered window would act on a stale image.

use std::io::Cursor;
use std::sync::Mutex;

use anyhow::{anyhow, bail, Result};
use x11rb::connection::Connection as _;
use x11rb::protocol::composite::{ConnectionExt as _, Redirect};
use x11rb::protocol::shm::{self, ConnectionExt as _};
use x11rb::protocol::xproto::{
    ConnectionExt as _, CreateGCAux, Gcontext, ImageFormat, Pixmap, Window,
};
use x11rb::rust_connection::RustConnection;

use super::connection::{with_connection, X11Connection};
use super::window::{self, FrameExtents, WindowGeometry};

/// How a capture was produced, so callers and health can tell the difference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CaptureMethod {
    /// XComposite off-screen redirection plus `NameWindowPixmap`.
    Composite,
    /// `ShmGetImage` straight off the window drawable.
    Direct,
}

impl CaptureMethod {
    pub fn as_str(&self) -> &'static str {
        match self {
            CaptureMethod::Composite => "composite",
            CaptureMethod::Direct => "direct",
        }
    }
}

/// One captured window image plus the facts about how it was obtained.
#[derive(Debug, Clone)]
pub struct WindowCapture {
    pub png: Vec<u8>,
    /// Width of the returned image, i.e. **after** the opt-in max-image-edge cap.
    ///
    /// This is the size the caller must declare to the model, so that the declared size
    /// and the decoded image keep matching. See `coordinate_width` for the space input
    /// coordinates are expressed in.
    pub width: u16,
    /// Height of the returned image, i.e. **after** the opt-in max-image-edge cap.
    pub height: u16,
    /// Width of the captured region in coordinates, i.e. **before** the cap.
    ///
    /// Equal to `width` unless `DSH_COMPUTER_USE_MAX_IMAGE_EDGE` is set. Input is
    /// injected in this space, so a caller that scales the image for display must map
    /// model coordinates back through it or every click lands off by the ratio.
    pub coordinate_width: u16,
    /// Height of the captured region in coordinates, i.e. **before** the cap.
    pub coordinate_height: u16,
    /// Where the captured region starts in root coordinates.
    pub origin_x: i32,
    pub origin_y: i32,
    pub method: CaptureMethod,
    /// Set when the ideal mode was unavailable and a lesser one was used instead.
    pub degraded: Option<String>,
    pub frame_extents: FrameExtents,
}

impl WindowCapture {
    /// Assemble a capture from the encoded image plus the region it came from.
    ///
    /// `encoded` is the size `encode_png` actually produced; the region size is the
    /// coordinate space. When no cap is configured the two are equal, and this
    /// constructor is the only place that decides that — every call site reports the
    /// truth by construction instead of re-deriving it.
    fn from_encoded(
        encoded: (Vec<u8>, u16, u16),
        region: (u16, u16),
        origin: (i32, i32),
        method: CaptureMethod,
        degraded: Option<String>,
        frame_extents: FrameExtents,
    ) -> Self {
        let (png, width, height) = encoded;
        let (coordinate_width, coordinate_height) = region;
        Self {
            png,
            width,
            height,
            coordinate_width,
            coordinate_height,
            origin_x: origin.0,
            origin_y: origin.1,
            method,
            degraded,
            frame_extents,
        }
    }
}

/// A System V shared memory segment, unmapped and removed on drop.
struct ShmSegment {
    address: *mut libc::c_void,
    segment_id: libc::c_int,
    size: usize,
}

// The pointer is only ever handed to the X server for the duration of one request and
// read back on the same thread; no other thread can reach it.
unsafe impl Send for ShmSegment {}

impl ShmSegment {
    fn new(size: usize) -> Result<Self> {
        let segment_id = unsafe {
            libc::shmget(
                libc::IPC_PRIVATE,
                size.max(1),
                libc::IPC_CREAT | 0o600,
            )
        };
        if segment_id < 0 {
            bail!(
                "shmget failed: {}",
                std::io::Error::last_os_error()
            );
        }
        let address = unsafe { libc::shmat(segment_id, std::ptr::null(), 0) };
        if address as isize == -1 {
            unsafe { libc::shmctl(segment_id, libc::IPC_RMID, std::ptr::null_mut()) };
            bail!("shmat failed: {}", std::io::Error::last_os_error());
        }
        // Mark for deletion immediately so the segment disappears when the last
        // mapping goes away, even if this process is killed.
        unsafe { libc::shmctl(segment_id, libc::IPC_RMID, std::ptr::null_mut()) };
        Ok(Self {
            address,
            segment_id,
            size,
        })
    }

    fn bytes(&self) -> &[u8] {
        unsafe { std::slice::from_raw_parts(self.address as *const u8, self.size) }
    }
}

impl Drop for ShmSegment {
    fn drop(&mut self) {
        let _ = self.segment_id;
        unsafe { libc::shmdt(self.address) };
    }
}

/// Removes an XComposite redirection when it goes out of scope.
///
/// This is the RAII half of the redirect: a helper that exits, errors or panics
/// mid-capture must not leave the user's window redirected off-screen, which would
/// make it invisible for as long as nothing composites it.
struct RedirectGuard<'a> {
    raw: &'a RustConnection,
    window: Window,
    armed: bool,
}

impl<'a> RedirectGuard<'a> {
    fn arm(raw: &'a RustConnection, window: Window) -> Result<Self> {
        raw.composite_redirect_window(window, Redirect::AUTOMATIC)
            .map_err(|error| anyhow!("composite_redirect_window could not be sent: {error}"))?
            .check()
            .map_err(|error| {
                anyhow!("composite_redirect_window was refused: {error:?}")
            })?;
        Ok(Self {
            raw,
            window,
            armed: true,
        })
    }
}

impl Drop for RedirectGuard<'_> {
    fn drop(&mut self) {
        if self.armed {
            // Best effort by construction: this runs on the way out, including on the
            // error paths, and there is nowhere left to report a failure to.
            if let Ok(cookie) = self.raw.composite_unredirect_window(self.window, Redirect::AUTOMATIC)
            {
                let _ = cookie.check();
            }
            let _ = self.raw.flush();
            self.armed = false;
        }
    }
}

/// Hold the single capture slot.
///
/// Captures are the one place in this module where a shared *mutable* server-side
/// resource is involved (a redirection), so they are serialized rather than left to
/// interleave with another capture on the same window.
static CAPTURE_LOCK: Mutex<()> = Mutex::new(());

/// Capture a window and encode it as PNG.
///
/// Tries the occlusion-proof Composite path first and falls back to a direct read,
/// recording which happened in [`WindowCapture::degraded`].
pub fn capture_window(id: u64) -> Result<WindowCapture> {
    let _slot = CAPTURE_LOCK
        .lock()
        .map_err(|_| anyhow!("the capture lock was poisoned"))?;
    let window = Window::try_from(id)
        .map_err(|_| anyhow!("window id {id} does not fit in an X11 window id"))?;
    let geometry = window::window_geometry(id)?;
    let frame_extents = window::frame_extents(id).unwrap_or_default();
    with_connection(|connection| {
        capture_on(connection, window, geometry, frame_extents)
    })?
}

fn capture_on(
    connection: &X11Connection,
    window: Window,
    geometry: WindowGeometry,
    frame_extents: FrameExtents,
) -> Result<WindowCapture> {
    if geometry.width == 0 || geometry.height == 0 {
        bail!(
            "window 0x{:x} has an empty client area ({}x{})",
            u32::from(window),
            geometry.width,
            geometry.height
        );
    }
    // x11rb separates "could not send" from "server refused"; either way the mode is
    // unavailable, so both collapse to one boolean here.
    let composite_available = connection
        .inner()
        .composite_query_version(0, 4)
        .ok()
        .map(|cookie| cookie.reply().is_ok())
        .unwrap_or(false);

    let composite = if composite_available {
        capture_composited(connection, window, geometry, frame_extents)
    } else {
        Err(anyhow!(
            "the X server provides no Composite extension, so occluding windows may appear in the image"
        ))
    };
    fall_back_to_direct(
        composite,
        || capture_direct_png(connection, window, geometry),
        geometry,
        frame_extents,
    )
}

/// Prefer the occlusion-proof capture, and describe the shortfall honestly when it fails.
///
/// Split out from the request path so the fallback itself is testable: the branch is
/// reached on a real session whenever another client (a compositor) already owns the
/// window's redirection, which is not reproducible in the headless test session.
fn fall_back_to_direct(
    composite: Result<WindowCapture>,
    direct: impl FnOnce() -> Result<(Vec<u8>, u16, u16)>,
    geometry: WindowGeometry,
    frame_extents: FrameExtents,
) -> Result<WindowCapture> {
    match composite {
        Ok(capture) => Ok(capture),
        Err(error) => {
            let encoded = direct()?;
            Ok(WindowCapture::from_encoded(
                encoded,
                (geometry.width, geometry.height),
                (geometry.x, geometry.y),
                CaptureMethod::Direct,
                Some(format!(
                    "XComposite capture unavailable, fell back to a direct window read \
                     (occluding windows may appear in the image): {error}"
                )),
                frame_extents,
            ))
        }
    }
}

/// Occlusion-proof capture: redirect, name the server pixmap, read it.
fn capture_composited(
    connection: &X11Connection,
    window: Window,
    geometry: WindowGeometry,
    frame_extents: FrameExtents,
) -> Result<WindowCapture> {
    let raw = connection.inner();
    let guard = RedirectGuard::arm(raw, window)?;
    // The redirection must be in effect before the pixmap is named, otherwise the name
    // refers to a window that is still drawing to the screen.
    raw.flush()
        .map_err(|error| anyhow!("flush after redirect failed: {error}"))?;

    // The X server allocates this resource: NameWindowPixmap takes a *Pixmap* argument
    // that it expects to be a fresh, unused XID. Creating the pixmap client-side first
    // makes the server answer BadIDChoice, so no create_pixmap call may appear here.
    let pixmap: Pixmap = raw
        .generate_id()
        .map_err(|error| anyhow!("could not allocate an id for the window pixmap: {error}"))?;
    raw.composite_name_window_pixmap(window, pixmap)
        .map_err(|error| anyhow!("composite_name_window_pixmap could not be sent: {error}"))?
        .check()
        .map_err(|error| anyhow!("composite_name_window_pixmap was refused: {error:?}"))?;
    raw.flush()
        .map_err(|error| anyhow!("flush after naming the window pixmap failed: {error}"))?;

    let encoded = read_drawable_png(connection, pixmap, geometry.width, geometry.height);
    // Free the named pixmap before dropping the redirection; the resource belongs to
    // this client, and leaving it behind would leak one pixmap per capture.
    let freed = raw
        .free_pixmap(pixmap)
        .map_err(|error| anyhow!("free_pixmap could not be sent: {error}"))
        .and_then(|cookie| cookie.check().map_err(|error| anyhow!("{error:?}")));
    drop(guard);
    let encoded = encoded?;
    freed?;

    Ok(WindowCapture::from_encoded(
        encoded,
        (geometry.width, geometry.height),
        (geometry.x, geometry.y),
        CaptureMethod::Composite,
        None,
        frame_extents,
    ))
}

/// Direct capture: read the window drawable as it is shown.
fn capture_direct_png(
    connection: &X11Connection,
    window: Window,
    geometry: WindowGeometry,
) -> Result<(Vec<u8>, u16, u16)> {
    read_drawable_png(connection, window, geometry.width, geometry.height)
}

/// `ShmGetImage` on any drawable and encode the pixels as PNG.
fn read_drawable_png(
    connection: &X11Connection,
    drawable: u32,
    width: u16,
    height: u16,
) -> Result<(Vec<u8>, u16, u16)> {
    let raw = connection.inner();
    let shm_available = connection
        .inner()
        .shm_query_version()
        .ok()
        .map(|cookie| cookie.reply().is_ok())
        .unwrap_or(false);
    if !shm_available {
        return read_drawable_png_slow(connection, drawable, width, height);
    }

    let bytes_per_pixel = connection.bytes_per_pixel();
    let expected = usize::from(width) * usize::from(height) * bytes_per_pixel;
    let segment = ShmSegment::new(expected)?;
    let shmseg = raw
        .generate_id()
        .map_err(|error| anyhow!("could not allocate an id for the shm segment: {error}"))?;
    raw.shm_attach(shmseg, segment.segment_id as u32, false)
        .map_err(|error| anyhow!("shm_attach could not be sent: {error}"))?
        .check()
        .map_err(|error| anyhow!("shm_attach was refused: {error:?}"))?;

    let reply = shm::get_image(
        raw,
        drawable,
        0,
        0,
        width,
        height,
        !0,
        u8::from(ImageFormat::Z_PIXMAP),
        shmseg,
        0,
    )
    .map_err(|error| anyhow!("shm_get_image could not be sent: {error}"))?
    .reply()
    .map_err(|error| anyhow!("shm_get_image was refused: {error:?}"));

    let detached = raw
        .shm_detach(shmseg)
        .map_err(|error| anyhow!("shm_detach could not be sent: {error}"))
        .and_then(|cookie| cookie.check().map_err(|error| anyhow!("{error:?}")));
    let reply = reply?;
    detached?;

    let depth = reply.depth;
    if depth != 24 && depth != 32 {
        bail!("unsupported drawable depth {depth}: only 24-bit and 32-bit visuals can be encoded");
    }
    let pixels = segment.bytes();
    let needed = usize::from(width) * usize::from(height) * bytes_per_pixel;
    if pixels.len() < needed {
        bail!(
            "the shared segment is {} bytes but {needed} are needed",
            pixels.len()
        );
    }
    encode_png(pixels, width, height, bytes_per_pixel)
}

/// Fallback capture for a server without MIT-SHM: plain `GetImage` into the reply.
fn read_drawable_png_slow(
    connection: &X11Connection,
    drawable: u32,
    width: u16,
    height: u16,
) -> Result<(Vec<u8>, u16, u16)> {
    let raw = connection.inner();
    let reply = raw
        .get_image(ImageFormat::Z_PIXMAP, drawable, 0, 0, width, height, !0)
        .map_err(|error| anyhow!("get_image could not be sent: {error}"))?
        .reply()
        .map_err(|error| anyhow!("get_image was refused: {error:?}"))?;
    let bytes_per_pixel = connection.bytes_per_pixel();
    encode_png(&reply.data, width, height, bytes_per_pixel)
}

/// Pack server ZPixmap bytes into PNG, applying the DSH-only max-image-edge cap.
///
/// X11 window pixels carry no meaningful alpha, so every pixel is written opaque; a
/// 32-bit visual would otherwise produce a fully transparent PNG that looks broken in
/// the model's view.
///
/// The cap is applied *before* encoding, so the bytes that travel are the bytes the
/// model reads and the reported size is the real size by construction. With no cap
/// configured (`DSH_COMPUTER_USE_MAX_IMAGE_EDGE` unset or 0) the returned pair is exactly
/// `(width, height)` and the encoded bytes are byte-for-byte what the official helper
/// would have produced.
fn encode_png(
    pixels: &[u8],
    width: u16,
    height: u16,
    bytes_per_pixel: usize,
) -> Result<(Vec<u8>, u16, u16)> {
    let count = usize::from(width) * usize::from(height);
    let mut rgba = Vec::with_capacity(count * 4);
    for index in 0..count {
        let start = index * bytes_per_pixel;
        let end = start + bytes_per_pixel;
        let source = pixels
            .get(start..end)
            .ok_or_else(|| anyhow!("the capture buffer ended early at pixel {index}"))?;
        let mut value = [0u8; 4];
        let take = source.len().min(4);
        value[..take].copy_from_slice(&source[..take]);
        let packed = u32::from_ne_bytes(value);
        rgba.push(((packed >> 16) & 0xff) as u8);
        rgba.push(((packed >> 8) & 0xff) as u8);
        rgba.push((packed & 0xff) as u8);
        rgba.push(0xff);
    }
    let image = image::RgbaImage::from_raw(u32::from(width), u32::from(height), rgba)
        .ok_or_else(|| anyhow!("could not build a {width}x{height} image from the capture"))?;

    let (image, out_width, out_height) = match crate::image_edge::max_image_edge_from_env() {
        Some(max_edge) => match crate::image_edge::scaled_dimensions(
            u32::from(width),
            u32::from(height),
            max_edge,
        ) {
            // Triangle is the deterministic, cheap filter this knob wants: the cap exists to
            // cut tokens on a wire screenshot, and a downward resize by a large factor makes
            // the filter choice invisible to the model.
            Some((target_width, target_height)) => (
                image::imageops::resize(
                    &image,
                    target_width,
                    target_height,
                    image::imageops::FilterType::Triangle,
                ),
                target_width as u16,
                target_height as u16,
            ),
            None => (image, width, height),
        },
        None => (image, width, height),
    };

    let mut out = Cursor::new(Vec::new());
    image
        .write_to(&mut out, image::ImageFormat::Png)
        .map_err(|error| anyhow!("PNG encoding failed: {error}"))?;
    Ok((out.into_inner(), out_width, out_height))
}

/// Capture the whole screen, for the cases window2 asks for screen-scoped pixels.
pub fn capture_root() -> Result<WindowCapture> {
    let _slot = CAPTURE_LOCK
        .lock()
        .map_err(|_| anyhow!("the capture lock was poisoned"))?;
    with_connection(|connection| {
        let raw = connection.inner();
        let (width, height) = connection.screen_size();
        // Keep a GC alive across the read so the root is forced to have its contents
        // realized; some servers hand back stale data for the root without one.
        let gc: Gcontext = raw.generate_id()?;
        let created = match raw.create_gc(gc, connection.root(), &CreateGCAux::new()) {
            Ok(cookie) => cookie.check().map_err(|error| anyhow!("{error:?}")),
            Err(error) => Err(anyhow!("{error}")),
        };
        let encoded = read_drawable_png(connection, connection.root(), width, height);
        if let Ok(cookie) = raw.free_gc(gc) {
            let _ = cookie.check();
        }
        created?;
        Ok(WindowCapture::from_encoded(
            encoded?,
            // The root's region is the whole screen: the cap shrinks the image, while
            // these stay the screen size the input coordinates are expressed in.
            (width, height),
            (0, 0),
            CaptureMethod::Direct,
            None,
            FrameExtents::default(),
        ))
    })?
}

#[cfg(test)]
mod tests {
    use super::*;
    /// The env var is process-global, so every module that sets it shares one lock.
    use crate::image_edge::with_env as with_max_image_edge;

    #[test]
    fn png_encoding_marks_pixels_opaque() {
        // A 2x1 image: one red pixel, one blue pixel, in BGRA order.
        let pixels = [0x00u8, 0x00, 0xff, 0x00, 0xff, 0x00, 0x00, 0x00];
        let (png, width, height) = encode_png(&pixels, 2, 1, 4).unwrap();
        // With no cap configured the reported size is the natural size.
        assert_eq!((width, height), (2, 1));
        assert_eq!(&png[..8], &[0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a]);
        let decoded = image::load_from_memory(&png).unwrap().to_rgba8();
        assert_eq!(decoded.get_pixel(0, 0).0, [0xff, 0x00, 0x00, 0xff]);
        assert_eq!(decoded.get_pixel(1, 0).0, [0x00, 0x00, 0xff, 0xff]);
    }

    #[test]
    fn a_configured_max_image_edge_caps_the_encoded_png_and_reports_the_new_size() {
        with_max_image_edge(Some("4"), || {
            // A 8x4 source: the cap of 4 must halve it, and the reported size must be the
            // encoded one so a caller can never declare a size the image does not have.
            let mut pixels = Vec::new();
            for index in 0..32u8 {
                pixels.extend_from_slice(&[index, index, index, 0xff]);
            }
            let (png, width, height) = encode_png(&pixels, 8, 4, 4).unwrap();
            assert_eq!((width, height), (4, 2));
            let decoded = image::load_from_memory(&png).unwrap().to_rgba8();
            assert_eq!(
                (decoded.width(), decoded.height()),
                (u32::from(width), u32::from(height)),
                "the declared size must be the decoded size"
            );
        });
    }

    #[test]
    fn an_image_within_the_cap_is_encoded_byte_for_byte_as_before() {
        // "不传 env 时行为逐字节不变" in its strongest form: the same pixels encoded with a
        // cap that does not bite must equal the no-cap bytes.
        let mut pixels = Vec::new();
        for index in 0..32u8 {
            pixels.extend_from_slice(&[index, index, index, 0xff]);
        }
        let uncapped = encode_png(&pixels, 8, 4, 4).unwrap();
        let capped_but_inert = with_max_image_edge(Some("8"), || encode_png(&pixels, 8, 4, 4).unwrap());
        assert_eq!(uncapped, capped_but_inert);
    }

    #[test]
    fn a_zero_max_image_edge_is_the_official_behaviour() {
        let mut pixels = Vec::new();
        for index in 0..32u8 {
            pixels.extend_from_slice(&[index, index, index, 0xff]);
        }
        let uncapped = encode_png(&pixels, 8, 4, 4).unwrap();
        let zero = with_max_image_edge(Some("0"), || encode_png(&pixels, 8, 4, 4).unwrap());
        assert_eq!(uncapped, zero, "0 means no cap, exactly like the official helper");
    }

    #[test]
    fn a_truncated_buffer_is_an_error_not_a_partial_image() {
        let pixels = [0x00u8, 0x00, 0xff, 0x00];
        let error = encode_png(&pixels, 4, 1, 4).unwrap_err();
        assert!(error.to_string().contains("ended early"));
        // The 4x1 request cannot be satisfied by a 4-byte buffer, and the failure must not
        // be masked by whatever cap happens to be configured.
        let error = with_max_image_edge(Some("1"), || encode_png(&pixels, 4, 1, 4).unwrap_err());
        assert!(error.to_string().contains("ended early"));
    }

    #[test]
    fn a_failed_composite_capture_falls_back_to_a_direct_read_and_says_why() {
        // This is the path a real session takes when a compositor already owns the
        // window's redirection (a second redirect comes back BadAccess). The server here
        // cannot reproduce that, so the failure is injected: what is under test is that
        // the helper still returns an image, labels it a direct read, and names the cause
        // instead of claiming occlusion-proofness.
        let geometry = WindowGeometry {
            x: 40,
            y: 30,
            width: 2,
            height: 1,
        };
        let pixels = [0x00u8, 0x00, 0xff, 0x00, 0xff, 0x00, 0x00, 0x00];
        let capture = fall_back_to_direct(
            Err(anyhow!("composite_redirect_window was refused: BadAccess")),
            || encode_png(&pixels, 2, 1, 4),
            geometry,
            FrameExtents::default(),
        )
        .expect("the fallback must still produce a capture");

        assert_eq!(capture.method, CaptureMethod::Direct);
        assert_eq!(capture.width, 2);
        assert_eq!(capture.height, 1);
        assert_eq!((capture.coordinate_width, capture.coordinate_height), (2, 1));
        assert_eq!(capture.origin_x, 40);
        let reason = capture.degraded.expect("the shortfall must be reported");
        assert!(reason.contains("XComposite"), "reason was: {reason}");
        assert!(reason.contains("BadAccess"), "reason was: {reason}");
        // The image is real, not a placeholder.
        let decoded = image::load_from_memory(&capture.png).unwrap().to_rgba8();
        assert_eq!(decoded.get_pixel(0, 0).0, [0xff, 0x00, 0x00, 0xff]);
    }

    #[test]
    fn a_successful_composite_capture_is_not_marked_degraded() {
        let geometry = WindowGeometry {
            x: 0,
            y: 0,
            width: 2,
            height: 1,
        };
        let pixels = [0x00u8, 0x00, 0xff, 0x00, 0xff, 0x00, 0x00, 0x00];
        let encoded = encode_png(&pixels, 2, 1, 4).unwrap();
        let capture = fall_back_to_direct(
            Ok(WindowCapture::from_encoded(
                encoded,
                (2, 1),
                (0, 0),
                CaptureMethod::Composite,
                None,
                FrameExtents::default(),
            )),
            || panic!("the direct path must not be used when composite succeeded"),
            geometry,
            FrameExtents::default(),
        )
        .unwrap();
        assert_eq!(capture.method, CaptureMethod::Composite);
        assert!(capture.degraded.is_none());
    }

    #[test]
    fn capture_methods_name_themselves() {
        assert_eq!(CaptureMethod::Composite.as_str(), "composite");
        assert_eq!(CaptureMethod::Direct.as_str(), "direct");
    }

    #[test]
    fn an_empty_client_area_is_refused() {
        let geometry = WindowGeometry {
            x: 0,
            y: 0,
            width: 0,
            height: 0,
        };
        assert!(geometry.width == 0);
    }
}