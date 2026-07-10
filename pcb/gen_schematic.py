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


# ── Grid snap ─────────────────────────────────────────────────────────────────
def _G(n):
    """Snap coordinate to nearest 1.27 mm (50 mil) schematic grid point."""
    return round(n / 1.27) * 1.27


# ── UUID helpers ──────────────────────────────────────────────────────────────
_uuid_counter = 0
def new_uuid():
    global _uuid_counter
    _uuid_counter += 1
    return f"{_uuid_counter:08x}-0000-0000-0000-000000000000"

ROOT_UUID = new_uuid()

# Centering offset for A3 (420×297mm) page.
# Circuit spans x=15..240, y=5..265 → center at (127.5, 135).
# A3 center at (210, 148.5) → shift = (210-127.5, 148.5-135) = (82.5, 13.5)
OX, OY = 82.5, 13.5


# ── Symbol extraction from .kicad_sym library files ───────────────────────────
def extract_sym(lib_file, name):
    """Return the top-level (symbol "name" ...) block from a .kicad_sym file."""
    with open(lib_file) as f:
        txt = f.read()
    # Leading whitespace before top-level "(symbol" varies by KiCad version
    # (2 spaces pre-9.0, tabs from 9.0 onward), so match it generically.
    m = re.search(rf'^[ \t]+\(symbol "{re.escape(name)}"', txt, re.MULTILINE)
    if m is None:
        raise ValueError(f'Symbol "{name}" not found in {lib_file}')
    idx = m.start()
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
    "Device:Q_NPN":       (f"{SYM_PATH}/Device.kicad_sym",                "Q_NPN"),
    "Amplifier_Operational:OPA1641": (f"{SYM_PATH}/Amplifier_Operational.kicad_sym", "OPA1641"),
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
        short_name = lib_id.split(":")[1]   # e.g. "R" or "L78L24_SOT89"
        # Rename outer symbol name to the full lib_id.
        raw = raw.replace(f'(symbol "{sname}"', f'(symbol "{lib_id}"', 1)
        # When sname != short_name we're using a parent symbol (because the real
        # target uses (extends sname) which kicad-cli can't resolve in embedded
        # lib_symbols). Apply the target's property values and rename sub-symbols
        # so the embedded flat symbol matches the resolved library symbol.
        if sname != short_name:
            raw = re.sub(rf'\(symbol "{re.escape(sname)}_', f'(symbol "{short_name}_', raw)
            try:
                target_raw = extract_sym(fpath, short_name)
                target_props = {m.group(1): m.group(2)
                                for m in re.finditer(r'\(property "([^"]+)" "([^"]*)"', target_raw)}
                def _patch(m):
                    name, val = m.group(1), m.group(2)
                    if name in target_props and target_props[name] != val:
                        return m.group(0).replace(f'"{val}"', f'"{target_props[name]}"', 1)
                    return m.group(0)
                raw = re.sub(r'\(property "([^"]+)" "([^"]*)"', _patch, raw)
            except ValueError:
                pass  # target symbol not in library; keep parent's properties
        lines.append(raw)
    lines.append(")")
    return "\n".join(lines)


# ── Wire ──────────────────────────────────────────────────────────────────────
def wire(x1, y1, x2, y2):
    return (f'(wire (pts (xy {_G(x1+OX):.2f} {_G(y1+OY):.2f}) (xy {_G(x2+OX):.2f} {_G(y2+OY):.2f}))\n'
            f'  (stroke (width 0) (type default))\n'
            f'  (uuid "{new_uuid()}")\n)')


# ── Local net label ───────────────────────────────────────────────────────────
def label(net, x, y, angle=0):
    return (f'(label "{net}" (at {_G(x+OX):.2f} {_G(y+OY):.2f} {angle})\n'
            f'  (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'  (uuid "{new_uuid()}")\n)')


# ── No-connect ────────────────────────────────────────────────────────────────
def no_connect(x, y):
    return f'(no_connect (at {_G(x+OX):.2f} {_G(y+OY):.2f}) (uuid "{new_uuid()}"))'


# ── Junction ──────────────────────────────────────────────────────────────────
def junction(x, y):
    return f'(junction (at {_G(x+OX):.2f} {_G(y+OY):.2f}) (diameter 0) (color 0 0 0 0) (uuid "{new_uuid()}"))'


