//! WASAPI loopback matching official helper `src/audio.rs`.
//!
//! Default render endpoint, shared-mode loopback with AUTOCONVERTPCM to 24 kHz
//! stereo 16-bit PCM. `max_duration_ms` caps both the capture deadline and the
//! PCM buffer (`duration_ms * 96` bytes).

use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use windows::Win32::Foundation::RPC_E_CHANGED_MODE;
use windows::Win32::Media::Audio::{
    eConsole, eRender, IAudioCaptureClient, IAudioClient, IMMDeviceEnumerator, MMDeviceEnumerator,
    AUDCLNT_BUFFERFLAGS_SILENT, AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
    AUDCLNT_STREAMFLAGS_LOOPBACK, AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY, WAVEFORMATEX,
    WAVE_FORMAT_PCM,
};
use windows::Win32::System::Com::{CoCreateInstance, CoInitializeEx, CLSCTX_ALL, COINIT_MULTITHREADED};

use crate::protocol::Error;

const SAMPLE_RATE: u32 = 24_000;
const CHANNELS: u16 = 2;
const BITS: u16 = 16;
const BLOCK_ALIGN: u16 = CHANNELS * BITS / 8;
const BYTE_RATE: u32 = SAMPLE_RATE * BLOCK_ALIGN as u32;
const BYTES_PER_MS: u64 = BYTE_RATE as u64 / 1000;
const BUFFER_HNS: i64 = 1_000_000;
const STREAM_FLAGS: u32 =
    AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;
const ALREADY_ACTIVE: &str = "computer audio recording is already active";
const NOT_ACTIVE: &str = "computer audio recording is not active";
pub const NOT_ENABLED: &str = "computer audio recording is not enabled";
const TOO_LARGE: &str = "captured computer audio is too large";

// APS-14: the remaining official src/audio.rs strings (strings_all.txt
// 18165/18199/18307/18313/18314), verbatim, so a future packet-error path reports the
// official text instead of inventing one.
pub const PACKET_NO_DATA: &str = "computer audio packet has no data";
pub const PACKET_SIZE_CHANGED: &str = "computer audio packet size changed while reading";
pub const READ_PACKET: &str = "read computer audio packet";
pub const READ_PACKET_SIZE: &str = "read computer audio packet size";
pub const RELEASE_PACKET: &str = "release computer audio packet";
pub const STOPPED_BEFORE_STARTED: &str = "computer audio recording stopped before it started";
pub const CALLER_STOPPED: &str = "computer audio recording caller stopped";
pub const WAV_CONTAINER_MAGIC: &str = "RIFF WAVE fmt data";

pub fn enabled() -> bool {
    std::env::var("SKY_ENABLE_AUDIO").ok().as_deref() == Some("1")
}

pub fn require_enabled() -> Result<(), Error> {
    if enabled() {
        Ok(())
    } else {
        Err(Error::desktop(NOT_ENABLED))
    }
}

struct Session {
    stop: Arc<AtomicBool>,
    thread: JoinHandle<Result<PathBuf, String>>,
}

static SESSION: Mutex<Option<Session>> = Mutex::new(None);

pub fn start(max_duration_ms: u64) -> Result<(), Error> {
    require_enabled()?;
    let mut slot = SESSION.lock().map_err(|_| Error::other("state lock"))?;
    if slot.is_some() {
        return Err(Error::desktop(ALREADY_ACTIVE));
    }
    let path = audio_path().map_err(|e| Error::desktop(e.to_string()))?;
    let stop = Arc::new(AtomicBool::new(false));
    let (ready_tx, ready_rx) = mpsc::sync_channel(1);
    let thread_stop = Arc::clone(&stop);
    let thread = thread::spawn(move || {
        match record_loop(path, max_duration_ms, thread_stop, ready_tx) {
            Ok(path) => Ok(path),
            Err(err) => Err(err.to_string()),
        }
    });
    match ready_rx.recv_timeout(Duration::from_secs(8)) {
        Ok(Ok(())) => {
            *slot = Some(Session { stop, thread });
            Ok(())
        }
        Ok(Err(err)) => {
            let _ = thread.join();
            Err(Error::desktop(err))
        }
        Err(_) => {
            stop.store(true, Ordering::SeqCst);
            let _ = thread.join();
            Err(Error::desktop("start computer audio capture"))
        }
    }
}

