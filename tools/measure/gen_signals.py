#!/usr/bin/env python3
"""Generate the test signals for the hardware characterisation in docs/measurement.md.

Writes 48 kHz mono 24-bit WAV files into tools/measure/signals/ (or --out):

    cal_tone_400Hz_-20dBFS.wav   reference tone, measured with a multimeter
    cal_tone_400Hz_-60dBFS.wav   same tone 40 dB lower, for the high-gain noise calibration
    sweep_-46dBFS.wav            log sweep 5 Hz - 22 kHz, low level (linear response)
    sweep_-26dBFS.wav            same sweep, +20 dB (optional, transformer saturation)

Use --hi-gain for a board built with R6 = 47k: all levels drop by 16 dB so the
op-amp does not clip.

    python3 tools/measure/gen_signals.py [--hi-gain] [--out DIR]
"""

import argparse
import os

import numpy as np

from wavio import write_wav

FS = 48000
TONE_HZ = 400.0
SWEEP_F0, SWEEP_F1, SWEEP_SEC = 5.0, 22000.0, 30.0
PAD_SEC = 2.0


def tone(level_dbfs, seconds=30.0):
    t = np.arange(int(seconds * FS)) / FS
    x = np.sin(2 * np.pi * TONE_HZ * t) * 10 ** (level_dbfs / 20)
    return fade(x)


def sweep(level_dbfs):
    """Exponential sine sweep with silence before and after."""
    n = int(SWEEP_SEC * FS)
    t = np.arange(n) / FS
    k = np.log(SWEEP_F1 / SWEEP_F0)
    phase = 2 * np.pi * SWEEP_F0 * SWEEP_SEC / k * (np.exp(t / SWEEP_SEC * k) - 1)
    x = fade(np.sin(phase) * 10 ** (level_dbfs / 20), 0.05)
    pad = np.zeros(int(PAD_SEC * FS))
    return np.concatenate([pad, x, pad])


def fade(x, seconds=0.02):
    n = int(seconds * FS)
    w = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
    x = x.copy()
    x[:n] *= w
    x[-n:] *= w[::-1]
    return x


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--hi-gain", action="store_true", help="board has R6 = 47k: lower all levels by 16 dB")
    p.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals"))
    a = p.parse_args()
    off = -16 if a.hi_gain else 0
    os.makedirs(a.out, exist_ok=True)
    files = {
        f"cal_tone_400Hz_{-20 + off}dBFS.wav": tone(-20 + off),
        f"cal_tone_400Hz_{-60 + off}dBFS.wav": tone(-60 + off),
        f"sweep_{-46 + off}dBFS.wav": sweep(-46 + off),
        f"sweep_{-26 + off}dBFS.wav": sweep(-26 + off),
    }
    for name, x in files.items():
        write_wav(os.path.join(a.out, name), x, FS)
        print(f"wrote {os.path.join(a.out, name)}  ({len(x) / FS:.0f} s)")


if __name__ == "__main__":
    main()
