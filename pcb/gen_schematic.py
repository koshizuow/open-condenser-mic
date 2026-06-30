#!/usr/bin/env python3
"""
Generate <name>.kicad_sch  (KiCad 7 S-expression format)

Strategy: every component is placed on a grid; every pin gets a short wire
stub and a local net label.  The schematic is electrically complete and can be
imported into KiCad for visual clean-up if desired.

Usage:
    python pcb/gen_schematic.py [--name PROJECT_NAME]
"""
import argparse, uuid, re, os, sys

SYM_PATH = "/usr/share/kicad/symbols"

def _parse_args():
    p = argparse.ArgumentParser(description="Generate KiCad schematic file.")
    p.add_argument("--name", default="open-condenser-mic", help="Project name (default: open-condenser-mic)")
    return p.parse_args()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_args = _parse_args()
OUT = os.path.join(_SCRIPT_DIR, f"{_args.name}.kicad_sch")
PROJECT = _args.name


# ── UUID helpers ──────────────────────────────────────────────────────────────
_uuid_counter = 0
def new_uuid():
    global _uuid_counter
    _uuid_counter += 1
    return f"{_uuid_counter:08x}-0000-0000-0000-000000000000"

ROOT_UUID = new_uuid()

# Centering offset for A3 (420×297mm) page.
# Circuit spans roughly x=20..255, y=15..175 → center at (137, 95).
# A3 center at (210, 148.5) → shift = (210-137, 148.5-95) ≈ (76.20, 55.88)
OX, OY = 76.20, 55.88


# ── Symbol extraction from .kicad_sym library files ───────────────────────────
def extract_sym(lib_file, name):
    """Return the top-level (symbol "name" ...) block from a .kicad_sym file."""
    with open(lib_file) as f:
        txt = f.read()
    target = f'  (symbol "{name}"'
    idx = txt.find(target)
    if idx == -1:
        raise ValueError(f'Symbol "{name}" not found in {lib_file}')
    depth = 0
    for i in range(idx, len(txt)):
        if txt[i] == '(':  depth += 1
        elif txt[i] == ')':
            depth -= 1
            if depth == 0:
                return txt[idx:i+1]
    raise ValueError(f'Unbalanced parens for "{name}"')


# ── Embedded symbol definitions we need ───────────────────────────────────────
LIBS = {
    "Device:R":           (f"{SYM_PATH}/Device.kicad_sym",                "R"),
    "Device:C":           (f"{SYM_PATH}/Device.kicad_sym",                "C"),
    "Device:C_Polarized": (f"{SYM_PATH}/Device.kicad_sym",                "C_Polarized"),
    "Device:L":           (f"{SYM_PATH}/Device.kicad_sym",                "L"),
    "Device:D_Zener":     (f"{SYM_PATH}/Device.kicad_sym",                "D_Zener"),
    "Amplifier_Operational:OPA1641": (f"{SYM_PATH}/Amplifier_Operational.kicad_sym", "OPA1641"),
    "Regulator_Linear:L78L24_SOT89": (f"{SYM_PATH}/Regulator_Linear.kicad_sym",      "MC78L05_SOT89"),
    "4xxx:40106":         (f"{SYM_PATH}/4xxx.kicad_sym",                  "40106"),
    "Diode:BAT54S":       (f"{SYM_PATH}/Diode.kicad_sym",                 "BAT54S"),
    "Connector_Generic:Conn_01x02": (f"{SYM_PATH}/Connector_Generic.kicad_sym", "Conn_01x02"),
    "Connector_Generic:Conn_01x03": (f"{SYM_PATH}/Connector_Generic.kicad_sym", "Conn_01x03"),
    "power:GND":          (f"{SYM_PATH}/power.kicad_sym",                 "GND"),
    "power:+24V":         (f"{SYM_PATH}/power.kicad_sym",                 "+24V"),
    "power:PWR_FLAG":     (f"{SYM_PATH}/power.kicad_sym",                 "PWR_FLAG"),
}

def lib_symbols_section():
    lines = ["(lib_symbols"]
    for lib_id, (fpath, sname) in LIBS.items():
        raw = extract_sym(fpath, sname)
        # Replace '  (symbol "SHORTNAME"' with '  (symbol "LIB:SHORTNAME"'
        short_name = lib_id.split(":")[1]   # e.g. "R" or "L78L24_SOT89"
        raw = raw.replace(f'(symbol "{sname}"', f'(symbol "{lib_id}"', 1)
        # Inner sub-symbols must use the short name (no lib: prefix).
        # When sname != short_name (e.g. we use a parent symbol), rename them.
        if sname != short_name:
            raw = re.sub(rf'\(symbol "{re.escape(sname)}_', f'(symbol "{short_name}_', raw)
        lines.append(raw)
    lines.append(")")
    return "\n".join(lines)