pub fn stop() -> Result<Value, Error> {
    require_enabled()?;
    let session = SESSION
        .lock()
        .map_err(|_| Error::other("state lock"))?
        .take()
        .ok_or_else(|| Error::desktop(NOT_ACTIVE))?;
    session.stop.store(true, Ordering::SeqCst);
    let path = session
        .thread
        .join()
        .unwrap_or_else(|_| Err("computer audio recording thread panicked".into()))
        .map_err(Error::desktop)?;
    let bytes = fs::read(&path).map_err(|_| Error::desktop("write captured computer audio"))?;
    if bytes.len() as u64 > max_pcm_bytes(300_000) + 44 {
        return Err(Error::desktop(TOO_LARGE));
    }
    let filepath = path
        .to_str()
        .ok_or_else(|| Error::desktop("convert computer audio filepath"))?
        .to_string();
    Ok(json!({
        "filepath": filepath,
        "data_url": data_url(&bytes),
    }))
}

pub fn abort() {
    if let Ok(mut slot) = SESSION.lock() {
        if let Some(session) = slot.take() {
            session.stop.store(true, Ordering::SeqCst);
            let _ = session.thread.join();
        }
    }
}

fn max_pcm_bytes(max_duration_ms: u64) -> u64 {
    max_duration_ms.saturating_mul(BYTES_PER_MS)
}

fn audio_path() -> Result<PathBuf> {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .context("system time is before the Unix epoch")?
        .as_millis();
    let mut path = std::env::temp_dir();
    path.push(format!(
        "dsh-computer-use-audio-{}-{stamp}.wav",
        std::process::id()
    ));
    Ok(path)
}

fn data_url(bytes: &[u8]) -> String {
    use base64::Engine;
    format!(
        "data:audio/wav;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(bytes)
    )
}

fn record_loop(
    path: PathBuf,
    max_duration_ms: u64,
    stop: Arc<AtomicBool>,
    ready: mpsc::SyncSender<Result<(), String>>,
) -> Result<PathBuf> {
    let result = (|| {
        let hr = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
        if hr.is_err() && hr != RPC_E_CHANGED_MODE {
            bail!("initialize computer audio capture");
        }
        let enumerator: IMMDeviceEnumerator =
            unsafe { CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL) }
                .context("create audio device enumerator")?;
        let device = unsafe { enumerator.GetDefaultAudioEndpoint(eRender, eConsole) }
            .context("get default audio output")?;
        let client: IAudioClient = unsafe { device.Activate::<IAudioClient>(CLSCTX_ALL, None) }
            .context("activate default audio output")?;
        let format = WAVEFORMATEX {
            wFormatTag: WAVE_FORMAT_PCM as u16,
            nChannels: CHANNELS,
            nSamplesPerSec: SAMPLE_RATE,
            nAvgBytesPerSec: BYTE_RATE,
            nBlockAlign: BLOCK_ALIGN,
            wBitsPerSample: BITS,
            cbSize: 0,
        };
        unsafe {
            client.Initialize(
                AUDCLNT_SHAREMODE_SHARED,
                STREAM_FLAGS,
                BUFFER_HNS,
                0,
                &format as *const WAVEFORMATEX,
                None,
            )
        }
        .context("initialize computer audio capture")?;
        let capture: IAudioCaptureClient = unsafe { client.GetService::<IAudioCaptureClient>() }
            .context("open computer audio capture stream")?;
        unsafe { client.Start() }.context("start computer audio capture")?;
        let _ = ready.send(Ok(()));
        let deadline = Instant::now() + Duration::from_millis(max_duration_ms);
        let max_bytes = max_pcm_bytes(max_duration_ms) as usize;
        let mut pcm = Vec::with_capacity(max_bytes.min(96_000));
        while !stop.load(Ordering::SeqCst) && Instant::now() < deadline {
            if crate::interrupt::stopped() {
                break;
            }
            let mut data = std::ptr::null_mut();
            let mut frames = 0u32;
            let mut flags = 0u32;
            let got = unsafe { capture.GetBuffer(&mut data, &mut frames, &mut flags, None, None) };
            match got {
                Ok(()) if frames > 0 => {
                    let nbytes = frames as usize * BLOCK_ALIGN as usize;
                    if pcm.len() + nbytes > max_bytes {
                        unsafe {
                            let _ = capture.ReleaseBuffer(frames);
                        }
                        bail!("{TOO_LARGE}");
                    }
                    if flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0 {
                        pcm.resize(pcm.len() + nbytes, 0);
                    } else if !data.is_null() {
                        pcm.extend_from_slice(unsafe { std::slice::from_raw_parts(data, nbytes) });
                    }
                    unsafe { capture.ReleaseBuffer(frames) }
                        .context("release computer audio packets")?;
                }
                _ => {
                    if frames > 0 {
                        let _ = unsafe { capture.ReleaseBuffer(frames) };
                    }
                    thread::sleep(Duration::from_millis(5));
                }
            }
        }
        let _ = unsafe { client.Stop() };
        write_wav(&path, &pcm).context("write captured computer audio")?;
        Ok(path)
    })();
    if let Err(err) = &result {
        let _ = ready.send(Err(err.to_string()));
    }
    result
}

