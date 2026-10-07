#!/usr/bin/env python3
"""Generate BOM and CPL (pick-and-place) from <name>.kicad_pcb.

Usage:
    python3 pcb/gen_bom.py [--hi-gain] [--presence] [--name PROJECT_NAME]

Flags:
    --hi-gain    Use R6=47k (high-gain variant); default R6=5.6k
    --presence   Populate R_PRES1/C_PRES1 presence-peak network; default DNP

Output suffix is derived from active flags:
    (none)            → bom.csv / cpl.csv
    --hi-gain         → bom-hi-gain.csv / cpl-hi-gain.csv
    --presence        → bom-presence.csv / cpl-presence.csv
    --hi-gain --presence → bom-hi-gain-presence.csv / cpl-hi-gain-presence.csv
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
    p = argparse.ArgumentParser(description="Generate BOM and CPL for one build variant.")
    p.add_argument("--name", default="open-condenser-mic",
                   help="Project name (default: open-condenser-mic)")
    p.add_argument("--hi-gain", action="store_true",
                   help="Use R6=47k instead of 5.6k")
    p.add_argument("--presence", action="store_true",
                   help="Populate R_PRES1/C_PRES1 presence-peak network")
    return p.parse_args()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

R6_DEFAULT = {"val": "5.6k",  "lcsc": "C25908"}
R6_HI_GAIN = {"val": "47k",   "lcsc": "C25792"}

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
    ("2.2k",      "R_0402_1005Metric"):            "C25879",    # R3, R_REG1 (#95; was 1.2k C25867)
    ("6.8k",      "R_0402_1005Metric"):            "C25944",    # UNI-ROYAL 0402WGJ0682TCE ±5% 44k pcs; C144738 ±1% out of stock; C26022 maps to 4.7kΩ 0805 in JLCPCB
    ("47k",       "R_0402_1005Metric"):            "C25792",    # UNI-ROYAL 0402WGF4702TCE ±1% BASIC — R6 hi-gain variant; C25900 maps to 4.7kΩ in JLCPCB
    ("100R",      "R_0402_1005Metric"):            "C25076",
    ("470k",      "R_0402_1005Metric"):            "C137976",   # YAGEO RC0402FR-07470KL ±1%; C25905 maps to 5.1kΩ in JLCPCB

    # Precision resistors (0603) — R1/R2 matched pair
    ("2.2k 0.1%", "R_0603_1608Metric"):            "C861295",   # YAGEO RT0603BRD072K2L thin film ±0.1% 25ppm 75V; Extended (15.7k stock 2026-10-07). #95: was 6.8k 0.1% (C2941290)

    # High-value bias resistors (0805) — R_GBIAS1, R_BIAS1 (#109)
    ("200M 0805",     "R_0805_2012Metric"):          "C3934221",  # Vishay CRCW0805200MJPEAHR ±5% thick film, 150V operating (datasheet 20022; the 0603 size is only 75V); 12.6k stock 2026-10-07. Was 100M 1206 (C5632242, C59781). Drop-in for lower noise: CRCW0805470MJPEAHR (470M, 150V)

    # Standard capacitors (0402)
    ("12n 25V X7R",   "C_0402_1005Metric"):        "C113786",   # YAGEO CC0402KRX7R8BB123; X7R fine — no DC bias, mV signal level
    ("100n 25V X7R",  "C_0402_1005Metric"):        "C77014",    # GRM155R71E104KE14D Murata; C307331 out of stock — C_U3 (15V rail)
    ("100n 50V X7R",  "C_0402_1005Metric"):        "C131394",   # YAGEO CC0402KRX7R9BB104 ±10% 50V — C2/C3 on V_OPA (up to 24.6V), same margin reasoning as C5/C6 in #54 (#100). Not C60474: that is the 16V CC0402KRX7R7BB104
    ("100n 63V X7R",  "C_0402_1005Metric"):        "C162178",   # GRM155R62A104KE14D muRata 100V X5R
    ("100p C0G",      "C_0402_1005Metric"):        "C445763",   # TDK C1005C0G1H101JT000F 100pF 50V C0G; C1554 maps to 20pF in JLCPCB

    # Standard capacitors (0603/0805/1206)
    ("10u 25V X5R",   "C_0603_1608Metric"):        "C344022",   # GRM188R61E106KA73D muRata
    ("1n 100V C0G 1206", "C_1206_3216Metric"):    "C513661",   # YAGEO CC1206JRNPO0BN102 NP0 ±5% 100V — C8; 1206 for creepage across ~55V DC (#96; was 0402 C694157)
    ("4.7u 50V X7R",  "C_1206_3216Metric"):        "C51205",    # CL31B475KBHNNNE Samsung

    # HV capacitors (#61: pump caps upgraded to 200V to reduce derating from 68% to 34%)
    ("100n 200V X7R", "C_0805_2012Metric"):        "C5448894",  # CCTC TCC0805X7R104K201FT ±10% 28k stock — Cp1/2/3
    # WCCA note (Cres1/C9): 470nF 200V X7R is 1206-only; layout constraints (transformer
    # cutout clearance + board edge) prevent 1206 upgrade without rerouting. Steady-state DC
    # bias (67-68V on 100V-rated cap) causes ~30% capacitance derating — no functional impact
    # on HV filter (fc still well below 1Hz). Accepted risk for DIY use; revisit at next rev.
    ("470n 100V X7R", "C_0805_2012Metric"):        "C596323",   # CC0805KKX7R0BB474 YAGEO — C9, Cres1

    # SMD electrolytic
    ("10u 35V",       "CP_Elec_4x5.4"):            "C86602",    # Honor Elec RVT1V100M0405 D4x5.4mm 2000hrs 35V — C5/C6; replaces C3343 25V (C6 V_OPA margin too small)

    # HV filter resistor (0603)
    ("1M 75V 0603",   "R_0603_1608Metric"):         "C22935",    # UNI-ROYAL 0603WAF1004T5E 1MΩ 75V ±1% Basic

    # DZ1 series resistor (#67)
    ("680R",          "R_0603_1608Metric"):         "C23228",    # UNI-ROYAL 0603WAF6800T5E 680Ω 75V ±1% 100mW Basic — R_DZ1; confirmed via JLCPCB parts search (2.39M stock)

    # TVS1/TVS2 ESD protection (#60, #93)
    ("SMF58CA", "D_SOD-123F"): "C1851338",   # Littelfuse SMF58CA, bidirectional, VRWM 58V, VBR 64.4-71.2V, Vc 93.6V, IR 1uA, SOD-123FL; Extended (1040 stock 2026-10-07). Standoff must be >= 52V: these sit on the phantom-fed XLR lines. Replaces ESD9B5.0ST5G (C111566, 5V standoff) which clamped phantom to ~7V
}

# ── KiCad → JLCPCB rotation correction ───────────────────────────────────────
ROT_OFFSET = {
    "SOIC-8_3.9x4.9mm_P1.27mm":   0,
    "SOIC-14_3.9x8.7mm_P1.27mm":  270,
    "SOT-89-3":                    0,
    "SOT-23":                      180,
    "D_SOD-123":                   0,
    "D_SOD-123F":                  0,
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
    _args = _parse_args()
    PCB = os.path.join(_SCRIPT_DIR, f"{_args.name}.kicad_pcb")

    if not os.path.exists(PCB):
        sys.exit(f"PCB not found: {PCB}\nRun gen_pcb.py first.")

    r6 = R6_HI_GAIN if _args.hi_gain else R6_DEFAULT
    parts = []
    if _args.hi_gain:
        parts.append("hi-gain")
    if _args.presence:
        parts.append("presence")
    suffix = ("-" + "-".join(parts)) if parts else ""

    board = pcbnew.LoadBoard(PCB)
    print(f"Generating BOM/CPL from {os.path.basename(PCB)}:")
    write_variant(board, suffix, r6["val"], r6["lcsc"], _args.presence)


if __name__ == "__main__":
    main()