# ── Power symbol (GND / +24V etc.) ────────────────────────────────────────────
_pwr_seq = [0]

def power_sym(lib_id, x, y, angle=0):
    _pwr_seq[0] += 1
    ref = f"#PWR{_pwr_seq[0]:04d}"
    short = lib_id.split(":")[1]
    ax, ay = _G(x + OX), _G(y + OY)
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
    ax, ay = _G(x + OX), _G(y + OY)
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
    "Device:Q_NPN": {
        # Verified from Device.kicad_sym Q_NPN_1_1: at (x,y,angle) is stub TIP; negate y for schematic
        "B": (-5.08,  0,    "L"),   # at (-5.08, 0, 0)   → stub tip left of body
        "C": ( 2.54, -5.08, "U"),   # at (2.54, +5.08, 270) → KiCad Y-up +5.08 → sch -5.08, stub up
        "E": ( 2.54,  5.08, "D"),   # at (2.54, -5.08, 90)  → KiCad Y-up -5.08 → sch +5.08, stub down
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
        # All gate units share the same visual pin layout, just different pin numbers
        "1":  (-7.62, 0, "L"),   # A1 input  (unit 1)
        "2":  ( 7.62, 0, "R"),   # Y1 output (unit 1)
        "3":  (-7.62, 0, "L"),   # A2 input  (unit 2)
        "4":  ( 7.62, 0, "R"),   # Y2 output (unit 2)
        "5":  (-7.62, 0, "L"),   # A3 input  (unit 3)
        "6":  ( 7.62, 0, "R"),   # Y3 output (unit 3)
        "9":  (-7.62, 0, "L"),   # A4 input  (unit 4)
        "8":  ( 7.62, 0, "R"),   # Y4 output (unit 4)
        "11": (-7.62, 0, "L"),   # A5 input  (unit 5)
        "10": ( 7.62, 0, "R"),   # Y5 output (unit 5)
        "13": (-7.62, 0, "L"),   # A6 input  (unit 6)
        "12": ( 7.62, 0, "R"),   # Y6 output (unit 6)
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

# Nets that become power symbols instead of wire-stub + label.
# Key: net name. Value: (power lib_id, {direction: angle}) where angle orients the symbol.
# GND on a D-direction pin → power:GND pointing downward (angle 0).
# V_OPA on a U-direction pin → power:+24V pointing upward (angle 0).
_POWER_SYMBOL_NETS = {
    "GND": {"D": ("power:GND", 0)},
    # V_OPA is drawn as an explicit bus spine + local wires (see Block A / Block D wires)
}

def stub_and_label(lib_id, cx, cy, pin_num, net_name, angle=0):
    """Return (wire_str, label_or_power_str) for one pin."""
    offsets = PIN_OFFSETS.get(lib_id, {})
    if pin_num not in offsets:
        return "", ""
    dx, dy, direction = offsets[pin_num]
    px, py = cx + dx, cy + dy  # pin tip

    # Power symbol substitution (replaces stub + label)
    pmap = _POWER_SYMBOL_NETS.get(net_name, {})
    if direction in pmap:
        plib, pangle = pmap[direction]
        return "", power_sym(plib, px, py, pangle)

    # Normal stub + label
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
# SCHEMATIC COMPONENTS  (all coords are raw mm, before OX/OY offset)
#
# Layout (inspired by OPIC.TX3): left→right signal flow, GND/V_OPA as power symbols
#
# ROW 1 (y≈5–48):    Phantom feed + regulator + V_OSC zener
# ROW 2 (y≈48–100):  HV bias | V_MID divider | OPA1641 stage | transformer + XLR
# ROW 3 (y≈108–150): Schmitt oscillator | Dickson charge pump | LC filter
# ROW 4 (y≈165+):    Unused U3 gates | PWR flags
# ─────────────────────────────────────────────────────────────────────────────

elements = []

# ── BLOCK A: PHANTOM FEED + VOLTAGE REGULATOR (x=15..80, y=5..48) ────────────
# GND pins (direction D) → power:GND symbols automatically
# V_OPA pins (direction U) → power:+24V symbols automatically

elements += component("Device:R", "R1", "6.8k 0.1%",
    22, 12,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "XLR_HOT", "2": "V_OPA_RAW"})

elements += component("Device:R", "R2", "6.8k 0.1%",
    22, 37,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "XLR_COLD", "2": "V_OPA_RAW"})

