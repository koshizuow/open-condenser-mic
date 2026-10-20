"""Minimal WAV read/write with numpy only (16/24/32-bit PCM and 32-bit float)."""

import struct
import wave

import numpy as np


def write_wav(path, x, fs):
    """Write mono float array in [-1, 1] as 24-bit PCM."""
    x = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    i = np.round(x * (2 ** 23 - 1)).astype("<i4")
    b = i.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(fs)
        w.writeframes(b)


def read_wav(path, channel=0):
    """Return (fs, float array in [-1, 1]) for one channel."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
            if fmt[0] == 0xFFFE and size >= 26:          # WAVE_FORMAT_EXTENSIBLE
                fmt = (struct.unpack("<H", body[24:26])[0],) + fmt[1:]
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    if fmt is None or raw is None:
        raise ValueError(f"{path}: missing fmt or data chunk")
    code, nch, fs, _, _, bits = fmt
    if code == 3 and bits == 32:
        x = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    elif code == 1 and bits == 16:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 2 ** 15
    elif code == 1 and bits == 24:
        u = np.frombuffer(raw[:len(raw) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        i = u[:, 0].astype(np.int32) | (u[:, 1].astype(np.int32) << 8) | (u[:, 2].astype(np.int8).astype(np.int32) << 16)
        x = i.astype(np.float64) / 2 ** 23
    elif code == 1 and bits == 32:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2 ** 31
    else:
        raise ValueError(f"{path}: unsupported WAV format code {code}, {bits} bit")
    x = x[:len(x) // nch * nch].reshape(-1, nch)
    return fs, x[:, min(channel, nch - 1)].copy()
