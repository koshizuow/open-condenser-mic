#!/usr/bin/env python3
"""Generate simulation plots for README. Run from project root or sim/ directory.

Requirements: ngspice, numpy, matplotlib
Output: ../img/hv_startup.png, ../img/noise_spectrum.png, ../img/freq_response.png
"""

import subprocess
import os
import re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(os.path.dirname(SIM_DIR), "img")
os.makedirs(IMG_DIR, exist_ok=True)

STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "#f8f8f8",
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
}
plt.rcParams.update(STYLE)

C1, C2 = "#1f77b4", "#ff7f0e"


def inject_control(sp_path, control_block):
    with open(sp_path) as f:
        content = f.read()
    return content.replace(".end", control_block + "\n.end")


def run_ngspice_stdout(sp_path_or_content, name, is_content=False):
    """Run ngspice in batch mode, return stdout."""
    if is_content:
        tmp_path = os.path.join(SIM_DIR, f"_tmp_{name}.sp")
        with open(tmp_path, "w") as f:
            f.write(sp_path_or_content)
        path = tmp_path
    else:
        path = sp_path_or_content
        tmp_path = None
    try:
        result = subprocess.run(
            ["ngspice", "-b", path],
            cwd=SIM_DIR,
            capture_output=True,
            text=True,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
    return result.stdout + result.stderr


def parse_table_stdout(output, first_table_only=False):
    """Parse ngspice .print table from stdout: Index freq col1 col2 ...

    If first_table_only=True, stop after the first table ends (useful when
    ngspice splits a .print with many variables into multiple sub-tables).
    """
    rows = []
    in_table = False
    for line in output.splitlines():
        line = line.strip()
        if re.match(r"^Index\s+frequency", line):
            if first_table_only and rows:
                break  # second table starts — stop
            in_table = True
            continue
        if in_table and re.match(r"^-{10}", line):
            continue
        if in_table and re.match(r"^\d+\s", line):
            parts = line.split()
            try:
                rows.append([float(x) for x in parts[1:]])  # skip Index
            except ValueError:
                pass
    return np.array(rows) if rows else np.zeros((0, 2))


def parse_measure(output):
    """Extract .measure results from ngspice stdout into a dict."""
    results = {}
    for line in output.splitlines():
        m = re.match(r"^\s*(\w+)\s*=\s*([0-9eE+\-.]+)", line, re.IGNORECASE)
        if m:
            try:
                results[m.group(1).lower()] = float(m.group(2))
            except ValueError:
                pass
    return results


def parse_wrdata(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                vals = [float(x) for x in line.split()]
                if len(vals) >= 2:
                    rows.append(vals)
            except ValueError:
                continue
    return np.array(rows)


# ─── 1. HV STARTUP (boost_dickson.sp) ────────────────────────────────────────

def plot_hv_startup():
    # boost_dickson.sp has its own .control block (LC vs RC comparison) that writes
    # _hv_tran.dat with v(vboost)/v(hvfilt) from the LC run (shows startup transient).
    # wrdata format: time v(vboost) time v(hvfilt)  (scale repeated per vector)
    data_path = os.path.join(SIM_DIR, "_hv_tran.dat")
    output = run_ngspice_stdout(os.path.join(SIM_DIR, "boost_dickson.sp"), "hv")
    measures = parse_measure(output)

    d = parse_wrdata(data_path)
    if os.path.exists(data_path):
        os.remove(data_path)

    # wrdata repeats scale col for each vector: [time, vboost, time, hvfilt]
    t_ms   = d[:, 0] * 1e3
    vboost = d[:, 1]
    hvfilt = d[:, 3]

    hv_avg    = measures.get("hv_avg_rc", hvfilt.mean())
    hv_max    = measures.get("hv_max_rc", float("nan"))
    hv_min    = measures.get("hv_min_rc", float("nan"))
    hv_ripple = hv_max - hv_min

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.suptitle("HV Rail — Dickson Charge Pump Startup", fontsize=12, fontweight="bold")

    ax.plot(t_ms, vboost, color=C1, lw=1.2, label="V_BOOST (raw)")
    ax.plot(t_ms, hvfilt, color=C2, lw=1.2, label="HV_FILT (RC, 1 MΩ + 470 nF)")
    ax.axhline(68, color="#aaaaaa", lw=0.8, ls="--", label="68 V target")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Voltage (V)")
    ax.legend(fontsize=9)
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 80)

    annotation = f"Steady-state: {hv_avg:.2f} V\nHV_FILT ripple: {hv_ripple*1e6:.1f} µV p-p"
    ax.text(0.98, 0.05, annotation, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc"))

    fig.tight_layout()
    out = os.path.join(IMG_DIR, "hv_startup.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Written: {out}")


# ─── 2. NOISE SPECTRUM (amp_noise_opa1641.sp) ────────────────────────────────

def plot_noise_spectrum():
    sp_path = os.path.join(SIM_DIR, "amp_noise_opa1641.sp")
    output = run_ngspice_stdout(sp_path, "noise")

    d = parse_table_stdout(output)
    # columns: frequency, inoise_spectrum, onoise_spectrum
    freq = d[:, 0]
    inoise_nv = d[:, 1] * 1e9  # V/rtHz → nV/rtHz

    # Audio band only (20 Hz – 20 kHz)
    mask = (freq >= 20) & (freq <= 20000)
    f_audio = freq[mask]
    n_audio = inoise_nv[mask]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.loglog(f_audio, n_audio, color=C1, lw=1.5, label="Input-referred noise (20 Hz – 20 kHz)")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Input-referred noise (nV/√Hz)")
    ax.set_title("Input-Referred Noise Spectrum", fontweight="bold")
    ax.legend(fontsize=9)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x/1000)}k" if x >= 1000 else f"{int(x)}"
    ))

    fig.tight_layout()
    out = os.path.join(IMG_DIR, "noise_spectrum.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Written: {out}")


