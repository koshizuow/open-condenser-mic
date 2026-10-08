#!/usr/bin/env python3
"""Analyse the recordings from docs/measurement.md.

    python3 tools/measure/analyze.py \\
        --sweep-ref tools/measure/signals/sweep_-46dBFS.wav --sweep-rec rec_sweep.wav \\
        --v-source 0.412 --v-xlr 0.455 \\
        --tone-rec rec_tone_small.wav --noise-rec rec_noise.wav \\
        [--iface-noise-rec rec_iface_noise.wav] [--rload 4000] [--cdummy 56e-12] [--plot out.png]

Every group of inputs is optional; the report covers whatever is given:

  sweep-ref + sweep-rec       frequency response, LF corner, fitted transformer inductance
  v-source + v-xlr            gain at the 400 Hz calibration tone (multimeter AC volts, rms)
  tone-rec + noise-rec        self-noise, A-weighted and as a density (needs v-xlr too)

    python3 tools/measure/analyze.py --self-test

Needs numpy only (matplotlib for --plot).
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pcb"))
from wavio import read_wav            # noqa: E402
from gen_params import PARAMS         # noqa: E402

TONE_HZ = 400.0
SMALL_TONE_DB = -40.0        # cal_tone -60 dBFS relative to cal_tone -20 dBFS
CAPSULE_V_PER_PA = 13.07e-3  # vendor sheet, see working notes; only used to express results in SPL

# Transformer and output parts not in gen_params (sim/models/passives.lib, gen_schematic.py)
RP, RS = 521.0, 42.0         # winding DC resistance, measured
R7, R_RFI = 100.0, 100.0
N = 3.0                      # step-down ratio
C_IN = 7e-12                 # OPA1641 input capacitance, approx.


def val(s):
    """Parse a SPICE value string from gen_params ('200Meg', '4.7u', '2.2k')."""
    s = str(s)
    for suf, m in (("Meg", 1e6), ("G", 1e9), ("k", 1e3), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if s.endswith(suf):
            return float(s[:-len(suf)]) * m
    return float(s)


def par(a, b):
    return a * b / (a + b)


def model(f, lp, r6=None, cdummy=56e-12, rload=4000.0, c7=None):
    """Complex transfer function, dummy-capacitor source voltage -> voltage across the preamp input."""
    w = 2j * np.pi * np.asarray(f, dtype=float)
    rg, rb = val(PARAMS["R_GBIAS"]), val(PARAMS["R_BIAS1"])
    c8 = val(PARAMS["C8"])
    c7 = c7 or val(PARAMS["C_DC"])
    gain = 1 + (r6 or val(PARAMS["R6_default"])) / val(PARAMS["R3"])
    r12 = 2 * val(PARAMS["R_PH_TAP"])
    # input network
    zb = par(rb, 1 / (w * C_IN))
    zl = par(rg, 1 / (w * c8) + zb)
    v_in = zl / (zl + 1 / (w * cdummy)) * zb / (zb + 1 / (w * c8))
    # output network
    z_out = par(r12, 2 * R_RFI + rload)
    z2 = RS + z_out
    zm = par(w * lp, N * N * z2)
    v_p = zm / (R7 + 1 / (w * c7) + RP + zm)
    v_load = v_p / N * z_out / z2 * rload / (2 * R_RFI + rload)
    return v_in * gain * v_load


def a_weight(f):
    f2 = np.asarray(f, dtype=float) ** 2
    ra = (12194.0 ** 2 * f2 * f2) / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194.0 ** 2))
    return ra * 10 ** (2.0 / 20)


def align(ref, rec):
    """Return rec trimmed to start where ref starts (FFT cross-correlation)."""
    n = 1 << int(np.ceil(np.log2(len(ref) + len(rec))))
    c = np.fft.irfft(np.fft.rfft(rec, n) * np.conj(np.fft.rfft(ref, n)), n)
    lag = int(np.argmax(np.abs(c)))
    if lag > n // 2:
        lag -= n
    out = np.zeros(len(ref))
    src = rec[max(lag, 0):max(lag, 0) + len(ref)] if lag >= 0 else np.concatenate([np.zeros(-lag), rec])[:len(ref)]
    out[:len(src)] = src
    return out, lag


def transfer(ref, rec, fs, fmin=5.0, fmax=20000.0, per_octave=12):
    """|H| = |rec/ref| on a log frequency grid, power-averaged per band. Returns (f, dB)."""
    y, lag = align(ref, rec)
    X, Y = np.fft.rfft(ref), np.fft.rfft(y)
    f = np.fft.rfftfreq(len(ref), 1 / fs)
    edges = fmin * 2 ** (np.arange(0, int(np.log2(fmax / fmin) * per_octave) + 2) / per_octave - 0.5 / per_octave)
    fc, db = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (f >= lo) & (f < hi)
        if m.sum() == 0:
            continue
        px, py = np.sum(np.abs(X[m]) ** 2), np.sum(np.abs(Y[m]) ** 2)
        if px <= 0:
            continue
        fc.append(np.sqrt(lo * hi))
        db.append(10 * np.log10(max(py, 1e-30) / px))
    return np.array(fc), np.array(db), lag


def at(f, y, fx):
    return float(np.interp(np.log(fx), np.log(f), y))


def corner(f, db, ref_hz=1000.0, drop=3.0):
    """Highest frequency below ref_hz where the response is `drop` dB under the 1 kHz level."""
    target = at(f, db, ref_hz) - drop
    below = np.where((f < ref_hz) & (db < target))[0]
    if len(below) == 0:
        return None
    i = below[-1]
    if i + 1 >= len(f):
        return float(f[i])
    t = (target - db[i]) / (db[i + 1] - db[i])
    return float(f[i] * (f[i + 1] / f[i]) ** t)


def fit_lp(f, db, **kw):
    """Least-squares fit of the driven-winding inductance over 20-800 Hz, normalised at 1 kHz."""
    m = (f >= 20) & (f <= 800)
    meas = db[m] - at(f, db, 1000.0)
    best = (None, 1e99)
    for lp in np.logspace(-1, 2, 601):
        h = 20 * np.log10(np.abs(model(np.append(f[m], 1000.0), lp, **kw)))
        err = float(np.sqrt(np.mean((h[:-1] - h[-1] - meas) ** 2)))
        if err < best[1]:
            best = (float(lp), err)
    return best


def band_rms(x, fs, weight=None, fmin=20.0, fmax=20000.0):
    """RMS of x in [fmin, fmax], optionally weighted by weight(f). Returns (rms, f, density)."""
    n = 1 << 15
    hop = n // 2
    w = np.hanning(n)
    segs = [x[i:i + n] * w for i in range(0, len(x) - n + 1, hop)]
    if not segs:
        raise ValueError("recording too short for noise analysis (need at least 1 s)")
    p = np.mean([np.abs(np.fft.rfft(s)) ** 2 for s in segs], axis=0)
    f = np.fft.rfftfreq(n, 1 / fs)
    psd = p / (fs * np.sum(w ** 2)) * 2          # one-sided, units^2/Hz
    m = (f >= fmin) & (f <= fmax)
    wt = weight(f[m]) ** 2 if weight else 1.0
    return float(np.sqrt(np.sum(psd[m] * wt) * (f[1] - f[0]))), f, np.sqrt(psd)


def tone_rms(x, fs, hz=TONE_HZ):
    """RMS of the component at hz (narrow band around it)."""
    n = len(x) - len(x) % fs
    x = x[:n] * np.hanning(n)
    X = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(n, 1 / fs)
    m = (f > hz - 5) & (f < hz + 5)
    return float(np.sqrt(np.sum(X[m] ** 2)) / (np.sum(np.hanning(n)) / 2) / np.sqrt(2) / np.sqrt(1.5))


def report(a):
    lines, out = [], {}

    def say(s=""):
        lines.append(s)

    fr = None
    kw = dict(cdummy=a.cdummy, rload=a.rload, r6=val(PARAMS["R6_hi_gain"]) if a.hi_gain else None)
    if a.sweep_ref and a.sweep_rec:
        fs, ref = read_wav(a.sweep_ref)
        fs2, rec = read_wav(a.sweep_rec, a.channel)
        if fs != fs2:
            raise SystemExit(f"sample rates differ: {fs} vs {fs2}. Record at {fs} Hz.")
        f, db, lag = transfer(ref, rec, fs)
        if a.loopback_rec:
            _, lb = read_wav(a.loopback_rec, a.channel)
            _, dbl, _ = transfer(ref, lb, fs)
            db = db - (dbl - at(f, dbl, 1000.0))
        fr = (f, db)
        rel = lambda fx: at(f, db, fx) - at(f, db, 1000.0)   # noqa: E731
        fc = corner(f, db)
        lp, err = fit_lp(f, db, **kw)
        out.update(fc=fc, lp=lp, fit_err=err)
        say("FREQUENCY RESPONSE (relative to 1 kHz)")
        say("  " + "  ".join(f"{fx:g} Hz {rel(fx):+.1f} dB" for fx in (20, 30, 50, 100, 200, 500, 5000, 10000, 15000)))
        say(f"  -3 dB low-frequency corner: {fc:.0f} Hz" if fc else "  -3 dB low-frequency corner: below the measured range")
        say(f"  fitted driven-winding inductance Lp: {lp:.2g} H   (rms fit error {err:.2f} dB over 20-800 Hz)")
        if err > 1.5:
            say("  NOTE fit error is large: the model does not describe this response well. Check levels,")
            say("       the load value (--rload) and that the low-level sweep was used.")
        say(f"  model in the repo uses Lp = 0.5 H, which predicts a corner near 150 Hz")
        if a.plot:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.semilogx(f, db - at(f, db, 1000.0), label="measured", lw=2)
            for l_, st in ((0.5, ":"), (lp, "--")):
                h = 20 * np.log10(np.abs(model(f, l_, **kw)))
                ax.semilogx(f, h - at(f, h, 1000.0), st, label=f"model, Lp = {l_:.2g} H")
            ax.set(xlim=(5, 20000), ylim=(-30, 6), xlabel="Frequency (Hz)", ylabel="dB re 1 kHz",
                   title="Electrical response through the dummy capsule")
            ax.grid(True, which="both", alpha=0.3)
            ax.legend()
            fig.tight_layout()
            fig.savefig(a.plot, dpi=130)
            say(f"  plot written to {a.plot}")
        say()

    gain_1k = None
    if a.v_source and a.v_xlr:
        g400 = a.v_xlr / a.v_source
        corr = (at(*fr, 1000.0) - at(*fr, TONE_HZ)) if fr else 0.0
        gain_1k = g400 * 10 ** (corr / 20)
        sens = 20 * np.log10(CAPSULE_V_PER_PA * gain_1k)
        exp = 20 * np.log10(abs(model(1000.0, out.get("lp", 4.5), **kw)))
        out.update(gain_db=20 * np.log10(gain_1k), sens=sens)
        say("GAIN")
        say(f"  at {TONE_HZ:g} Hz: {20 * np.log10(g400):+.2f} dB ({a.v_xlr:g} V / {a.v_source:g} V)")
        say(f"  at 1 kHz:  {20 * np.log10(gain_1k):+.2f} dB" + ("" if fr else "   (no sweep given: assumed equal to 400 Hz)"))
        say(f"  model expects {exp:+.2f} dB into {a.rload:g} ohm; difference {20 * np.log10(gain_1k) - exp:+.2f} dB")
        say(f"  equivalent sensitivity with a {CAPSULE_V_PER_PA * 1e3:.1f} mV/Pa capsule: {sens:.1f} dBV/Pa")
        say()

    if a.noise_rec:
        if not (a.tone_rec and a.v_xlr):
            raise SystemExit("--noise-rec needs --tone-rec and --v-xlr for calibration")
        fs, tr = read_wav(a.tone_rec, a.channel)
        fs2, nr = read_wav(a.noise_rec, a.channel)
        v_small = a.v_xlr * 10 ** (SMALL_TONE_DB / 20)
        v_per_fs = v_small / tone_rms(tr, fs)
        g = gain_1k or abs(model(1000.0, out.get("lp", 4.5), **kw))
        out_a, f, dens = band_rms(nr, fs2, a_weight)
        out_a *= v_per_fs
        in_a = out_a / g
        spl = 20 * np.log10(in_a / CAPSULE_V_PER_PA) + 94
        d = lambda fx: float(np.interp(fx, f, dens)) * v_per_fs / g * 1e9   # noqa: E731
        out.update(noise_dba=spl, n1k=d(1000.0), n10k=d(10000.0))
        say("SELF-NOISE (dummy capacitor in place of the capsule, housing closed)")
        say(f"  output, A-weighted 20 Hz-20 kHz: {out_a * 1e6:.2f} uV  ({20 * np.log10(out_a / 0.775):.1f} dBu)")
        say(f"  input-referred, A-weighted:      {in_a * 1e6:.2f} uV  = {spl:.1f} dB(A) SPL equivalent")
        say(f"  input-referred density: {d(1000.0):.1f} nV/rtHz at 1 kHz, {d(10000.0):.1f} nV/rtHz at 10 kHz")
        say("  simulation (200M bias):  18.4 dB(A), 39.2 nV/rtHz at 1 kHz, 9.1 nV/rtHz at 10 kHz")
        if not gain_1k:
            say("  NOTE no measured gain given: referred to input with the model gain")
        if a.iface_noise_rec:
            _, ir = read_wav(a.iface_noise_rec, a.channel)
            ia, _, _ = band_rms(ir, fs2, a_weight)
            margin = 20 * np.log10(out_a / (ia * v_per_fs))
            out.update(iface_margin=margin)
            say(f"  interface alone at the same gain: {ia * v_per_fs * 1e6:.2f} uV A-weighted, {margin:.1f} dB below the mic")
            if margin < 10:
                say("  NOTE less than 10 dB of margin: the interface noise is inflating the result. Raise the preamp gain.")
        say()

    if not lines:
        raise SystemExit("nothing to do: give --sweep-ref/--sweep-rec, --v-source/--v-xlr or --noise-rec (see --help)")
    print("\n".join(lines).rstrip())
    return out


def self_test():
    """Synthesise recordings from the model and check the analysis recovers the inputs."""
    import tempfile
    from gen_signals import sweep, tone, FS
    from wavio import write_wav
    rng = np.random.default_rng(1)
    lp_true, rload = 4.5, 4000.0
    tmp = tempfile.mkdtemp()
    ref = sweep(-46)
    f = np.fft.rfftfreq(len(ref), 1 / FS)
    h = np.zeros(len(f), dtype=complex)
    h[1:] = model(f[1:], lp_true, rload=rload)
    rec = np.fft.irfft(np.fft.rfft(ref) * h, len(ref))
    rec = np.concatenate([np.zeros(17777), rec, np.zeros(5000)]) + rng.normal(0, 2e-7, len(rec) + 22777)
    write_wav(os.path.join(tmp, "ref.wav"), ref, FS)
    write_wav(os.path.join(tmp, "rec.wav"), rec, FS)
    # calibration: interface gain such that 1 V at XLR = 0.5 FS at "low gain", x100 at "high gain"
    g1k = abs(model(1000.0, lp_true, rload=rload))
    g400 = abs(model(400.0, lp_true, rload=rload))
    v_source = 0.40
    v_xlr = v_source * g400
    hi = 0.5 * 100
    write_wav(os.path.join(tmp, "tone.wav"), tone(-60) / 10 ** (-60 / 20) * np.sqrt(2) * v_xlr * 10 ** (SMALL_TONE_DB / 20) * hi, FS)
    # noise: white at the input, 30 nV/rtHz, through the model gain at 1 kHz (flat), 20 s
    dens_in = 30e-9
    n = rng.normal(0, dens_in * np.sqrt(FS / 2), 20 * FS) * g1k * hi
    write_wav(os.path.join(tmp, "noise.wav"), n, FS)
    fw = np.linspace(20, 20000, 200000)
    exp_in_a = dens_in * np.sqrt(np.trapz(a_weight(fw) ** 2, fw))
    exp_spl = 20 * np.log10(exp_in_a / CAPSULE_V_PER_PA) + 94

    a = argparse.Namespace(sweep_ref=os.path.join(tmp, "ref.wav"), sweep_rec=os.path.join(tmp, "rec.wav"),
                           loopback_rec=None, v_source=v_source, v_xlr=v_xlr, tone_rec=os.path.join(tmp, "tone.wav"),
                           noise_rec=os.path.join(tmp, "noise.wav"), iface_noise_rec=None, rload=rload,
                           cdummy=56e-12, hi_gain=False, channel=0, plot=None)
    out = report(a)
    checks = [
        ("fitted Lp", out["lp"], lp_true, 0.07 * lp_true),
        ("gain at 1 kHz (dB)", out["gain_db"], 20 * np.log10(g1k), 0.2),
        ("noise dB(A)", out["noise_dba"], exp_spl, 0.5),
        ("noise density at 1 kHz (nV)", out["n1k"], dens_in * 1e9, 1.5),
    ]
    print()
    ok = True
    for name, got, want, tol in checks:
        good = abs(got - want) <= tol
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} self-test {name}: got {got:.3f}, expected {want:.3f} (tolerance {tol:.2g})")
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sweep-ref", help="the sweep WAV that was played")
    p.add_argument("--sweep-rec", help="recording of the mic output during the sweep")
    p.add_argument("--loopback-rec", help="optional: the same sweep recorded through the interface alone")
    p.add_argument("--v-source", type=float, help="multimeter AC volts at the injection point during cal_tone -20 dBFS")
    p.add_argument("--v-xlr", type=float, help="multimeter AC volts between XLR pins 2 and 3 during the same tone")
    p.add_argument("--tone-rec", help="recording of cal_tone -60 dBFS at the preamp gain used for the noise recording")
    p.add_argument("--noise-rec", help="recording of the mic with the dummy capacitor returned to BP, housing closed")
    p.add_argument("--iface-noise-rec", help="optional: recording at the same gain with the input terminated")
    p.add_argument("--rload", type=float, default=4000.0, help="preamp input impedance in ohm (default 4000)")
    p.add_argument("--cdummy", type=float, default=56e-12, help="dummy capacitor in farad (default 56e-12)")
    p.add_argument("--hi-gain", action="store_true", help="board has R6 = 47k")
    p.add_argument("--channel", type=int, default=0, help="channel index in the recordings (default 0)")
    p.add_argument("--plot", help="write a frequency response plot to this PNG")
    p.add_argument("--self-test", action="store_true", help="run the built-in check on synthetic data")
    a = p.parse_args()
    if a.self_test:
        self_test()
    report(a)


if __name__ == "__main__":
    main()