elements += component("Device:C", "C1", "100n 63V X7R",
    38, 20,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OPA_RAW", "2": "GND"})

# Low-Iq V_OPA supply: R_REG1 biases Z_REG1 (24V zener) → Q1 emitter follower → V_OPA = 23.3V
# Total Iq < 3.5mA at 48V phantom; V_OPA_RAW ≈ 25.8V (vs ~11V with L78L24 at 48V phantom)
elements += component("Device:R", "R_REG1", "2.2k",
    48, 13,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_OPA_RAW", "2": "V_BASE_REG"})

elements += component("Device:D_Zener", "Z_REG1", "24V BZT52C24",
    63, 25,
    footprint="Diode_SMD:D_SOD-123",
    pins={"1": "V_BASE_REG", "2": "GND"})

# Q1: NPN emitter follower — C=V_OPA_RAW, B=V_BASE_REG (24V zener), E=V_OPA (23.3V out)
elements += component("Device:Q_NPN", "Q1", "MMBT5551",
    75, 20,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"C": "V_OPA_RAW", "B": "V_BASE_REG", "E": "V_OPA"})

elements += component("Device:C", "C2", "100n 25V X7R",
    74, 12,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OPA", "2": "GND"})

elements += component("Device:C_Polarized", "C5", "10u 25V",
    95, 50,
    footprint="Capacitor_SMD:CP_Elec_4x5.4",
    pins={"1": "V_MID", "2": "GND"})

elements += component("Device:C_Polarized", "C6", "10u 25V",
    74, 63,
    footprint="Capacitor_SMD:CP_Elec_4x5.4",
    pins={"1": "V_OPA", "2": "GND"})

# R_ZEN1 + Z_OSC1: y=20 row, V_OPA → R_ZEN1(105) → V_OSC → Z_OSC1(120) → GND
# V_OPA on R_ZEN1.pin1 uses net label (stub_and_label auto-generates it).
# V_OSC on both R_ZEN1.pin2 and Z_OSC1.pin1 uses net labels — no explicit wire needed.
elements += component("Device:R", "R_ZEN1", "6.8k",
    105, 20,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_OPA", "2": "V_OSC"})

elements += component("Device:D_Zener", "Z_OSC1", "15V MMSZ15VT1G",
    120, 20,
    footprint="Diode_SMD:D_SOD-123",
    pins={"1": "V_OSC", "2": "GND"})

# V_OPA spine at x=80: C2 (top), Q1.E stub, R4, C6 (bottom)
# Q1 at (75,20): E tip=(77.54,25.08), stub_end=(77.54,27.62) → wire right to spine
# R_ZEN1 uses V_OPA net label (auto-generated by stub_and_label) — no spine branch needed.
elements.append(wire(80, 8.19, 80, 59.19))           # V_OPA spine
elements.append(wire(74, 8.19, 80, 8.19))             # C2.pin1 tip → spine top
elements.append(wire(77.54, 27.62, 80, 27.62))        # Q1.E stub_end → spine
elements.append(wire(72, 46.19, 80, 46.19))           # R4.pin1 tip → spine
elements.append(wire(74, 59.19, 80, 59.19))           # C6.pin1 tip → spine bottom
elements.append(junction(80, 27.62))                  # T: spine + Q1.E branch
elements.append(junction(80, 46.19))                  # T: spine + R4 branch

# V_OPA_RAW: R1.pin2 stub_end ↔ R2.pin1 stub_end
# R1(22,12) pin2(D) stub_end=(22,18.35); R2(22,37) pin1(U) stub_end=(22,30.65)
elements.append(wire(22, 18.35, 22, 30.65))

# V_OPA_RAW net shared via label: C1.pin1 + R_REG1.pin1 + Q1.C — no explicit wires needed

# ── BLOCK B: V_MID VOLTAGE DIVIDER (x=68..90, y=48..88) ─────────────────────

elements += component("Device:R", "R4", "470k",
    72, 50,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_OPA", "2": "V_MID"})

elements += component("Device:R", "R5", "470k",
    72, 75,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_MID", "2": "GND"})

# R4.pin2 ↔ R5.pin1 vertical V_MID wire; C4/C5 connect via V_MID net label
elements.append(wire(72, 56.35, 72, 68.65))          # R4.pin2 ↔ R5.pin1 (V_MID node)

# C4 at (87,63): same y as C6(74,63) — both are bypass caps at the same stage.
# V_MID connects via net label; no branch wire needed (consistent with C5 approach).
elements += component("Device:C", "C4", "10u 25V X5R",
    87, 63,
    footprint="Capacitor_SMD:C_0603_1608Metric",
    pins={"1": "V_MID", "2": "GND"})

# ── BLOCK C: HV BIAS CHAIN + CAPSULE + AC COUPLING (x=20..58, y=48..95) ──────

elements += component("Device:R", "R_GBIAS1", "47M 1206",
    30, 60,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "HV_FILT", "2": "HV_MID"})

elements += component("Device:R", "R_GBIAS2", "47M 1206",
    30, 85,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "HV_MID", "2": "CAP_FP"})

# R_GBIAS1↔R_GBIAS2 series wire (HV_MID node)
# GBIAS1(30,60).pin2 stub D→(30,66.35); GBIAS2(30,85).pin1 stub U→(30,78.65)
elements.append(wire(30, 66.35, 30, 78.65))

elements += component("Connector_Generic:Conn_01x02", "J2", "CAPSULE",
    50, 52,
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    pins={"1": "CAP_FP", "2": "GND"})

elements += component("Device:C", "C8", "1n 100V C0G 0402",
    50, 70,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "CAP_FP", "2": "VPLUS"})

elements += component("Device:R", "R_BIAS1", "100M 1206",
    50, 88,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "VPLUS", "2": "V_MID"})

# CAP_FP bus at x=44: R_GBIAS2.pin2 → J2.pin1 → C8.pin1
# R_GBIAS2(30,85) pin2 tip=(30,88.81) stub D→(30,91.35)
# J2(50,52) pin1 tip=(44.92,52) stub L→(42.38,52)
# C8(50,70) pin1 tip=(50,66.19) stub U→(50,63.65)
elements.append(wire(44, 52, 44, 91.35))         # vertical CAP_FP bus at x=44 (extended)
elements.append(wire(42.38, 52, 44, 52))          # J2.pin1 stub_end → bus top
elements.append(wire(50, 63.65, 44, 63.65))      # C8.pin1 stub_end → bus mid
elements.append(wire(30, 91.35, 44, 91.35))      # R_GBIAS2.pin2 stub_end → bus bot
elements.append(junction(44, 63.65))             # T: bus + C8 branch

# VPLUS node: C8.pin2 → R_BIAS1.pin1 (vertical at x=50); then right to U1.IN+
# C8(50,70) pin2 tip=(50,73.81); R_BIAS1(50,88) pin1 tip=(50,84.19)
# U1(122,67) IN+ tip=(114.38,64.46) stub L→(111.84,64.46)
elements.append(wire(50, 73.81, 50, 84.19))      # C8.pin2 → R_BIAS1.pin1 (VPLUS vertical)
elements.append(wire(50, 76.35, 111.84, 76.35))  # horizontal to U1.IN+ column
elements.append(wire(111.84, 76.35, 111.84, 64.46))  # up to U1.IN+ stub_end
elements.append(junction(50, 76.35))             # T: vertical VPLUS + horizontal

# ── BLOCK D: OPA1641 SIGNAL STAGE (x=88..172, y=48..102) ────────────────────

elements += component("Device:R", "R3", "2.2k",
    92, 84,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_MID", "2": "VINV"})

# Presence-peak network: Rs (6.2k) + C (12nF) in series, parallel with R3.
# At DC: C blocks → Z = R3 = 2.2k (gain unchanged).
# At HF: C shorts → Z = R3‖Rs = 1.61k → +2.6 dB above f_c = 1/(2π×6.2k×12nF) ≈ 2.1 kHz.
# Placed at x=77, left of R3, clear of VPLUS wire (y=76.35) and all Block B components.
elements += component("Device:R", "R_PRES1", "6.2k",
    77, 90,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "V_MID", "2": "RS_MID"})

elements += component("Device:C", "C_PRES1", "12n 25V X7R",
    77, 108,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "RS_MID", "2": "VINV"})