# ── Wire ──────────────────────────────────────────────────────────────────────
def wire(x1, y1, x2, y2):
    return (f'(wire (pts (xy {x1+OX:.2f} {y1+OY:.2f}) (xy {x2+OX:.2f} {y2+OY:.2f}))\n'
            f'  (stroke (width 0) (type default))\n'
            f'  (uuid "{new_uuid()}")\n)')


# ── Local net label ───────────────────────────────────────────────────────────
def label(net, x, y, angle=0):
    return (f'(label "{net}" (at {x+OX:.2f} {y+OY:.2f} {angle})\n'
            f'  (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'  (uuid "{new_uuid()}")\n'
            f'  (property "Intersheet References" "${{INTERSHEET_REFS}}" (at 0 0 0)\n'
            f'    (effects (font (size 1.27 1.27)) hide))\n)')


# ── No-connect ────────────────────────────────────────────────────────────────
def no_connect(x, y):
    return f'(no_connect (at {x+OX:.2f} {y+OY:.2f}) (uuid "{new_uuid()}"))'


# ── Junction ──────────────────────────────────────────────────────────────────
def junction(x, y):
    return f'(junction (at {x+OX:.2f} {y+OY:.2f}) (diameter 0) (color 0 0 0 0) (uuid "{new_uuid()}"))'


# ── Power symbol (GND / +24V etc.) ────────────────────────────────────────────
_pwr_seq = [0]

def power_sym(lib_id, x, y, angle=0):
    _pwr_seq[0] += 1
    ref = f"#PWR{_pwr_seq[0]:04d}"
    short = lib_id.split(":")[1]
    ax, ay = x + OX, y + OY
    return (f'(symbol (lib_id "{lib_id}") (at {ax:.2f} {ay:.2f} {angle}) (unit 1)\n'
            f'  (in_bom yes) (on_board yes) (dnp no)\n'
            f'  (uuid "{new_uuid()}")\n'
            f'  (property "Reference" "{ref}" (at {ax:.2f} {ay+2.54:.2f} {angle})\n'
            f'    (effects (font (size 1.27 1.27)) hide))\n'
            f'  (property "Value" "{short}" (at {ax:.2f} {ay-2.54:.2f} {angle})\n'
            f'    (effects (font (size 1.27 1.27))))\n'
            f'  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (instances (project "{PROJECT}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))\n)')