# Presence peak: Rs (6.2k) + C (12nF) in series, parallel with R4 (gain resistor = R3 in schematic)
# Corner f = 1/(2π × 6.2k × 12n) ≈ 2.1 kHz; HF boost = +2.6 dB (R3‖Rs = 2.2k‖6.2k = 1.61k)
PRESENCE_PEAK_LINES = """\
* Presence-peak network (R_PRES1 + C_PRES1, in series, parallel with R4)
R_PRES1  NET_VBIAS  RS_MID  6.2k
C_PRES1  RS_MID  PIN2_NODE  12n
"""


# ─── 3. AC FREQUENCY RESPONSE (amp_ac.sp) ────────────────────────────────────

def _run_ac(content_modifier=None):
    """Run amp_ac.sp, optionally modifying SPICE content, return (freq, db_norm)."""
    data_path = os.path.join(SIM_DIR, "_ac.dat")
    ctrl = f"""
.control
run
let xlr_db = db(v(xlr_diff))
wrdata {data_path} xlr_db
.endc"""
    with open(os.path.join(SIM_DIR, "amp_ac.sp")) as f:
        base = f.read()
    if content_modifier:
        base = content_modifier(base)
    content = base.replace(".end", ctrl + "\n.end")
    run_ngspice_stdout(content, "ac", is_content=True)
    d = parse_wrdata(data_path)
    if os.path.exists(data_path):
        os.remove(data_path)
    freq = d[:, 0]
    db_xlr = d[:, 1]
    ref_idx = np.argmin(np.abs(freq - 1000))
    return freq, db_xlr - db_xlr[ref_idx]


def plot_freq_response():
    freq_base, db_base = _run_ac()
    freq_peak, db_peak = _run_ac(
        lambda s: s.replace(".end", PRESENCE_PEAK_LINES + ".end")
    )

    mask = (freq_base >= 20) & (freq_base <= 200000)

    fig, ax = plt.subplots(figsize=(7, 4))
    mask_peak = (freq_peak >= 20) & (freq_peak <= 200000)
    ax.semilogx(freq_base[mask], db_base[mask], color=C1, lw=1.5,
                label="Baseline (R_PRES1/C_PRES1 DNP)")
    ax.semilogx(freq_peak[mask_peak], db_peak[mask_peak], color=C2, lw=1.5,
                label="With presence peak (Rs=6.2k, C=12nF, f_c≈2.1 kHz)")
    ax.axhline(-3, color="#aaaaaa", lw=0.8, ls="--", label="−3 dB")
    ax.axvline(20000, color="#cccccc", lw=0.8, ls=":", label="20 kHz")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Gain (dB, normalized to 1 kHz)")
    ax.set_title("AC Frequency Response — XLR Differential Output", fontweight="bold")
    ax.legend(fontsize=9)
    ax.set_xlim(20, 200000)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(
        lambda x, _: f"{int(x/1000)}k" if x >= 1000 else f"{int(x)}"
    ))

    fig.tight_layout()
    out = os.path.join(IMG_DIR, "freq_response.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Written: {out}")


if __name__ == "__main__":
    print("Running simulations and generating plots...")
    plot_hv_startup()
    plot_noise_spectrum()
    plot_freq_response()
    print("Done. Images written to img/")