elements += component("Device:R", "R6", "5.6k",
    107, 52,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "SIG_OUT", "2": "VINV"})

# U1: OPA1641; GND(pin4,D)→GND sym automatically; V_OPA connected via local wire below
elements += component("Amplifier_Operational:OPA1641", "U1", "OPA1641",
    122, 67,
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    pins={"3": "VPLUS", "2": "VINV", "6": "SIG_OUT", "7": "V_OPA", "4": "GND"})

elements += component("Device:C", "C3", "100n 25V X7R",
    113, 83,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OPA", "2": "GND"})

elements += component("Device:R", "R7", "100R",
    143, 64,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "SIG_OUT", "2": "SIG_PROT"})

elements += component("Device:C", "C7", "4.7u 50V X7R 1206",
    159, 58,
    footprint="Capacitor_SMD:C_1206_3216Metric",
    pins={"1": "SIG_PROT", "2": "TX_DRV"})

# VINV node: R6.pin2 → vertical bus → R3.pin2 branch + U1.IN− branch
# R6(107,52) pin2 tip=(107,55.81) stub D→(107,58.35)
# R3(92,84) pin2 tip=(92,87.81) stub D→(92,90.35)   [VINV,D → NOT GND, keeps stub]
# U1(122,67) IN− tip=(114.38,69.54) stub L→(111.84,69.54)
elements.append(wire(107, 58.35, 107, 90.35))    # vertical VINV bus
elements.append(wire(92, 90.35, 107, 90.35))     # R3.pin2 stub_end → right to bus
elements.append(wire(107, 69.54, 111.84, 69.54)) # bus → U1.IN− stub_end
elements.append(junction(107, 69.54))            # T: bus + U1.IN− branch
elements.append(junction(107, 90.35))            # T: bus + R3 branch