# ── Component symbol instance ──────────────────────────────────────────────────
def sym(lib_id, ref, val, x, y, angle=0, unit=1,
        footprint="", datasheet="", dnp=False,
        extra_props=None, pins=None):
    """
    pins: dict of {pin_number: net_name} — generates wire stub + label for each.
    Pin positions are looked up from PIN_OFFSETS below.
    """
    dnp_str = "yes" if dnp else "no"
    ax, ay = x + OX, y + OY
    lines = [
        f'(symbol (lib_id "{lib_id}") (at {ax:.2f} {ay:.2f} {angle}) (unit {unit})',
        f'  (in_bom yes) (on_board yes) (dnp {dnp_str})',
        f'  (uuid "{new_uuid()}")',
        f'  (property "Reference" "{ref}" (at {ax+2.54:.2f} {ay-2.54:.2f} {angle})',
        f'    (effects (font (size 1.27 1.27))))',
        f'  (property "Value" "{val}" (at {ax+2.54:.2f} {ay+1.27:.2f} {angle})',
        f'    (effects (font (size 1.27 1.27))))',
        f'  (property "Footprint" "{footprint}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
        f'  (property "Datasheet" "{datasheet}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
    ]
    if extra_props:
        for k, v in extra_props.items():
            lines.append(f'  (property "{k}" "{v}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    lines.append(f'  (instances (project "{PROJECT}" (path "/{ROOT_UUID}" (reference "{ref}") (unit {unit}))))')
    lines.append(")")
    return "\n".join(lines)


# ── Pin offset table (relative to component centre, in mm) ────────────────────
# Format: lib_id -> {pin_num: (dx, dy, stub_dir)}
# stub_dir: 'L'=left, 'R'=right, 'U'=up, 'D'=down
# Stub length = 2.54mm in stub_dir from pin tip

PIN_OFFSETS = {
    # Symbol coords are Y-up; schematic coords (written here) are Y-down → negate dy.
    "Device:R": {
        "1": (0, -3.81, "U"),   # top pin
        "2": (0,  3.81, "D"),   # bottom pin
    },
    "Device:C": {
        "1": (0, -3.81, "U"),
        "2": (0,  3.81, "D"),
    },
    "Device:C_Polarized": {
        "1": (0, -3.81, "U"),
        "2": (0,  3.81, "D"),
    },
    "Device:L": {
        "1": (0, -3.81, "U"),
        "2": (0,  3.81, "D"),
    },
    "Device:D_Zener": {
        "1": (-3.81, 0, "L"),   # K cathode (left)
        "2": ( 3.81, 0, "R"),   # A anode  (right)
    },
    "Amplifier_Operational:OPA1641": {
        "2": (-7.62, +2.54, "L"),   # IN- (sym y=-2.54 → sch +2.54, below centre)
        "3": (-7.62, -2.54, "L"),   # IN+ (sym y=+2.54 → sch -2.54, above centre)
        "4": (-2.54, +7.62, "D"),   # V-  (sym y=-7.62 → sch +7.62, below)
        "6": ( 7.62,  0,    "R"),   # OUT
        "7": (-2.54, -7.62, "U"),   # V+  (sym y=+7.62 → sch -7.62, above)
    },
    "Regulator_Linear:L78L24_SOT89": {
        # MC78L05_SOT89 parent: OUT=pin1, GND=pin2, IN=pin3
        "1": ( 7.62,  0,    "R"),   # OUT
        "2": ( 0,     7.62, "D"),   # GND (sym y=-7.62 → sch +7.62)
        "3": (-7.62,  0,    "L"),   # IN
    },
    "4xxx:40106": {
        # All gate units share the same pin layout, just different pin numbers
        "1":  (-7.62, 0, "L"),   # A1 input  (unit 1)
        "2":  ( 7.62, 0, "R"),   # Y1 output (unit 1)
        "3":  (-7.62, 0, "L"),   # A2 input  (unit 2)
        "4":  ( 7.62, 0, "R"),   # Y2 output (unit 2)
        "14": (0, -12.7, "U"),   # VDD (sym y=+12.7 → sch -12.7, above)
        "7":  (0,  12.7, "D"),   # VSS (sym y=-12.7 → sch +12.7, below)
    },
    "Diode:BAT54S": {
        # Series dual Schottky: A→[D1]→COM→[D2]→K
        "1": (-7.62,  0,    "L"),   # A  anode (left)
        "2": ( 7.62,  0,    "R"),   # K  cathode (right)
        "3": ( 0,     5.08, "D"),   # COM mid-node (sym y=-5.08 → sch +5.08, below)
    },
    "Connector_Generic:Conn_01x02": {
        # sym Y-up: pin1=(−5.08, 0), pin2=(−5.08, −2.54) → sch: negate y
        "1": (-5.08,  0,    "L"),
        "2": (-5.08,  2.54, "L"),
    },
    "Connector_Generic:Conn_01x03": {
        # sym Y-up: pin1=(−5.08,+2.54), pin2=(−5.08,0), pin3=(−5.08,−2.54)
        "1": (-5.08, -2.54, "L"),
        "2": (-5.08,  0,    "L"),
        "3": (-5.08,  2.54, "L"),
    },
}

STUB_LEN = 2.54  # 100 mil wire stub — keeps same-column stubs from overlapping

def stub_and_label(lib_id, cx, cy, pin_num, net_name, angle=0):
    """Return (wire_str, label_str) for one pin."""
    offsets = PIN_OFFSETS.get(lib_id, {})
    if pin_num not in offsets:
        return "", ""
    dx, dy, direction = offsets[pin_num]
    # Pin tip in schematic coordinates
    px, py = cx + dx, cy + dy
    # Stub end
    if direction == "L":
        lx, ly = px - STUB_LEN, py
        la = 0
    elif direction == "R":
        lx, ly = px + STUB_LEN, py
        la = 180
    elif direction == "U":
        lx, ly = px, py - STUB_LEN
        la = 270
    else:  # D
        lx, ly = px, py + STUB_LEN
        la = 90
    w = wire(px, py, lx, ly)
    lb = label(net_name, lx, ly, la)
    return w, lb


def component(lib_id, ref, val, x, y, angle=0, unit=1,
              footprint="", datasheet="", pins=None, dnp=False, extra_props=None):
    """Return list of S-expression strings: symbol + wire stubs + labels."""
    parts = [sym(lib_id, ref, val, x, y, angle, unit,
                 footprint, datasheet, dnp, extra_props)]
    if pins:
        for pin_num, net_name in pins.items():
            w, lb = stub_and_label(lib_id, x, y, pin_num, net_name, angle)
            if w:  parts.append(w)
            if lb: parts.append(lb)
    return parts


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMATIC COMPONENTS
# Each component defined as: (lib_id, ref, val, x, y, angle, unit, fp, ds, {pins})
# Grid: 2.54mm. Blocks separated by ~20mm.
#
# Coordinate map (all mm, Y increases downward):
#   Power / regulator block      : x=20..90,   y=20..70
#   Capsule input / OPA1641 block: x=100..190, y=20..80
#   Boost section                : x=20..160,  y=90..170
#   Transformer / XLR output     : x=170..260, y=60..100
# ─────────────────────────────────────────────────────────────────────────────

elements = []

# ── POWER BLOCK ──────────────────────────────────────────────────────────────

# R1: 6.8kΩ phantom feed from XLR pin 2 (XLR_HOT carries phantom +48V + audio hot)
elements += component("Device:R", "R1", "6.8k 0.1%",
    45, 22.5,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "XLR_HOT", "2": "V_OPA_RAW"})