/// The RIFF/WAVE container the official helper writes: a 44-byte canonical header
/// followed by raw 24 kHz stereo 16-bit PCM.
fn wav_bytes(pcm: &[u8]) -> Vec<u8> {
    let data_len = pcm.len() as u32;
    let mut out = Vec::with_capacity(44 + pcm.len());
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(36 + data_len).to_le_bytes());
    out.extend_from_slice(b"WAVE");
    out.extend_from_slice(b"fmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&CHANNELS.to_le_bytes());
    out.extend_from_slice(&SAMPLE_RATE.to_le_bytes());
    out.extend_from_slice(&BYTE_RATE.to_le_bytes());
    out.extend_from_slice(&BLOCK_ALIGN.to_le_bytes());
    out.extend_from_slice(&BITS.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&data_len.to_le_bytes());
    out.extend_from_slice(pcm);
    out
}

fn write_wav(path: &PathBuf, pcm: &[u8]) -> Result<()> {
    fs::write(path, wav_bytes(pcm))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disabled_without_env() {
        std::env::remove_var("SKY_ENABLE_AUDIO");
        assert!(!enabled());
        let err = require_enabled().unwrap_err();
        assert_eq!(err.message, NOT_ENABLED);
        assert_eq!(NOT_ENABLED, "computer audio recording is not enabled");
    }

    // APS-14: the official src/audio.rs strings, byte for byte
    // (strings_all.txt 18165/18199/18307/18313/18314).
    #[test]
    fn missing_official_audio_strings_are_verbatim() {
        let table = [
            (PACKET_NO_DATA, "computer audio packet has no data"),
            (
                PACKET_SIZE_CHANGED,
                "computer audio packet size changed while reading",
            ),
            (READ_PACKET, "read computer audio packet"),
            (READ_PACKET_SIZE, "read computer audio packet size"),
            (RELEASE_PACKET, "release computer audio packet"),
            (
                STOPPED_BEFORE_STARTED,
                "computer audio recording stopped before it started",
            ),
            (CALLER_STOPPED, "computer audio recording caller stopped"),
            (WAV_CONTAINER_MAGIC, "RIFF WAVE fmt data"),
        ];
        for (ours, official) in table {
            assert_eq!(ours, official);
        }
    }

    /// APS-14: the WAV container is canonical and self-describing; a decoder keys off
    /// these bytes, so drift in any header field is a real regression.
    #[test]
    fn wav_header_is_the_official_24khz_stereo_pcm_container() {
        let pcm = vec![0u8; 8];
        let wav = wav_bytes(&pcm);
        assert_eq!(wav.len(), 44 + pcm.len());
        assert_eq!(&wav[0..4], b"RIFF");
        assert_eq!(u32::from_le_bytes(wav[4..8].try_into().unwrap()), 36 + 8);
        assert_eq!(&wav[8..12], b"WAVE");
        assert_eq!(&wav[12..16], b"fmt ");
        assert_eq!(u32::from_le_bytes(wav[16..20].try_into().unwrap()), 16);
        assert_eq!(u16::from_le_bytes(wav[20..22].try_into().unwrap()), 1);
        assert_eq!(u16::from_le_bytes(wav[22..24].try_into().unwrap()), CHANNELS);
        assert_eq!(u32::from_le_bytes(wav[24..28].try_into().unwrap()), SAMPLE_RATE);
        assert_eq!(u32::from_le_bytes(wav[28..32].try_into().unwrap()), BYTE_RATE);
        assert_eq!(u16::from_le_bytes(wav[32..34].try_into().unwrap()), BLOCK_ALIGN);
        assert_eq!(u16::from_le_bytes(wav[34..36].try_into().unwrap()), BITS);
        assert_eq!(&wav[36..40], b"data");
        assert_eq!(u32::from_le_bytes(wav[40..44].try_into().unwrap()), 8);
        assert_eq!(SAMPLE_RATE, 24_000);
        assert_eq!(CHANNELS, 2);
        assert_eq!(BITS, 16);
        assert_eq!(BYTE_RATE, 96_000);
        assert_eq!(BLOCK_ALIGN, 4);
    }
}
