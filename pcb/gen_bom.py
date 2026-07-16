#!/usr/bin/env python3
"""Generate BOM and CPL (pick-and-place) from <name>.kicad_pcb.

Usage:
    python3 pcb/gen_bom.py [--name PROJECT_NAME]

Outputs (written to pcb/):
    bom.csv / cpl.csv                       — default build (R6=5.6k, presence DNP)
    bom-hi-gain.csv / cpl-hi-gain.csv       — R6=47k, presence DNP
    bom-presence.csv / cpl-presence.csv     — R6=5.6k, presence populated
    bom-hi-gain-presence.csv / ...          — R6=47k, presence populated
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
    p = argparse.ArgumentParser(description="Generate BOM and CPL variants from KiCad PCB file.")
    p.add_argument("--name", default="open-condenser-mic",
                   help="Project name (default: open-condenser-mic)")
    return p.parse_args()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_args = _parse_args()
PCB = os.path.join(_SCRIPT_DIR, f"{_args.name}.kicad_pcb")

# ── Build variants ────────────────────────────────────────────────────────────
# Each variant overrides R6 value/LCSC and controls the presence-peak DNP set.
# The default (no suffix) is the standard build shipped in fabrication-outputs.
VARIANTS = {
    "":                  {"r6_val": "5.6k",  "r6_lcsc": "C25908", "presence": False},
    "-hi-gain":          {"r6_val": "47k",   "r6_lcsc": "C25792", "presence": False},
    "-presence":         {"r6_val": "5.6k",  "r6_lcsc": "C25908", "presence": True},
    "-hi-gain-presence": {"r6_val": "47k",   "r6_lcsc": "C25792", "presence": True},
}

# ── DNP: skip footprint library prefixes (test points, mounting holes) ───────
DNP_LIB_PREFIXES = (
    "TestPoint",
    "MountingHole",
)

# ── LCSC part number lookup ───────────────────────────────────────────────────
# Key: (value_normalised, footprint_id)
# !! Verify all numbers against current LCSC catalog before ordering !!
LCSC = {
    # ICs
    ("OPA1641",   "SOIC-8_3.9x4.9mm_P1.27mm"):   "C2057597",  # TI OPA1641AIDR SOIC-8; C328784 maps to wrong part in JLCPCB
    ("MMBT5551",  "SOT-23"):                       "C2145",     # MMBT5551 NPN 160V hFE≥75 Basic; emitter follower for V_OPA rail
    ("CD40106B",  "SOIC-14_3.9x8.7mm_P1.27mm"):   "C38184",    # TI CD40106BM96; C5993 low stock

    # Diodes
    ("BAT54S",    "SOT-23"):                       "C83935",    # Semtech BAT54S SOT-23; C8541 maps to SS8550 PNP TH in JLCPCB
    ("15V MMSZ15","D_SOD-123"):                    "C27754",    # MMSZ15T1G onsemi 15V zener SOD-123; C460671 maps to wrong part in JLCPCB
    ("68V BZT52C68","D_SOD-123"):                  "C242416",   # MMSZ5266BT1G onsemi 68V 500mW SOD-123; C7427990 has no 3D model in JLCPCB viewer
    ("24V BZT52C24","D_SOD-123"):                  "C173422",   # MDD BZT52C24 24V 500mW SOD-123; zener reference for V_OPA emitter follower

    # Standard resistors (0402)
    ("5.6k",      "R_0402_1005Metric"):            "C25908",    # UNI-ROYAL 0402WGF5601TCE ±1% — R6 default (flat/hi-SPL)
    ("6.2k",      "R_0402_1005Metric"):            "C25915",    # UNI-ROYAL 0402WGF6201TCE ±1%
    ("2.2k",      "R_0402_1005Metric"):            "C25879",
    ("6.8k",      "R_0402_1005Metric"):            "C144738",   # YAGEO AC0402FR-076K8L ±1% 757pcs; C93940 out of stock; C26022 maps to 4.7kΩ 0805 in JLCPCB
    ("47k",       "R_0402_1005Metric"):            "C25792",    # UNI-ROYAL 0402WGF4702TCE ±1% BASIC — R6 hi-gain variant; C25900 maps to 4.7kΩ in JLCPCB
    ("100R",      "R_0402_1005Metric"):            "C25076",
    ("470k",      "R_0402_1005Metric"):            "C137976",   # YAGEO RC0402FR-07470KL ±1%; C25905 maps to 5.1kΩ in JLCPCB

    # Precision resistors (0603) — R1/R2 matched pair
    ("6.8k 0.1%", "R_0603_1608Metric"):            "C2941290",  # ARG03BTC6801 Viking 0.1%

    # High-value resistors (1206)
    ("100M 1206", "R_1206_3216Metric"):            "C5632242",  # FHF06JT-107 PSA 250mW ±5% — R_BIAS1
    ("47M 1206",  "R_1206_3216Metric"):            "C163361",   # RC1206JR-0747ML YAGEO 200V ±5% — R_GBIAS1/2

    # Standard capacitors (0402)
    ("12n 25V X7R",   "C_0402_1005Metric"):        "C113786",   # YAGEO CC0402KRX7R8BB123; X7R fine — no DC bias, mV signal level
    ("100n 25V X7R",  "C_0402_1005Metric"):        "C77014",    # GRM155R71E104KE14D Murata; C307331 out of stock
    ("100n 63V X7R",  "C_0402_1005Metric"):        "C162178",   # GRM155R62A104KE14D muRata 100V X5R
    ("100p C0G",      "C_0402_1005Metric"):        "C445763",   # TDK C1005C0G1H101JT000F 100pF 50V C0G; C1554 maps to 20pF in JLCPCB

    # Standard capacitors (0603/0805/1206)
    ("10u 25V X5R",   "C_0603_1608Metric"):        "C344022",   # GRM188R61E106KA73D muRata
    ("1n 100V C0G",   "C_0402_1005Metric"):        "C694157",   # TDK C1005C0G2A102JT000E 100V C0G — C8 has ~56V DC bias; 1nF gives f=1.6Hz with R_BIAS1
    ("4.7u 50V X7R",  "C_1206_3216Metric"):        "C51205",    # CL31B475KBHNNNE Samsung

    # 100V capacitors
    ("100n 100V X7R", "C_0805_2012Metric"):        "C28233",    # CL21B104KCFNNNE Samsung BASIC — Cp1/2/3
    ("470n 100V X7R", "C_0805_2012Metric"):        "C596323",   # CC0805KKX7R0BB474 YAGEO 81k stock — C9, Cres1

    # SMD electrolytic
    ("10u 25V",       "CP_Elec_4x5.4"):            "C3343",     # Honor Elec RVT1E100M0405 D4x5.4mm 2000hrs — C5/C6

    # Inductor
    ("10mH FNR5040S", "L_Changjiang_FNR5040S"):    "C167995",   # cjiang FNR5040S103MT shielded 5x5mm
}

# ── KiCad → JLCPCB rotation correction ───────────────────────────────────────
ROT_OFFSET = {
    "SOIC-8_3.9x4.9mm_P1.27mm":   0,
    "SOIC-14_3.9x8.7mm_P1.27mm":  270,
    "SOT-89-3":                    0,
    "SOT-23":                      180,
    "D_SOD-123":                   0,
}

ROT_OFFSET_REF = {
    "Z_OSC1": 180,   # JLCPCB model anode on left at 0°; need 180° so cathode→pad1=V_OSC
    "Z_REG1": 180,   # same SOD-123 convention; KiCad 180° → JLCPCB 0° puts cathode at right (pad1=V_BASE_REG)
}


def normalise_fp(fp_id: str) -> str:
    return fp_id.split(":")[-1] if ":" in fp_id else fp_id


def jlcpcb_rotation(ref: str, kicad_deg: float, fp_id: str) -> float:
    fp = normalise_fp(fp_id)
    offset = ROT_OFFSET_REF.get(ref, ROT_OFFSET.get(fp, 0))
    return (-kicad_deg + offset) % 360


def _bom_note(val, lcsc):
    if lcsc:
        return ""
    if any(x in val for x in ["M ", "100V", "mH"]):
        return "LIKELY CUSTOMER-SUPPLIED — verify availability"
    return "LCSC# needed"


def write_variant(board, suffix, r6_val, r6_lcsc, presence):
    """Write bom{suffix}.csv and cpl{suffix}.csv for one build variant."""
    dnp_refs = set() if presence else {"R_PRES1", "C_PRES1"}

    components = []
    dnp_components = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        fp_id = fp.GetFPIDAsString()
        lib_name = fp_id.split(":")[0] if ":" in fp_id else ""

        if lib_name.startswith(DNP_LIB_PREFIXES):
            continue
        if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE:
            continue

        val   = r6_val if ref == "R6" else fp.GetValue()
        fp_nm = normalise_fp(fp_id)
        pos   = fp.GetPosition()
        lcsc  = r6_lcsc if ref == "R6" else LCSC.get((val, fp_nm), "")

        record = {
            "ref":   ref,
            "val":   val,
            "fp":    fp_nm,
            "x":     round(pos.x / 1e6, 4),
            "y":     round(pos.y / 1e6, 4),
            "rot":   jlcpcb_rotation(ref, fp.GetOrientationDegrees(), fp_id),
            "layer": "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom",
            "lcsc":  lcsc,
        }
        if ref in dnp_refs:
            dnp_components.append(record)
        else:
            components.append(record)

    from collections import defaultdict
    groups = defaultdict(list)
    for c in components:
        groups[(c["val"], c["fp"])].append(c)

    dnp_groups = defaultdict(list)
    for c in dnp_components:
        dnp_groups[(c["val"], c["fp"])].append(c)

    bom_out = os.path.join(_SCRIPT_DIR, f"bom{suffix}.csv")
    cpl_out = os.path.join(_SCRIPT_DIR, f"cpl{suffix}.csv")

    with open(bom_out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "Qty", "LCSC Part#", "Note"])
        for (val, fp_nm), items in sorted(groups.items(), key=lambda x: x[0]):
            refs = ",".join(sorted(c["ref"] for c in items))
            lcsc = items[0]["lcsc"]
            w.writerow([val, refs, fp_nm, len(items), lcsc, _bom_note(val, lcsc)])
        if dnp_groups:
            w.writerow([])
            w.writerow(["# DNP (Do Not Populate) — optional presence-peak network"])
            w.writerow(["# Populate if using a flat-response capsule and presence lift is desired"])
            # DNP parts intentionally omitted as data rows — JLCPCB rejects BOM entries
            # that have no corresponding CPL position.

    with open(cpl_out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X(mm)", "Mid Y(mm)", "Layer", "Rotation"])
        for c in sorted(components, key=lambda x: x["ref"]):
            w.writerow([c["ref"], c["x"], c["y"], c["layer"], c["rot"]])

    label = f"[{suffix.lstrip('-') or 'default'}]"
    print(f"  {label:25s}  BOM: {len(groups)} items ({len(components)} parts"
          + (f", {len(dnp_components)} DNP" if dnp_components else "") + ")"
          + f"  CPL: {len(components)} placements")

    missing = [(val, fp, items[0]["lcsc"])
               for (val, fp), items in groups.items() if not items[0]["lcsc"]]
    if missing:
        print(f"    !! {len(missing)} missing LCSC#:")
        for val, fp, _ in missing:
            refs = ",".join(sorted(c["ref"] for c in groups[(val, fp)]))
            print(f"       {refs:20s}  {val:20s}  {fp}")


def main():
    if not os.path.exists(PCB):
        sys.exit(f"PCB not found: {PCB}\nRun gen_pcb.py first.")

    board = pcbnew.LoadBoard(PCB)
    print(f"Generating BOM/CPL variants from {os.path.basename(PCB)}:")
    for suffix, v in VARIANTS.items():
        write_variant(board, suffix, v["r6_val"], v["r6_lcsc"], v["presence"])


if __name__ == "__main__":
    main()