# R2: 6.8kΩ phantom feed from XLR pin 3 (XLR_COLD carries phantom +48V + audio cold)
elements += component("Device:R", "R2", "6.8k 0.1%",
    45, 37.5,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "XLR_COLD", "2": "V_OPA_RAW"})

# U2: 78L24 SOT89  (MC78L05_SOT89 parent: OUT=pin1, GND=pin2, IN=pin3)
elements += component("Regulator_Linear:L78L24_SOT89", "U2", "L78L24",
    65, 30,
    footprint="Package_TO_SOT_SMD:SOT-89-3",
    pins={"3": "V_OPA_RAW", "2": "GND", "1": "V_OPA"})

# C1: 100nF 78L24 input decoupling
elements += component("Device:C", "C1", "100n 63V X7R",
    52, 22,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OPA_RAW", "2": "GND"})

# C2: 100nF 78L24 output decoupling
elements += component("Device:C", "C2", "100n 25V X7R",
    78, 22,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OPA", "2": "GND"})

# R4: 470kΩ V_MID divider high side
elements += component("Device:R", "R4", "470k",
    90, 30,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_OPA", "2": "V_MID"})

# R5: 470kΩ V_MID divider low side
elements += component("Device:R", "R5", "470k",
    90, 45,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_MID", "2": "GND"})

# C4: 10µF V_MID bypass
elements += component("Device:C", "C4", "10u 25V X5R",
    103, 37.5,
    footprint="Capacitor_SMD:C_0603_1608Metric",
    pins={"1": "V_MID", "2": "GND"})

# C5: 10µF SMD electrolytic VBIAS bypass
elements += component("Device:C_Polarized", "C5", "10u 25V",
    78, 45,
    footprint="Capacitor_SMD:CP_Elec_4x5.4",
    pins={"1": "GND", "2": "V_MID"})

# C6: 10µF SMD electrolytic VCC bypass
elements += component("Device:C_Polarized", "C6", "10u 25V",
    78, 62.5,
    footprint="Capacitor_SMD:CP_Elec_4x5.4",
    pins={"1": "GND", "2": "V_OPA"})

# R_ZEN: 6.8kΩ series resistor for Z_OSC
elements += component("Device:R", "R_ZEN1", "6.8k",
    90, 15,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_OPA", "2": "V_OSC"})

# Z_OSC: 15V zener shunt regulator for U3 VDD  (pin2=A=GND, pin1=K=V_OSC)
elements += component("Device:D_Zener", "Z_OSC1", "15V MMSZ15VT1G",
    110, 15,
    footprint="Diode_SMD:D_SOD-123",
    pins={"2": "GND", "1": "V_OSC"})

# ── OPA1641 SIGNAL BLOCK ──────────────────────────────────────────────────────

# R_GBIAS1: 47MΩ HV polarization resistor (first half)
elements += component("Device:R", "R_GBIAS1", "47M 1206",
    120, 22.5,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "HV_FILT", "2": "HV_MID"})

# R_GBIAS2: 47MΩ HV polarization resistor (second half, net 94MΩ total)
elements += component("Device:R", "R_GBIAS2", "47M 1206",
    120, 30,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "HV_MID", "2": "CAP_FP"})

# J2: Capsule front plate wire pad
elements += component("Connector_Generic:Conn_01x02", "J2", "CAPSULE",
    140, 17.5, pins={"1": "CAP_FP", "2": "GND"},
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")

# C8: 10nF C0G input coupling cap
elements += component("Device:C", "C8", "10n X7R 0805",
    135, 30,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "CAP_FP", "2": "VPLUS"})

# R_BIAS: 100MΩ input bias VPLUS→V_MID
elements += component("Device:R", "R_BIAS1", "100M 1206",
    135, 45,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "VPLUS", "2": "V_MID"})

# U1: OPA1641 SOIC-8
elements += component("Amplifier_Operational:OPA1641", "U1", "OPA1641",
    165, 55,
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    pins={"3": "VPLUS", "2": "VINV", "6": "SIG_OUT", "7": "V_OPA", "4": "GND"})

# R3: 2.2kΩ inverting input bias (Rin)
elements += component("Device:R", "R3", "2.2k",
    148, 52.5,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_MID", "2": "VINV"})

# R6: 130kΩ feedback (Rf)
elements += component("Device:R", "R6", "130k",
    165, 40,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "SIG_OUT", "2": "VINV"})

# R7: 100Ω output series protection
elements += component("Device:R", "R7", "100R",
    185, 55,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "SIG_OUT", "2": "SIG_PROT"})

# C3: 100nF VCC HF decoupling near OPA1641
elements += component("Device:C", "C3", "100n 25V X7R",
    158, 70,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OPA", "2": "GND"})

# C7: 4.7µF X7R 1206 DC blocking cap to transformer
elements += component("Device:C", "C7", "4.7u 50V X7R 1206",
    200, 55,
    footprint="Capacitor_SMD:C_1206_3216Metric",
    pins={"1": "SIG_PROT", "2": "TX_DRV"})

# ── TRANSFORMER (NTE10/3) — modeled as 5 solder pad connectors ───────────────
# T1 is a TH transformer with flying wires; represented by two connectors:
# Connector A: primary (3× winding driven side): TX_DRV, GND, GND  (red, blue, black wires)
# Connector B: secondary (1× winding balanced out): XLR_HOT, XLR_COLD  (white, yellow wires)
elements += component("Connector_Generic:Conn_01x03", "TP1", "NTE10/3_PRI",
    218, 55, pins={"1": "TX_DRV", "2": "GND", "3": "GND"},
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")

elements += component("Connector_Generic:Conn_01x02", "TS1", "NTE10/3_SEC",
    235, 55, pins={"1": "XLR_HOT", "2": "XLR_COLD"},
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")

# J3: XLR balanced output connector (3-pin: GND, HOT, COLD)
elements += component("Connector_Generic:Conn_01x03", "J3", "XLR_OUT",
    255, 60, pins={"1": "GND", "2": "XLR_HOT", "3": "XLR_COLD"},
    footprint="Connector_Audio:XLR3_Male_Neutrik_NC3MXX_Horizontal")

# ── BOOST SECTION ─────────────────────────────────────────────────────────────

# U3: CD40106B hex Schmitt inverter, unit 1 (oscillator gate)
elements += component("4xxx:40106", "U3", "CD40106B",
    40, 110, unit=1,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"1": "CLKA_IN", "2": "CLKA"})

# U3 power unit (unit 7): VDD=pin14, VSS=pin7
elements += component("4xxx:40106", "U3", "CD40106B",
    40, 145, unit=7,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"14": "V_OSC", "7": "GND"})

# R_OSC: 47kΩ oscillator timing resistor (between CLKA and CLKA_IN)
elements += component("Device:R", "R_OSC1", "47k",
    58, 107.5,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "CLKA", "2": "CLKA_IN"})

# C10: 100pF oscillator timing cap
elements += component("Device:C", "C10", "100p C0G",
    58, 122.5,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "CLKA_IN", "2": "GND"})