# SIG_OUT node: U1.OUT → feedback arc to R6.pin1 + output to R7.pin1
# U1(122,67) OUT tip=(129.62,67) stub R→(132.16,67)
# R6(107,52) pin1 tip=(107,48.19) stub U→(107,45.65)
# R7(143,64) pin1 tip=(143,60.19) stub U→(143,57.65)
elements.append(wire(132.16, 67, 132.16, 45.65)) # U1.OUT stub up to R6.pin1 level
elements.append(wire(132.16, 45.65, 107, 45.65)) # left to R6.pin1 stub_end (feedback)
elements.append(wire(132.16, 67, 143, 67))        # right toward R7
elements.append(wire(143, 67, 143, 60.19))        # up to R7.pin1 tip
elements.append(junction(132.16, 67))             # T: feedback up + output right

# SIG_PROT: R7.pin2 → around C7 right side → C7.pin1
# R7(143,64) pin2 tip=(143,67.81) stub D→(143,70.35)
# C7(159,58) pin1 tip=(159,54.19) stub U→(159,51.65)
elements.append(wire(143, 70.35, 162, 70.35))    # right of C7
elements.append(wire(162, 70.35, 162, 54.19))    # up
elements.append(wire(162, 54.19, 159, 54.19))    # left to C7.pin1 tip

# V_OPA local: C3.pin1 stub_end (113,76.65) → up → U1.V+ tip (119.46,59.38)
# Visually shows that U1.V+ and C3 (bypass) share the same V_OPA supply
elements.append(wire(113, 76.65, 113, 59.38))    # vertical up from C3 stub_end
elements.append(wire(113, 59.38, 119.46, 59.38)) # horizontal to U1.V+ tip

# ── BLOCK E: TRANSFORMER + XLR OUTPUT (x=178..230, y=55..78) ─────────────────

elements += component("Connector_Generic:Conn_01x03", "TP1", "NTE10/3_PRI",
    178, 63,
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    pins={"1": "TX_DRV", "2": "GND"})
elements.append(no_connect(172.92, 65.54))  # S3 pin tip: far end of secondary winding, leave floating

elements += component("Connector_Generic:Conn_01x02", "TS1", "NTE10/3_SEC",
    196, 63,
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    pins={"1": "XLR_HOT", "2": "XLR_COLD"})

elements += component("Connector_Generic:Conn_01x03", "J3", "XLR_OUT",
    213, 67,
    footprint="",
    pins={"1": "GND", "2": "XLR_HOT_F", "3": "XLR_COLD_F"})

# RFI filter: 100R series + 100pF C0G shunt on each XLR leg (fc ~16 MHz)
# Placed to the right of J3; XLR_HOT/COLD nets connect via local label to TS1
# XLR_HOT_F/COLD_F connect via local label to J3 stubs above
elements += component("Device:R", "R_RFI1", "100R",
    235, 58,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "XLR_HOT", "2": "XLR_HOT_F"})

