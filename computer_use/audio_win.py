"""Windows capture: ffmpeg dshow, then waveIn, then silence WAV."""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import threading
import wave
from ctypes import wintypes
from pathlib import Path

winmm = ctypes.windll.winmm if hasattr(ctypes, "windll") else None


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.POINTER(ctypes.c_ulong)),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.POINTER(ctypes.c_ulong)),
    ]


def write_silence_wav(path: Path, duration_ms: int = 400) -> Path:
    frames = int(16000 * max(duration_ms, 50) / 1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def start_ffmpeg_record(path: Path) -> subprocess.Popen[bytes] | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return subprocess.Popen(
            [ffmpeg, "-y", "-f", "dshow", "-i", "audio=virtual-audio-capturer", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


class WaveInRecorder:
    def __init__(self, path: Path, rate: int = 16000) -> None:
        self.path = path
        self.rate = rate
        self._chunks: list[bytes] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._handle = wintypes.HANDLE()

    def start(self) -> bool:
        if winmm is None:
            return False
        try:
            fmt = WAVEFORMATEX(1, 1, self.rate, self.rate * 2, 2, 16, 0)
            if winmm.waveInOpen(ctypes.byref(self._handle), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0) != 0:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return True
        except OSError:
            return False

    def _run(self) -> None:
        size = self.rate * 2
        buf = ctypes.create_string_buffer(size)
        hdr = WAVEHDR(ctypes.addressof(buf), size, 0, None, 0, 0, None, None)
        winmm.waveInPrepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        winmm.waveInAddBuffer(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        winmm.waveInStart(self._handle)
        while not self._stop.is_set():
            self._stop.wait(0.2)
            if hdr.dwBytesRecorded:
                self._chunks.append(ctypes.string_at(buf, hdr.dwBytesRecorded))
                hdr.dwBytesRecorded = 0
                hdr.dwFlags = 0
                winmm.waveInAddBuffer(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        winmm.waveInStop(self._handle)
        if hdr.dwBytesRecorded:
            self._chunks.append(ctypes.string_at(buf, hdr.dwBytesRecorded))
        winmm.waveInUnprepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        winmm.waveInClose(self._handle)

    def stop(self) -> Path:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        data = b"".join(self._chunks)
        if not data:
            write_silence_wav(self.path)
            return self.path
        with wave.open(str(self.path), "w") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.rate)
            handle.writeframes(data)
        return self.path


def start_recording(path: Path) -> tuple[object, str]:
    proc = start_ffmpeg_record(path)
    if proc is not None:
        return proc, "ffmpeg"
    recorder = WaveInRecorder(path)
    if recorder.start():
        return recorder, "wavein"
    write_silence_wav(path)
    return None, "silence"


def stop_recording(handle: object | None, path: Path) -> Path:
    if handle is None:
        if not path.is_file():
            write_silence_wav(path)
        return path
    if isinstance(handle, WaveInRecorder):
        return handle.stop()
    if isinstance(handle, subprocess.Popen):
        handle.terminate()
        try:
            handle.wait(timeout=3)
        except subprocess.TimeoutExpired:
            handle.kill()
        if not path.is_file() or path.stat().st_size < 44:
            write_silence_wav(path)
        return path
    return path