# U3 bypass cap on V_OSC
elements += component("Device:C", "C_U3", "100n 25V X7R",
    48, 120,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OSC", "2": "GND"})

# Dickson pump diodes — 2× BAT54S (series dual Schottky, A→COM→K = 2 diodes per pkg)
# D1: pin1(A)=V_OPA → [D1a] → pin3(COM)=N1 → [D1b] → pin2(K)=N2
# D2: pin1(A)=N2    → [D2a] → pin3(COM)=N3 → [D2b] → pin2(K)=VBOOST

elements += component("Diode:BAT54S", "D1", "BAT54S",
    85, 100,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"1": "V_OPA", "3": "N1", "2": "N2"})

elements += component("Diode:BAT54S", "D2", "BAT54S",
    113, 100,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"1": "N2", "3": "N3", "2": "VBOOST"})

# Pump caps: Cp1 (CLKA), Cp2 (CLKB), Cp3 (CLKA)
# CLKB = inverted CLKA (second gate of CD40106B)
elements += component("Device:C", "Cp1", "100n 100V X7R",
    83, 115,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "N1", "2": "CLKA"})

elements += component("Device:C", "Cp2", "100n 100V X7R",
    100, 115,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "N2", "2": "CLKB"})

elements += component("Device:C", "Cp3", "100n 100V X7R",
    117, 115,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "N3", "2": "CLKA"})