elements += component("Device:C", "C_RFI1", "100p C0G",
    247, 58,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "XLR_HOT_F", "2": "GND"})

elements += component("Device:R", "R_RFI2", "100R",
    235, 76,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "XLR_COLD", "2": "XLR_COLD_F"})

elements += component("Device:C", "C_RFI2", "100p C0G",
    247, 76,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "XLR_COLD_F", "2": "GND"})

# TX_DRV: C7.pin2 stub_end (159,51.65) → TP1.pin1 stub_end (170.38,60.46)
# C7(159,58) pin2(U) stub_end=(159,51.65); TP1(178,63) pin1(L) stub_end=(170.38,60.46)
elements.append(wire(159, 51.65, 170.38, 51.65))
elements.append(wire(170.38, 51.65, 170.38, 60.46))

# XLR outputs connect via net labels: TS1(XLR_HOT/COLD) → R_RFI1/2 → J3(XLR_HOT_F/COLD_F)
# No explicit wires needed; net-label stubs on each component carry the signal topology.

# ── BLOCK F: SCHMITT OSCILLATOR (x=15..67, y=108..160) ───────────────────────

elements += component("4xxx:40106", "U3", "CD40106B",
    28, 118, unit=1,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"1": "CLKA_IN", "2": "CLKA"})

elements += component("4xxx:40106", "U3", "CD40106B",
    52, 118, unit=2,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"3": "CLKA", "4": "CLKB"})

elements += component("4xxx:40106", "U3", "CD40106B",
    28, 148, unit=7,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"14": "V_OSC", "7": "GND"})

elements += component("Device:R", "R_OSC1", "47k",
    40, 106,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "CLKA", "2": "CLKA_IN"})

# R_OSC1(40,106): pin1(CLKA,U) tip=(40,102.19) stub→(40,99.65)
#                 pin2(CLKA_IN,D) tip=(40,109.81) stub→(40,112.35)
# C10(40,128): pin1(CLKA_IN,U) tip=(40,124.19) stub→(40,121.65)
#              pin2(GND,D) auto
elements += component("Device:C", "C10", "100p C0G",
    40, 128,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "CLKA_IN", "2": "GND"})

# R_OSC1↔C10 CLKA_IN vertical wire
elements.append(wire(40, 112.35, 40, 121.65))

# CLKA horizontal bus: U3A(28,118).pin2 stub(38.16,118) ↔ U3B(52,118).pin3 stub(41.84,118)
# branch up to R_OSC1.pin1 tip (40,102.19) via junction at (40,118)
elements.append(wire(38.16, 118, 41.84, 118))
elements.append(wire(40, 118, 40, 102.19))
elements.append(junction(40, 118))

# CLKA_IN feedback: R_OSC1.pin2 stub (40,112.35) → left → down to U3A.pin1 stub (17.84,118)
# horizontal at y=112.35 is above gate bodies (gates at y=118, body top ≈ y=114)
elements.append(wire(40, 112.35, 17.84, 112.35))
elements.append(wire(17.84, 112.35, 17.84, 118))
elements.append(junction(40, 112.35))

elements += component("Device:C", "C_U3", "100n 25V X7R",
    38, 140,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "V_OSC", "2": "GND"})

# V_OSC: U3G.pin14 stub_end (28,132.76) → C_U3.pin1 stub_end (38,133.65)
elements.append(wire(28, 132.76, 38, 132.76))
elements.append(wire(38, 132.76, 38, 133.65))

# ── BLOCK G: DICKSON CHARGE PUMP (x=82..180, y=108..150) ─────────────────────

elements += component("Diode:BAT54S", "D1", "BAT54S",
    88, 113,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"1": "V_OPA", "3": "N1", "2": "N2"})

elements += component("Diode:BAT54S", "D2", "BAT54S",
    118, 113,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"1": "N2", "3": "N3", "2": "VBOOST"})

elements += component("Device:C", "Cp1", "100n 100V X7R",
    88, 133,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "N1", "2": "CLKA"})

elements += component("Device:C", "Cp2", "100n 100V X7R",
    103, 133,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "N2", "2": "CLKB"})

elements += component("Device:C", "Cp3", "100n 100V X7R",
    118, 133,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "N3", "2": "CLKA"})

