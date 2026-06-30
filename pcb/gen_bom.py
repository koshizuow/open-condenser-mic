#!/usr/bin/env python3
"""Generate BOM and CPL (pick-and-place) from <name>.kicad_pcb.

Usage:
    python3 pcb/gen_bom.py [--name PROJECT_NAME]

Outputs:
    pcb/bom.csv  — grouped BOM (Designator, Qty, Value, Footprint, LCSC#)
    pcb/cpl.csv  — CPL for SMT assembly (Designator, Mid X, Mid Y, Layer, Rotation)
"""

import argparse
import csv
import os
import sys

try:
    import pcbnew
except ImportError:
    sys.exit("pcbnew not found — run inside KiCad Python or with KiCad's Python")

def _parse_args():
    p = argparse.ArgumentParser(description="Generate BOM and CPL from KiCad PCB file.")
    p.add_argument("--name", default="open-condenser-mic", help="Project name (default: open-condenser-mic)")
    return p.parse_args()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_args = _parse_args()
PCB = os.path.join(_SCRIPT_DIR, f"{_args.name}.kicad_pcb")
BOM_OUT = os.path.join(_SCRIPT_DIR, "bom.csv")
CPL_OUT = os.path.join(_SCRIPT_DIR, "cpl.csv")

# ── DNP: hand-solder or no component ─────────────────────────────────────────
# Matched by reference OR by footprint library prefix (more robust — fix_ref
# changes GetReference() so original ref strings like "TP1.1" are gone).
DNP_REFS = set()  # all SMD parts now; C5/C6 moved to SMD

# Skip any footprint whose library name starts with one of these prefixes
DNP_LIB_PREFIXES = (
    "TestPoint",       # bare THT solder pads (J2, J3, TP1, TS1)
    "MountingHole",    # board and transformer mounting holes
)

# ── LCSC part number lookup ───────────────────────────────────────────────────
# Key: (value_normalised, footprint_id)
# Leave blank ("") if unknown / needs manual lookup.
# !! Verify all numbers against current LCSC catalog before ordering !!
LCSC = {
    # ICs
    ("OPA1641",   "SOIC-8_3.9x4.9mm_P1.27mm"):   "C2057597",  # TI OPA1641AIDR SOIC-8; C328784 maps to wrong part in JLCPCB
    ("L78L24",    "SOT-89-3"):                     "C130141",   # ST L78L24ACUTR; C112410 unavailable
    ("CD40106B",  "SOIC-14_3.9x8.7mm_P1.27mm"):   "C38184",    # TI CD40106BM96; C5993 low stock

    # Diodes
    ("BAT54S",    "SOT-23"):                       "C83935",    # Semtech BAT54S SOT-23; C8541 maps to SS8550 PNP TH in JLCPCB
    ("15V MMSZ15","D_SOD-123"):                    "C27754",    # MMSZ15T1G onsemi 15V zener SOD-123; C460671 maps to wrong part in JLCPCB
    ("68V BZT52C68","D_SOD-123"):                  "C242416",   # MMSZ5266BT1G onsemi 68V 500mW SOD-123; C7427990 has no 3D model in JLCPCB viewer

    # Standard resistors (0402)
    ("2.2k",      "R_0402_1005Metric"):            "C25879",
    ("6.8k",      "R_0402_1005Metric"):            "C144738",   # YAGEO AC0402FR-076K8L ±1% 757pcs; C93940 out of stock; C26022 maps to 4.7kΩ 0805 in JLCPCB
    ("47k",       "R_0402_1005Metric"):            "C25792",    # UNI-ROYAL 0402WGF4702TCE ±1% BASIC; C25900 maps to 4.7kΩ in JLCPCB
    ("100R",      "R_0402_1005Metric"):            "C25076",
    ("130k",      "R_0402_1005Metric"):            "C93946",    # YAGEO RC0402FR-07130KL ±1%; C25812 unavailable
    ("470k",      "R_0402_1005Metric"):            "C137976",   # YAGEO RC0402FR-07470KL ±1%; C25905 maps to 5.1kΩ in JLCPCB

    # Precision resistors (0603) — R1/R2 matched pair
    ("6.8k 0.1%", "R_0603_1608Metric"):            "C2941290",  # ARG03BTC6801 Viking 0.1%

    # High-value resistors (1206)
    ("100M 1206", "R_1206_3216Metric"):            "C5632242",  # FHF06JT-107 PSA 250mW ±5% — R_BIAS1
    ("47M 1206",  "R_1206_3216Metric"):            "C163361",   # RC1206JR-0747ML YAGEO 200V ±5% — R_GBIAS1/2

    # Standard capacitors (0402)
    ("100n 25V X7R",  "C_0402_1005Metric"):        "C77014",    # GRM155R71E104KE14D Murata; C307331 out of stock
    ("100n 63V X7R",  "C_0402_1005Metric"):        "C162178",   # GRM155R62A104KE14D muRata 100V X5R
    ("100p C0G",      "C_0402_1005Metric"):        "C445763",   # TDK C1005C0G1H101JT000F 100pF 50V C0G; C1554 maps to 20pF in JLCPCB

    # Standard capacitors (0603/0805/1206)
    ("10u 25V X5R",   "C_0603_1608Metric"):        "C344022",   # GRM188R61E106KA73D muRata
    ("10n X7R",       "C_0805_2012Metric"):        "C1710",     # CL21B103KBANNNC Samsung (was C0G)
    ("4.7u 50V X7R",  "C_1206_3216Metric"):        "C51205",    # CL31B475KBHNNNE Samsung

    # 100V capacitors
    ("100n 100V X7R", "C_0805_2012Metric"):        "C28233",    # CL21B104KCFNNNE Samsung BASIC — Cp1/2/3
    ("470n 100V X7R", "C_0805_2012Metric"):        "C596323",    # CC0805KKX7R0BB474 YAGEO 81k stock — C9, Cres1

    # SMD electrolytic
    ("10u 25V",       "CP_Elec_4x5.4"):             "C3343",    # Honor Elec RVT1E100M0405 D4x5.4mm 2000hrs — C5/C6

    # Inductor
    ("10mH FNR5040S", "L_Changjiang_FNR5040S"):     "C167995",  # cjiang FNR5040S103MT shielded 5x5mm
}