# CLKB second gate of CD40106B (unit 2)
elements += component("4xxx:40106", "U3", "CD40106B",
    55, 130, unit=2,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"3": "CLKA", "4": "CLKB"})

# Reservoir cap
elements += component("Device:C", "Cres1", "470n 100V X7R",
    146, 100,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "VBOOST", "2": "GND"})

# DZ1: 68V zener HV clamp on VBOOST  (pin2=A=GND, pin1=K=VBOOST)
elements += component("Device:D_Zener", "DZ1", "68V BZT52C68",
    160, 115,
    footprint="Diode_SMD:D_SOD-123",
    pins={"2": "GND", "1": "VBOOST"})

# L1: 10mH SMD LC filter inductor
elements += component("Device:L", "L1", "10mH FNR5040S",
    178, 100,
    footprint="Inductor_SMD:L_Changjiang_FNR5040S",
    pins={"1": "VBOOST", "2": "HV_FILT"})

# C9: 470nF 100V LC filter cap
elements += component("Device:C", "C9", "470n 100V X7R",
    193, 112,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "HV_FILT", "2": "GND"})

# ── POWER FLAGS (suppress ERC power_pin_not_driven) ──────────────────────────
# Placed in a dedicated block below the main circuit (y=185..215, before shift).
# Net labels connect the flags to the appropriate nets without overlapping components.

# GND: power symbol + PWR_FLAG on same wire
elements.append(power_sym("power:GND",      25, 185))
elements.append(power_sym("power:PWR_FLAG", 35, 185))
elements.append(wire(25, 185, 35, 185))

# V_OPA_RAW: U2 IN pin (power_in) needs a driver
elements.append(label("V_OPA_RAW", 20, 200, 0))
elements.append(wire(20, 200, 35, 200))
elements.append(power_sym("power:PWR_FLAG", 35, 200))

# V_OSC: U3 VDD (power_in) needs a driver
elements.append(label("V_OSC", 20, 210, 0))
elements.append(wire(20, 210, 35, 210))
elements.append(power_sym("power:PWR_FLAG", 35, 210))

# ── SHEET / SYMBOL INSTANCES (required for KiCad 7 validity) ─────────────────
SHEET_INST = f'(sheet_instances (path "/" (page "1")))'
SYMBOL_INST = ""  # Already embedded in each symbol via 'instances' field


# ─────────────────────────────────────────────────────────────────────────────
# ASSEMBLE AND WRITE
# ─────────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs("pcb", exist_ok=True)

    body_lines = []
    for e in elements:
        if isinstance(e, str):
            body_lines.append(e)
        elif isinstance(e, list):
            body_lines.extend(e)

    body = "\n\n".join(body_lines)

    schematic = f"""(kicad_sch (version 20230121) (generator kiutils)

  (uuid "{ROOT_UUID}")

  (paper "A3")

  {lib_symbols_section()}

{body}

  {SHEET_INST}

)
"""
    out_path = OUT
    with open(out_path, "w") as f:
        f.write(schematic)
    print(f"Written: {out_path}")
    print(f"Components: {schematic.count('(lib_id ')} instances")


if __name__ == "__main__":
    main()