# N1: D1.pin3(COM,D) stub_end(88,120.62) → Cp1.pin1(N1,U) stub_end(88,126.65)
elements.append(wire(88, 120.62, 88, 126.65))

# N2: D1.pin2(K,R) stub_end(98.16,113) ↔ D2.pin1(A,L) stub_end(107.84,113)
#     branch at x=103 down to Cp2.pin1(N2,U) stub_end(103,126.65)
elements.append(wire(98.16, 113, 107.84, 113))
elements.append(wire(103, 113, 103, 126.65))
elements.append(junction(103, 113))

# N3: D2.pin3(COM,D) stub_end(118,120.62) → Cp3.pin1(N3,U) stub_end(118,126.65)
elements.append(wire(118, 120.62, 118, 126.65))

# CLKA pump bus at y=145: connects Cp1.pin2(88,139.35) and Cp3.pin2(118,139.35)
# Cp2.pin2(CLKB) stub at (103,139.35) is between them — bus routed below to avoid crossing CLKB
elements.append(wire(88, 139.35, 88, 145))
elements.append(wire(118, 139.35, 118, 145))
elements.append(wire(88, 145, 118, 145))

elements += component("Device:C", "Cres1", "470n 100V X7R",
    150, 113,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "VBOOST", "2": "GND"})

elements += component("Device:D_Zener", "DZ1", "68V BZT52C68",
    166, 128,
    footprint="Diode_SMD:D_SOD-123",
    pins={"1": "VBOOST", "2": "GND"})

# VBOOST horizontal bus at y=106.65: D2 → Cres1 → DZ1 → L1
# Cres1.stub_end=(150,106.65), L1.stub_end=(188,106.65) already at this y level
elements.append(wire(128.16, 106.65, 188, 106.65)) # VBOOST horizontal bus
elements.append(wire(128.16, 113, 128.16, 106.65))  # D2.pin2 stub_end → bus
elements.append(wire(159.65, 128, 159.65, 106.65))  # DZ1.pin1 stub_end → bus
elements.append(junction(150, 106.65))              # T: bus + Cres1 stub
elements.append(junction(159.65, 106.65))           # T: bus + DZ1 branch

# ── BLOCK H: LC FILTER (x=183..215, y=108..140) ──────────────────────────────

elements += component("Device:L", "L1", "10mH FNR5040S",
    188, 113,
    footprint="Inductor_SMD:L_Changjiang_FNR5040S",
    pins={"1": "VBOOST", "2": "HV_FILT"})

elements += component("Device:C", "C9", "470n 100V X7R",
    204, 128,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "HV_FILT", "2": "GND"})

# HV_FILT: L1.pin2 stub_end (188,119.35) → right → C9.pin1 stub_end (204,121.65)
elements.append(wire(188, 119.35, 204, 119.35))  # horizontal
elements.append(wire(204, 119.35, 204, 121.65))  # down to C9.pin1 stub_end

# ── BLOCK I: UNUSED U3 GATES (x=232, y=165..210) ─────────────────────────────

for _u, _in_pin, _uy in [
    (3, "5",  165),
    (4, "9",  180),
    (5, "11", 195),
    (6, "13", 210),
]:
    elements += component("4xxx:40106", "U3", "CD40106B",
        232, _uy, unit=_u,
        footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
        pins={_in_pin: "GND"})
    elements.append(no_connect(232 + 7.62, _uy))

# ── POWER FLAGS ───────────────────────────────────────────────────────────────

elements.append(power_sym("power:GND",      20, 215))
elements.append(power_sym("power:PWR_FLAG", 33, 215))
elements.append(wire(20, 215, 33, 215))

elements.append(label("V_OPA", 15, 228, 0))
elements.append(wire(15, 228, 33, 228))
elements.append(power_sym("power:PWR_FLAG", 33, 228))

elements.append(label("V_OPA_RAW", 15, 241, 0))
elements.append(wire(15, 241, 33, 241))
elements.append(power_sym("power:PWR_FLAG", 33, 241))

elements.append(label("V_OSC", 15, 254, 0))
elements.append(wire(15, 254, 33, 254))
elements.append(power_sym("power:PWR_FLAG", 33, 254))

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

    schematic = f"""(kicad_sch (version 20230819) (generator kiutils)

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