# ── KiCad → JLCPCB rotation correction ───────────────────────────────────────
# KiCad CCW positive; JLCPCB CW positive → negate.
# Some footprints need an additional offset; add here if placement is wrong.
# Format: footprint_id -> extra_offset_deg (applied AFTER negation)
ROT_OFFSET = {
    "SOIC-8_3.9x4.9mm_P1.27mm":   0,    # JLCPCB model pin1 at top-left (same as KiCad); no offset needed
    "SOIC-14_3.9x8.7mm_P1.27mm":  270,  # JLCPCB model horizontal, pin1 at lower-left; need portrait + pin1 top-left
    "SOT-89-3":                    0,    # U2 — not yet verified in viewer
    "SOT-23":                      180,  # JLCPCB model pin1 at bottom-right; KiCad pad1 at top-left
    "D_SOD-123":                   0,    # DZ1 correct at 0 (KiCad 90° → JLCPCB 270° puts cathode at bottom=VBOOST)
}

# Per-reference overrides (take priority over ROT_OFFSET footprint table)
ROT_OFFSET_REF = {
    "Z_OSC1": 180,  # JLCPCB model anode(+) on left; need 180° so anode→pad2=GND, cathode→pad1=V_OSC
}


def normalise_fp(fp_id: str) -> str:
    """Strip library prefix, keep only footprint name."""
    return fp_id.split(":")[-1] if ":" in fp_id else fp_id


def jlcpcb_rotation(ref: str, kicad_deg: float, fp_id: str) -> float:
    fp = normalise_fp(fp_id)
    offset = ROT_OFFSET_REF.get(ref, ROT_OFFSET.get(fp, 0))
    return (-kicad_deg + offset) % 360


def main():
    if not os.path.exists(PCB):
        sys.exit(f"PCB not found: {PCB}\nRun gen_pcb.py first.")

    board = pcbnew.LoadBoard(PCB)
    fps = list(board.GetFootprints())

    # Collect all non-DNP SMT footprints
    components = []
    for fp in fps:
        ref = fp.GetReference()
        fp_id = fp.GetFPIDAsString()
        lib_name = fp_id.split(":")[0] if ":" in fp_id else ""

        if ref in DNP_REFS:
            continue
        if lib_name.startswith(DNP_LIB_PREFIXES):
            continue
        if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE:
            # THT not in DNP set — warn and skip
            print(f"  [SKIP THT] {ref}")
            continue

        val   = fp.GetValue()
        fp_nm = normalise_fp(fp_id)
        pos   = fp.GetPosition()
        x_mm  = pos.x / 1e6
        y_mm  = pos.y / 1e6
        rot   = fp.GetOrientationDegrees()
        layer = "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom"

        lcsc_key = (val, fp_nm)
        lcsc = LCSC.get(lcsc_key, "")

        components.append({
            "ref":    ref,
            "val":    val,
            "fp":     fp_nm,
            "x":      round(x_mm, 4),
            "y":      round(y_mm, 4),
            "rot":    jlcpcb_rotation(ref, rot, fp_id),
            "layer":  layer,
            "lcsc":   lcsc,
        })

    # ── BOM: group by (value, footprint) ─────────────────────────────────────
    from collections import defaultdict
    groups = defaultdict(list)
    for c in components:
        groups[(c["val"], c["fp"])].append(c)

    with open(BOM_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "Qty", "LCSC Part#", "Note"])
        for (val, fp_nm), items in sorted(groups.items(), key=lambda x: x[0]):
            refs  = ",".join(sorted(c["ref"] for c in items))
            lcsc  = items[0]["lcsc"]
            note  = ""
            if not lcsc:
                if any(x in val for x in ["M ", "100V", "mH"]):
                    note = "LIKELY CUSTOMER-SUPPLIED — verify availability"
                else:
                    note = "LCSC# needed"
            w.writerow([val, refs, fp_nm, len(items), lcsc, note])

    print(f"BOM written: {BOM_OUT}  ({len(groups)} line items, {len(components)} parts)")

    # ── CPL ──────────────────────────────────────────────────────────────────
    with open(CPL_OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X(mm)", "Mid Y(mm)", "Layer", "Rotation"])
        for c in sorted(components, key=lambda x: x["ref"]):
            w.writerow([c["ref"], c["x"], c["y"], c["layer"], c["rot"]])

    print(f"CPL written: {CPL_OUT}  ({len(components)} placements)")

    # ── Flag missing LCSC numbers ─────────────────────────────────────────────
    missing = [(val, fp, items[0]["lcsc"])
               for (val, fp), items in groups.items() if not items[0]["lcsc"]]
    if missing:
        print(f"\n{'─'*60}")
        print(f"  {len(missing)} line items without LCSC# (fill in LCSC dict):")
        for val, fp, _ in missing:
            refs = ",".join(sorted(c["ref"] for c in groups[(val, fp)]))
            print(f"    {refs:25s}  {val:20s}  {fp}")


if __name__ == "__main__":
    main()
