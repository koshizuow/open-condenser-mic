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

ROOT_UUID = new_uuid()   # single-sheet uuid

_spath = [f"/{ROOT_UUID}"]   # component instances path (single sheet)

# Base offset for A3 (420×297mm) page.
# Per-section placement is done via _SX, _SY below.
OX, OY = 82.5, 40

# Per-section offset (set before each block group):
#   Audio  (upper-right)  _SX=75-8*1.27=+64.84, _SY=-60
#   Power  (lower-left)   _SX=-80+6*1.27=-72.38, _SY=85-9*1.27=+73.57
#   PWR_FLAGS (upper-left) _SX=-78+6*1.27=-70.38, _SY=-190
# All X/Y shifts are multiples of 1.27 mm (grid unit) to preserve snap alignment.
_SX = 0
_SY = 0


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
    return (f'(wire (pts (xy {_G(x1+OX+_SX):.2f} {_G(y1+OY+_SY):.2f}) (xy {_G(x2+OX+_SX):.2f} {_G(y2+OY+_SY):.2f}))\n'
            f'  (stroke (width 0) (type default))\n'
            f'  (uuid "{new_uuid()}")\n)')


# ── Local net label ───────────────────────────────────────────────────────────
def label(net, x, y, angle=0):
    return (f'(label "{net}" (at {_G(x+OX+_SX):.2f} {_G(y+OY+_SY):.2f} {angle})\n'
            f'  (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'  (uuid "{new_uuid()}")\n)')


def global_label(net, x, y, angle=0, shape="bidirectional"):
    ax, ay = _G(x + OX + _SX), _G(y + OY + _SY)
    # KiCad global_label angle = direction the PIN points (body is opposite).
    # Callers pass angle = direction wire arrives; +180° converts to pin-points direction.
    # Vertical entry labels (wire from below): pass angle=90 → ka=270 (pin down, body up).
    ka = (angle + 180) % 360
    return (f'(global_label "{net}" (shape {shape}) (at {ax:.2f} {ay:.2f} {ka})\n'
            f'  (effects (font (size 1.27 1.27)) (justify right))\n'
            f'  (uuid "{new_uuid()}")\n'
            f'  (property "Intersheet References" "${{INTERSHEET_REFS}}" (at {ax:.2f} {ay:.2f} {ka})\n'
            f'    (effects (font (size 1.27 1.27)) hide)))')


# ── No-connect ────────────────────────────────────────────────────────────────
def no_connect(x, y):
    return f'(no_connect (at {_G(x+OX+_SX):.2f} {_G(y+OY+_SY):.2f}) (uuid "{new_uuid()}"))'


# ── Junction ──────────────────────────────────────────────────────────────────
def junction(x, y):
    return f'(junction (at {_G(x+OX+_SX):.2f} {_G(y+OY+_SY):.2f}) (diameter 0) (color 0 0 0 0) (uuid "{new_uuid()}"))'


# ── Power symbol (GND / +24V etc.) ────────────────────────────────────────────
_pwr_seq = [0]

def power_sym(lib_id, x, y, angle=0):
    _pwr_seq[0] += 1
    ref = f"#PWR{_pwr_seq[0]:04d}"
    short = lib_id.split(":")[1]
    ax, ay = _G(x + OX + _SX), _G(y + OY + _SY)
    # GND graphic extends downward from pin tip; label goes below bars (+3.81).
    # Other power symbols (PWR_FLAG, +24V) label above pin (-2.54).
    val_y = ay + 3.81 if short == "GND" else ay - 2.54
    return (f'(symbol (lib_id "{lib_id}") (at {ax:.2f} {ay:.2f} {angle}) (unit 1)\n'
            f'  (in_bom yes) (on_board yes) (dnp no)\n'
            f'  (uuid "{new_uuid()}")\n'
            f'  (property "Reference" "{ref}" (at {ax:.2f} {ay+2.54:.2f} {angle})\n'
            f'    (effects (font (size 1.27 1.27)) hide))\n'
            f'  (property "Value" "{short}" (at {ax:.2f} {val_y:.2f} {angle})\n'
            f'    (effects (font (size 1.27 1.27))))\n'
            f'  (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'  (instances (project "{PROJECT}" (path "{_spath[0]}" (reference "{ref}") (unit 1))))\n)')


# ── Component symbol instance ──────────────────────────────────────────────────
def sym(lib_id, ref, val, x, y, angle=0, unit=1,
        footprint="", datasheet="", dnp=False,
        extra_props=None, pins=None,
        ref_at=(2.54, -2.54), val_at=(2.54, 1.27)):
    """
    pins: dict of {pin_number: net_name} — generates wire stub + label for each.
    Pin positions are looked up from PIN_OFFSETS below.
    ref_at / val_at: (dx, dy) offset from component centre to text anchor (left-edge of text).
    """
    dnp_str = "yes" if dnp else "no"
    ax, ay = _G(x + OX + _SX), _G(y + OY + _SY)
    lines = [
        f'(symbol (lib_id "{lib_id}") (at {ax:.2f} {ay:.2f} {angle}) (unit {unit})',
        f'  (in_bom yes) (on_board yes) (dnp {dnp_str})',
        f'  (uuid "{new_uuid()}")',
        f'  (property "Reference" "{ref}" (at {_G(ax + ref_at[0]):.2f} {_G(ay + ref_at[1]):.2f} 0)',
        f'    (effects (font (size 1.27 1.27)) (justify left)))',
        f'  (property "Value" "{val}" (at {_G(ax + val_at[0]):.2f} {_G(ay + val_at[1]):.2f} 0)',
        f'    (effects (font (size 1.27 1.27)) (justify left)))',
        f'  (property "Footprint" "{footprint}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
        f'  (property "Datasheet" "{datasheet}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
    ]
    if extra_props:
        for k, v in extra_props.items():
            lines.append(f'  (property "{k}" "{v}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    lines.append(f'  (instances (project "{PROJECT}" (path "{_spath[0]}" (reference "{ref}") (unit {unit}))))')
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
    "GND": {"D": ("power:GND", 0), "R": ("power:GND", 0)},
    # V_OPA is drawn as an explicit bus spine + local wires (see Block A / Block D wires)
}

def stub_and_label(lib_id, cx, cy, pin_num, net_name, angle=0):
    """Return (wire_str, label_or_power_str) for one pin.

    Prefix net_name with '~' to generate the wire stub but suppress the label
    (use when the pin is already identified by an explicit wire to a labeled segment).
    """
    offsets = PIN_OFFSETS.get(lib_id, {})
    if pin_num not in offsets:
        return "", ""
    dx, dy, direction = offsets[pin_num]
    px, py = cx + dx, cy + dy  # pin tip

    show_label = not net_name.startswith("~")
    actual_net = net_name[1:] if not show_label else net_name

    # Power symbol substitution (replaces stub + label)
    pmap = _POWER_SYMBOL_NETS.get(actual_net, {})
    if direction in pmap:
        plib, pangle = pmap[direction]
        return "", power_sym(plib, px, py, pangle)

    # Stub wire + optional label
    if direction == "L":
        lx, ly = px - STUB_LEN, py
        la = 180
    elif direction == "R":
        lx, ly = px + STUB_LEN, py
        la = 180
    elif direction == "U":
        lx, ly = px, py - STUB_LEN
        la = 270
    else:  # D
        lx, ly = px, py + STUB_LEN
        la = 0
    w = wire(px, py, lx, ly)
    lb = label(actual_net, lx, ly, la) if show_label else ""
    return w, lb


def component(lib_id, ref, val, x, y, angle=0, unit=1,
              footprint="", datasheet="", pins=None, dnp=False, extra_props=None,
              ref_at=(2.54, -2.54), val_at=(2.54, 1.27)):
    """Return list of S-expression strings: symbol + wire stubs + labels."""
    parts = [sym(lib_id, ref, val, x, y, angle, unit,
                 footprint, datasheet, dnp, extra_props,
                 ref_at=ref_at, val_at=val_at)]
    if pins:
        for pin_num, net_name in pins.items():
            w, lb = stub_and_label(lib_id, x, y, pin_num, net_name, angle)
            if w:  parts.append(w)
            if lb: parts.append(lb)
    return parts


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMATIC COMPONENTS  (all coords are raw mm, before OX/OY/_SX/_SY offsets)
#
# Layout: audio signal chain (upper-right) | power supply (lower-left)
#   Audio  (Blocks C,D,E) _SX=+64.84 _SY=-60 → schematic x≈158..398, y≈24..97
#   Power  (Blocks A,B,F,G,H) _SX=-72.38 _SY=+73.57 → schematic x≈20..218, y≈117..278
#   PWR_FLAGS (upper-left) _SX=-70.38 _SY=-190 → schematic x≈27..46, y≈22..61
# ─────────────────────────────────────────────────────────────────────────────

elements = []

# ── POWER SECTION ─────────────────────────────────────────────────────────────
_SX = -80 + 6*1.27   # shift right 6 grid units: V_OSC left bus at x≈20mm
_SY = 85 - 9*1.27    # shift up 9 grid units: GND text at y≈278mm

# ── BLOCK A: PHANTOM FEED + VOLTAGE REGULATOR (x=15..80, y=5..48) ────────────
# GND pins (direction D) → power:GND symbols automatically
# V_OPA pins (direction U) → power:+24V symbols automatically

elements += component("Device:R", "R1", "6.8k 0.1%",
    22, 12,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "~XLR_HOT", "2": "V_OPA_RAW"})

elements += component("Device:R", "R2", "6.8k 0.1%",
    22, 31,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "~V_OPA_RAW", "2": "~XLR_COLD"})
# XLR_HOT/COLD: local net labels at stub ends; connect to Block E labels by net name
# R1.pin1 stub_end=(22,5.65) U-direction → angle=180 (text left); R2.pin2 stub_end=(22,37.35) D→angle=180
elements.append(label("XLR_HOT", 22, 5.65, 180))
elements.append(label("XLR_COLD", 22, 37.35, 180))

elements += component("Device:C", "C1", "100n 63V X7R",
    35, 20,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~V_OPA_RAW", "2": "GND"})

# Low-Iq V_OPA supply: R_REG1 biases Z_REG1 (24V zener) → Q1 emitter follower → V_OPA = 23.3V
# Total Iq < 3.5mA at 48V phantom; V_OPA_RAW ≈ 25.8V (vs ~11V with L78L24 at 48V phantom)
elements += component("Device:R", "R_REG1", "2.2k",
    55, 13,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~V_OPA_RAW", "2": "~V_BASE_REG"})

elements += component("Device:D_Zener", "Z_REG1", "24V BZT52C24",
    72, 25,
    footprint="Diode_SMD:D_SOD-123",
    pins={"1": "~V_BASE_REG", "2": "GND"},
    ref_at=(-6, 5.5), val_at=(-6, 8))

# Q1: NPN emitter follower — C=V_OPA_RAW, B=V_BASE_REG (24V zener), E=V_OPA (23.3V out)
elements += component("Device:Q_NPN", "Q1", "MMBT5551",
    85, 20,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"C": "~V_OPA_RAW", "B": "~V_BASE_REG", "E": "~V_OPA"},
    ref_at=(2.54, 10), val_at=(2.54, 12.5))

# V_BASE_REG bus: R_REG1.pin2 stub_end (55,19.35) ─── Q1.B stub_end (77.38,20), all snap to y=59.69
#                 vertical branch at x=65.65 down to Z_REG1.pin1 stub_end (65.65,25)
elements.append(label("V_BASE_REG", 55, 19.35, 180)) # label at bus left endpoint
elements.append(wire(55, 19.35, 65.65, 19.35))     # V_BASE_REG bus seg1
elements.append(wire(65.65, 19.35, 77.38, 19.35))  # V_BASE_REG bus seg2
elements.append(wire(65.65, 19.35, 65.65, 25))
elements.append(junction(65.65, 19.35))

elements += component("Device:C", "C2", "100n 25V X7R",
    99, 14.61,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~V_OPA", "2": "GND"},
    val_at=(2.54, -5.08))

elements += component("Device:C_Polarized", "C5", "10u 25V",
    60, 63,
    footprint="Capacitor_SMD:CP_Elec_4x5.4",
    pins={"1": "~V_MID", "2": "GND"})

elements += component("Device:C_Polarized", "C6", "10u 25V",
    95, 50,
    footprint="Capacitor_SMD:CP_Elec_4x5.4",
    pins={"1": "~V_OPA", "2": "GND"})

# R_ZEN1 + Z_OSC1: y=20 row, V_OPA → R_ZEN1(105) → V_OSC → Z_OSC1(120) → GND
# R_ZEN1.pin1 stub_end (105,13.65) wired back to V_OPA spine at x=92.
# R_ZEN1.pin2 stub_end (105,26.35) wired to Z_OSC1.pin1 stub_end (113.65,20) via V_OSC.
elements += component("Device:R", "R_ZEN1", "6.8k",
    105, 20,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~V_OPA", "2": "~V_OSC"},
    ref_at=(2.54, -5))

elements += component("Device:D_Zener", "Z_OSC1", "15V MMSZ15VT1G",
    125, 20,
    footprint="Diode_SMD:D_SOD-123",
    pins={"1": "~V_OSC", "2": "GND"},
    val_at=(2.54, -5.08))

# V_OPA spine at x=92: C2 tip (top), R_ZEN1 stub branch, Q1.E stub, R4 tip, C6 tip (bottom)
# Q1 at (85,20): E tip=(87.54,25.08), stub_end=(87.54,27.62) → wire right to spine
# R_ZEN1.pin1 stub_end=(105,13.65) → wire left to spine at y=13.65
elements.append(wire(92, 6.99, 92, 8.26))             # stub: corner → junction
elements.append(label("V_OPA", 92, 6.99, 270))        # V_OPA supply-side label (upward)
elements.append(junction(92, 8.26))                   # T: label stub + spine down + C2 right
elements.append(wire(92, 8.26, 99, 8.26))             # C2.pin1 stub_end ← junction
elements.append(wire(92, 8.26, 92, 13.65))            # V_OPA spine seg1: junction → R_ZEN1 branch
elements.append(wire(92, 13.65, 92, 27.62))           # V_OPA spine seg2: R_ZEN1 → Q1.E junction
elements.append(wire(92, 27.62, 92, 43.65))           # V_OPA spine seg3: Q1.E → R4 junction (spine ends here)
elements.append(wire(87.54, 27.62, 92, 27.62))        # Q1.E stub_end → spine
elements.append(wire(72, 43.65, 92, 43.65))           # R4.pin1 stub_end → spine (V_OPA)
elements.append(wire(92, 43.65, 95, 43.65))           # C6.pin1 stub_end ← spine (V_OPA); C6 at (95,50)
elements.append(wire(92, 13.65, 105, 13.65))          # spine → R_ZEN1.pin1 stub_end
elements.append(junction(92, 13.65))                  # T: spine + R_ZEN1 branch
elements.append(junction(92, 27.62))                  # T: spine + Q1.E branch
elements.append(junction(92, 43.65))                  # T: spine end + R4 branch + C6 branch

# V_OPA extension to D1 (Block G pump): physical wire from R4 node (72,43.65) down x=65 to D1.
# D1(88,113) pin1(A,L) tip=(80.38,113), stub_end=(77.84,113)
elements.append(wire(65, 43.65, 72, 43.65))           # extension meets R4 node
elements.append(junction(72, 43.65))                  # T: R4 stub + spine wire + extension
elements.append(wire(65, 43.65, 65, 113))             # down to D1 level (x=65 clears R3/PRES area)
elements.append(wire(65, 113, 77.84, 113))            # right to D1.pin1 stub_end

# V_OSC explicit wire: R_ZEN1.pin2 stub (105,26.35) → Z_OSC1.pin1 stub (113.65,20)
elements.append(wire(105, 26.35, 113.65, 26.35))
elements.append(wire(113.65, 26.35, 113.65, 20))
elements.append(junction(113.65, 20))                 # T: V_OSC wire + V_OSC bus up + Z_OSC1 stub
elements.append(label("V_OSC", 113.65, 20, 180))     # label at junction, text extends left
elements.append(wire(113.65, 20, 118.65, 20))         # junction → Z_OSC1.pin1 stub_end

# V_OPA_RAW: R1.pin2 stub_end ↔ R2.pin1 stub_end
# R1(22,12) pin2(D) stub_end=(22,18.35); R2(22,31) pin1(U) stub_end=(22,24.65)
elements.append(wire(22, 18.35, 22, 24.65))

# T7a: V_OPA_RAW left cluster — connect R1.pin2 tip to C1.pin1 tip with horizontal wire
# R1(22,12) pin2(D) tip=(22,15.81); C1(35,20) pin1(U) tip=(35,16.19)
# After _G both snap to same schematic y; wire runs between the two component bodies
elements.append(wire(22, 15.81, 35, 16.19))

# T7b: V_OPA_RAW bus extend to R_REG1 and Q1
# Bus at y=4 (one grid above C2.pin1 stub_end at y=5.65, avoids accidental V_OPA short)
# C1.pin1 stub_end(35,13.65) → up to y=4 → right to R_REG1(55) and Q1.C(87.54)
elements.append(wire(35, 13.65, 35, 4))       # C1 stub_end up to bus level
elements.append(wire(35, 4, 55, 4))           # bus left segment
elements.append(wire(55, 4, 87.54, 4))        # bus right segment
elements.append(wire(55, 4, 55, 6.65))        # branch down to R_REG1.pin1 stub_end
elements.append(wire(87.54, 4, 87.54, 12.38)) # branch down to Q1.C stub_end

# ── BLOCK B: V_MID VOLTAGE DIVIDER (x=68..90, y=48..88) ─────────────────────

elements += component("Device:R", "R4", "470k",
    72, 50,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~V_OPA", "2": "~V_MID"})

elements += component("Device:R", "R5", "470k",
    72, 75,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~V_MID", "2": "GND"})

# R4.pin2 ↔ R5.pin1 vertical V_MID wire
elements.append(wire(72, 56.35, 72, 68.65))          # R4.pin2 ↔ R5.pin1 (V_MID node)

elements += component("Device:C", "C4", "10u 25V X5R",
    87, 63,
    footprint="Capacitor_SMD:C_0603_1608Metric",
    pins={"1": "~V_MID", "2": "GND"})

# T8a: V_MID bus — C5, C4, and R3 all wired explicitly
# C5(60,63).pin1 stub_end=(60,56.65) and C4(87,63).pin1 stub_end=(87,56.65) snap to same grid y as
# R4.pin2 stub_end(72,56.35) → one horizontal bus at sch_y=96.52
elements.append(wire(60, 56.65, 72, 56.35))          # C5.pin1 stub_end → V_MID bus (R4.pin2 stub_end)
elements.append(wire(72, 56.35, 80, 56.35))          # V_MID horiz seg1: R4.pin2 → R3 branch junction
elements.append(wire(80, 56.35, 87, 56.35))          # V_MID horiz seg2: junction → C4.pin1 stub_end
elements.append(junction(72, 56.35))                 # 3-way: C5 wire + R4.pin2 stub + bus right
elements.append(label("V_MID", 87, 56.35, 0))        # V_MID supply-side label (at C4.pin1 bus end)

# ── AUDIO SECTION ─────────────────────────────────────────────────────────────
_SX = 75 - 8*1.27    # shift left 8 grid units: J3 text at x≈397mm
_SY = -60

# ── BLOCK C: HV BIAS CHAIN + CAPSULE + AC COUPLING (x=20..58, y=48..95) ──────

elements += component("Device:R", "R_GBIAS1", "100M 200V 1206",
    30, 57,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "~HV_FILT", "2": "CAP_FP"},
    ref_at=(-13, -2.54), val_at=(-18, 1.27))
elements.append(wire(30, 50.65, 10, 50.65))               # stub left to label
elements.append(label("HV_FILT", 10, 50.65, 180))         # HV_FILT net label (connects to power Block H)

elements += component("Connector_Generic:Conn_01x02", "J2", "CAPSULE",
    50, 44,
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    pins={"1": "~CAP_FP", "2": "~V_MID"})

elements += component("Device:C", "C8", "1n 100V C0G 0402",
    50, 70,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~CAP_FP", "2": "~VPLUS"},
    val_at=(2.54, 3.81))

elements += component("Device:R", "R_BIAS1", "100M 1206",
    50, 83,
    footprint="Resistor_SMD:R_1206_3216Metric",
    pins={"1": "~VPLUS", "2": "~V_MID"},
    val_at=(2.54, -6))

# V_MID audio bus: net label connects to power Block B.
# Serves R3.pin1, R_PRES1.pin1 (Block D), R_BIAS1.pin2, J2.pin2 (Block C).
elements.append(label("V_MID", 70, 83, 180))              # V_MID net label (connects to power Block B)
elements.append(wire(80, 77.65, 92, 77.65))              # right to R3.pin1 stub_end
elements.append(wire(80, 77.65, 80, 83))                 # down to R_PRES1 level
elements.append(wire(80, 83, 70, 83))                    # left bus extended to label AT
elements.append(wire(77, 83, 53, 83))                    # continue left to J2 branch junction
elements.append(wire(53, 83, 53, 89.35))                 # down to R_BIAS1.pin2 level
elements.append(wire(53, 89.35, 50, 89.35))              # left to R_BIAS1.pin2 stub_end
elements.append(junction(77, 83))                        # T: horizontal bus + R_PRES1.pin1 stub_end

# CAP_FP bus at x=36: J2.pin1 + C8.pin1 + R_GBIAS1.pin2 all physically wired.
# J2(50,44) pin1 stub L→(42.38,44); C8(50,70) pin1 stub U→(50,63.65); R_GBIAS1(30,58) pin2 stub D→(30,64.35)
# R_GBIAS1 at y=58 so pin2 stub end snaps to same schematic row as C8 stub end — direct rightward wire.
elements.append(label("CAP_FP", 36, 44, 180))     # label at bus top
elements.append(wire(36, 44, 36, 63.65))          # CAP_FP bus (top to C8/R_GBIAS1 level)
elements.append(wire(42.38, 44, 36, 44))          # J2.pin1 stub_end → bus top
elements.append(junction(36, 63.65))              # 3-way junction: bus bottom + C8 + R_GBIAS1 wires
elements.append(wire(50, 63.65, 36, 63.65))       # C8.pin1 stub_end → junction
elements.append(wire(30, 63.35, 36, 63.65))       # R_GBIAS1.pin2 stub_end → junction (same sch row)
# J2.pin2 (~V_MID): stub_end=(42.38,46.54) → left → down at x=38 → right to V_MID bus at (53,83)
elements.append(wire(42.38, 46.54, 38, 46.54))
elements.append(wire(38, 46.54, 38, 83))
elements.append(wire(38, 83, 53, 83))
elements.append(junction(53, 83))

# VPLUS node: C8.pin2 → R_BIAS1.pin1 meeting at junction (50,76.35)=sch(132.08,116.84)
# C8(50,70) pin2 tip=(50,73.81) stub→(50,76.35); R_BIAS1(50,83) pin1 tip=(50,79.19) stub→(50,76.35)
# Both stubs meet at the same junction; then horizontal bus right to U1.IN+
elements.append(wire(50, 73.81, 50, 76.35))      # VPLUS seg1: C8.pin2 tip → junction
elements.append(wire(50, 76.35, 50, 79.19))      # VPLUS seg2: junction → R_BIAS1.pin1 tip
elements.append(wire(50, 76.35, 111.84, 76.35))  # horizontal to U1.IN+ column
elements.append(label("VPLUS", 111.84, 76.35, 270))  # label at L-corner, rotated 90°
elements.append(wire(111.84, 76.35, 111.84, 64.46))  # up to U1.IN+ stub_end
elements.append(junction(50, 76.35))             # T: vertical VPLUS + horizontal

# ── BLOCK D: OPA1641 SIGNAL STAGE (x=88..172, y=48..102) ────────────────────

elements += component("Device:R", "R3", "2.2k",
    92, 84,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~V_MID", "2": "~VINV"})

# Presence-peak network: Rs (6.2k) + C (12nF) in series, parallel with R3.
# At DC: C blocks → Z = R3 = 2.2k (gain unchanged).
# At HF: C shorts → Z = R3‖Rs = 1.61k → +2.6 dB above f_c = 1/(2π×6.2k×12nF) ≈ 2.1 kHz.
# Placed at x=77, left of R3, clear of VPLUS wire (y=76.35) and all Block B components.
elements += component("Device:R", "R_PRES1", "6.2k",
    77, 90,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~V_MID", "2": "~RS_MID"})

elements += component("Device:C", "C_PRES1", "12n 25V X7R",
    77, 110,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~RS_MID", "2": "~VINV"},
    val_at=(2.54, -5.08))

# RS_MID: R_PRES1.pin2 stub_end(77,96.35) → C_PRES1.pin1 stub_end(77,103.65)
# C_PRES1 moved to y=110 so pin2 tip snaps away from D1.pin1 stub_end (both were at sch 160.02,152.4)
elements.append(wire(77, 96.35, 77, 103.65))

elements += component("Device:R", "R6", "5.6k",
    107, 52,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~SIG_OUT", "2": "VINV"})

# U1: OPA1641; GND(pin4,D)→GND sym automatically; V_OPA connected via local wire below
elements += component("Amplifier_Operational:OPA1641", "U1", "OPA1641",
    122, 67,
    footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    pins={"3": "~VPLUS", "2": "~VINV", "6": "SIG_OUT", "7": "~V_OPA", "4": "GND"},
    ref_at=(10, 4), val_at=(10, 6.5))

elements += component("Device:C", "C3", "100n 25V X7R",
    113, 83,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~V_OPA", "2": "GND"})

elements += component("Device:R", "R7", "100R",
    143, 64,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~SIG_OUT", "2": "~SIG_PROT"})

elements += component("Device:C", "C7", "4.7u 50V X7R 1206",
    159, 58,
    footprint="Capacitor_SMD:C_1206_3216Metric",
    pins={"1": "~SIG_PROT", "2": "~TX_DRV"},
    val_at=(0, -5))

# VINV node: R6.pin2 → vertical bus → R3.pin2 branch + U1.IN− branch
# R6(107,52) pin2 tip=(107,55.81) stub D→(107,58.35)
# R3(92,84) pin2 tip=(92,87.81) stub D→(92,90.35)   [VINV,D → NOT GND, keeps stub]
# U1(122,67) IN− tip=(114.38,69.54) stub L→(111.84,69.54)
elements.append(wire(107, 58.35, 107, 69.54))    # VINV bus seg1: R6.pin2 → U1.IN− junction
elements.append(wire(107, 69.54, 107, 90.35))    # VINV bus seg2: U1.IN− → R3 junction
elements.append(wire(107, 90.35, 107, 116.35))   # VINV bus seg3: R3 → C_PRES1.pin2
elements.append(wire(92, 90.35, 107, 90.35))     # R3.pin2 stub_end → right to bus
elements.append(wire(107, 69.54, 111.84, 69.54)) # bus → U1.IN− stub_end
elements.append(wire(77, 116.35, 107, 116.35))   # C_PRES1.pin2 stub_end → bus bottom
elements.append(junction(107, 69.54))            # T: bus + U1.IN− branch
elements.append(junction(107, 90.35))            # T: bus + R3 branch

# SIG_OUT node: U1.OUT → feedback arc to R6.pin1 + output to R7.pin1
# U1(122,67) OUT tip=(129.62,67) stub R→(132.16,67)
# R6(107,52) pin1 tip=(107,48.19) stub U→(107,45.65)
# R7(143,64) pin1 tip=(143,60.19) stub U→(143,57.65)
elements.append(wire(132.16, 67, 132.16, 57.65))    # U1.OUT stub up to R7-branch junction
elements.append(wire(132.16, 57.65, 132.16, 45.65)) # continue up to R6.pin1 level
elements.append(wire(132.16, 45.65, 107, 45.65))    # left to R6.pin1 stub_end (feedback)
elements.append(wire(132.16, 57.65, 143, 57.65))    # right to R7.pin1 stub_end (SIG_OUT)
elements.append(junction(132.16, 57.65))             # T: feedback up + R7 branch right

# SIG_PROT: R7.pin2 stub_end → up between R7 and C7 → C7.pin1 stub_end
# R7(143,64) pin2 stub D→(143,70.35); C7(159,58) pin1 stub U→(159,51.65)
elements.append(label("SIG_PROT", 143, 70.35, 0))   # label at R7.pin2 stub_end
elements.append(wire(143, 70.35, 155, 70.35))        # right to turn between R7 and C7
elements.append(wire(155, 70.35, 155, 51.65))        # up to C7.pin1 level
elements.append(wire(155, 51.65, 159, 51.65))        # right to C7.pin1 stub_end

# V_OPA local: junction at U1.V+ stub_end; short stub up to label; C3 branches left.
elements.append(wire(119.46, 56.84, 119.46, 54.30))  # short stub up to label
elements.append(label("V_OPA", 119.46, 54.30, 270))   # V_OPA net label (connects to power Block A spine)
elements.append(wire(119.46, 56.84, 113, 56.84))      # junction → left to C3 branch
elements.append(wire(113, 56.84, 113, 76.65))         # down to C3.pin1 stub_end
elements.append(junction(119.46, 56.84))               # T: U1.V+ stub + label stub + C3 branch

# ── BLOCK E: TRANSFORMER + XLR OUTPUT (x=178..230, y=55..78) ─────────────────

elements += component("Connector_Generic:Conn_01x03", "TP1", "NTE10/3_PRI",
    178, 63,
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    pins={"1": "~TX_DRV", "2": "~GND"},
    val_at=(2.54, -5))
elements.append(no_connect(172.92, 65.54))  # S3 pin tip: far end of secondary winding, leave floating
# TP1.pin2 GND: L-shape down from stub_end, then GND power symbol
# stub_end=(170.38,63) → down to y=68 → GND symbol
elements.append(wire(170.38, 63, 170.38, 68))
elements.append(power_sym("power:GND", 170.38, 68, 0))

elements += component("Connector_Generic:Conn_01x02", "TS1", "NTE10/3_SEC",
    196, 63,
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    pins={"1": "~XLR_HOT", "2": "~XLR_COLD"},
    val_at=(2.54, 4))

elements += component("Connector_Generic:Conn_01x03", "J3", "XLR_OUT",
    247, 67,
    footprint="",
    pins={"1": "~GND", "2": "~XLR_HOT_F", "3": "~XLR_COLD_F"})
# J3.pin1 GND: L-shape UP from stub_end (239.38,64.46) → left → GND symbol
# Going up avoids pin2/pin3 stubs which are below pin1 at the same x
elements.append(wire(239.38, 64.46, 239.38, 57))
elements.append(wire(239.38, 57, 235, 57))
elements.append(power_sym("power:GND", 235, 57, 0))

# RFI filter: 100R series + 100pF C0G shunt on each XLR leg (fc ~16 MHz)
# Placed between TS1 and J3 so signal flow reads left-to-right: TS1→R_RFI→C_RFI→J3
elements += component("Device:R", "R_RFI1", "100R",
    210, 58,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~XLR_HOT", "2": "~XLR_HOT_F"})

elements += component("Device:C", "C_RFI1", "100p C0G",
    222, 54,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~XLR_HOT_F", "2": "GND"})

elements += component("Device:R", "R_RFI2", "100R",
    210, 76,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~XLR_COLD", "2": "~XLR_COLD_F"})

elements += component("Device:C", "C_RFI2", "100p C0G",
    222, 76,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~XLR_COLD_F", "2": "GND"})

# TX_DRV: C7.pin2 stub_end (159,64.35) → TP1.pin1 stub_end (170.38,60.46)
# C7(159,58) pin2(D) stub_end=(159,64.35); TP1(178,63) pin1(L) stub_end=(170.38,60.46)
# Route via x=164 to avoid crossing TP1.pin2 GND stub_end at (170.38,63)
# Label at L-corner (164,60.46): text extends left, clear of TP1 pin area
elements.append(wire(159, 64.35, 164, 64.35))
elements.append(wire(164, 64.35, 164, 60.46))
elements.append(wire(164, 60.46, 170.38, 60.46))
elements.append(label("TX_DRV", 164, 60.46, 180))

# T9b: XLR explicit wires — HOT leg
# TS1(196,63).pin1 L-stub_end=(188.38,63) → R_RFI1(210,58).pin1 U-stub_end=(210,51.65)
# Route: up from TS1 stub_end to R_RFI1 stub level, then horizontal right.
elements.append(wire(188.38, 63, 188.38, 51.65))     # TS1.pin1 stub_end up to R_RFI1 row
elements.append(junction(188.38, 51.65))              # T: TS1 stub + bus right + label stub left
elements.append(wire(188.38, 51.65, 178, 51.65))      # label stub left
elements.append(label("XLR_HOT", 178, 51.65, 180))    # XLR_HOT net label (connects to power Block A R1)
elements.append(wire(188.38, 51.65, 210, 51.65))      # XLR_HOT bus: TS1 junction → R_RFI1.pin1 stub_end
# XLR_HOT_F bus at x=216 (avoids C_RFI1.pin2 GND stub_end at (222,64.35) same y as R_RFI1.pin2)
# R_RFI1.pin2 D-stub_end=(210,64.35), C_RFI1.pin1 U-stub_end=(222,51.65), J3.pin2 L-stub_end=(239.38,67)
elements.append(wire(210, 64.35, 216, 64.35))         # R_RFI1.pin2 stub_end → bus
elements.append(wire(216, 64.35, 216, 47.65))         # bus up to C_RFI1.pin1 level
elements.append(wire(216, 47.65, 222, 47.65))         # to C_RFI1.pin1 stub_end
elements.append(wire(216, 64.35, 216, 67))            # bus down to J3.pin2 level
elements.append(wire(216, 67, 239.38, 67))            # to J3.pin2 stub_end
elements.append(junction(216, 64.35))                 # T: R_RFI1 tap + bus up + bus down
elements.append(label("XLR_HOT_F", 216, 67, 180))    # label at approach left endpoint (L-corner)

# T9b: XLR explicit wires — COLD leg
# TS1(196,63).pin2 L-stub_end=(188.38,65.54) → R_RFI2(210,76).pin1 U-stub_end=(210,69.65)
elements.append(wire(188.38, 65.54, 188.38, 69.65))  # TS1.pin2 stub_end down to R_RFI2 row
elements.append(junction(188.38, 69.65))              # T: TS1 stub + bus right + label stub left
elements.append(wire(188.38, 69.65, 178, 69.65))      # label stub left
elements.append(label("XLR_COLD", 178, 69.65, 180))   # XLR_COLD net label (connects to power Block A R2)
elements.append(wire(188.38, 69.65, 210, 69.65))      # XLR_COLD bus: TS1 junction → R_RFI2.pin1 stub_end
# XLR_COLD_F bus at x=216
# R_RFI2.pin2 D-stub_end=(210,82.35), C_RFI2.pin1 U-stub_end=(222,69.65), J3.pin3 L-stub_end=(239.38,69.54)
# Split into two segments so junction is at an endpoint, not interior — interior junction causes KiCad ERC
# to flag the label at J3.pin3 stub_end as dangling even when the wire endpoint is correct.
elements.append(wire(210, 82.35, 216, 82.35))         # R_RFI2.pin2 stub_end → bus
elements.append(wire(216, 82.35, 216, 69.65))         # bus up to C_RFI2/J3 level
elements.append(wire(216, 69.65, 222, 69.65))         # bus → C_RFI2.pin1 stub_end
elements.append(wire(222, 69.54, 239.38, 69.54))      # approach: C_RFI2 → J3.pin3 (separate segment)
elements.append(junction(222, 69.65))                 # 3-way: bus end + C_RFI2 stub + approach start
elements.append(label("XLR_COLD_F", 222, 69.54, 180)) # label at approach left endpoint (junction)

# ── POWER SECTION (continues) ─────────────────────────────────────────────────
_SX = -80 + 6*1.27
_SY = 85 - 9*1.27

# ── BLOCK F: SCHMITT OSCILLATOR (x=15..67, y=108..160) ───────────────────────

elements += component("4xxx:40106", "U3", "CD40106B",
    28, 118, unit=1,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"1": "~CLKA_IN", "2": "CLKA"})

elements += component("4xxx:40106", "U3", "CD40106B",
    52, 118, unit=2,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"3": "~CLKA", "4": "CLKB"})

elements += component("4xxx:40106", "U3", "CD40106B",
    28, 148, unit=7,
    footprint="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    pins={"14": "~V_OSC", "7": "GND"},
    ref_at=(-5, -2.54), val_at=(-5, 1.27))

elements += component("Device:R", "R_OSC1", "47k",
    40, 106,
    footprint="Resistor_SMD:R_0402_1005Metric",
    pins={"1": "~CLKA", "2": "~CLKA_IN"})

# R_OSC1(40,106): pin1(CLKA,U) tip=(40,102.19) stub→(40,99.65)
#                 pin2(CLKA_IN,D) tip=(40,109.81) stub→(40,112.35)
# C10(40,125): pin1(CLKA_IN,U) tip=(40,121.19) stub→(40,118.65)
#              pin2(GND,D) auto
elements += component("Device:C", "C10", "100p C0G",
    40, 125,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~CLKA_IN", "2": "GND"})

# R_OSC1↔C10 CLKA_IN vertical wire
elements.append(wire(40, 112.35, 40, 118.65))

# CLKA horizontal bus: U3A(28,118).pin2 stub(38.16,118) ↔ U3B(52,118).pin3 stub(41.84,118)
# CLKA branch routes via x=44 (L-shape) so it does not pass through CLKA_IN junction at (40,112.35)
# or the CLKA_IN vertical at (40,118); CLKA and CLKA_IN are thus physically separate nets.
elements.append(wire(38.16, 118, 41.84, 118))  # CLKA bus U3A→U3B
elements.append(wire(41.84, 118, 44, 118))      # extend bus to branch point
elements.append(wire(44, 118, 44, 99.65))       # CLKA branch up at x=44
elements.append(wire(44, 99.65, 40, 99.65))     # connect to R_OSC1.pin1 stub_end

# CLKA_IN feedback: R_OSC1.pin2 stub (40,112.35) → left → down to U3A.pin1 stub (17.84,118)
# horizontal at y=112.35 is above gate bodies (gates at y=118, body top ≈ y=114)
elements.append(wire(40, 112.35, 17.84, 112.35))
elements.append(label("CLKA_IN", 17.84, 112.35, 180))  # at L-corner before bend down
elements.append(wire(17.84, 112.35, 17.84, 118))
elements.append(junction(40, 112.35))

elements += component("Device:C", "C_U3", "100n 25V X7R",
    38, 140,
    footprint="Capacitor_SMD:C_0402_1005Metric",
    pins={"1": "~V_OSC", "2": "GND"})

# V_OSC local wire: U3G.pin14 stub_end (28,132.76) → C_U3.pin1 stub_end (38,133.65)
elements.append(wire(28, 132.76, 38, 132.76))
elements.append(wire(38, 132.76, 38, 133.65))

# T10: V_OSC long bus — connect R_ZEN1/Z_OSC1 node (113.65,20) to U3G/C_U3 node (28,132.76)
# Route: up from junction(113.65,20) to y=3 (above V_OPA_RAW bus at y=4 and spine top at y=8.19),
# left along top margin at x=10 (clear of all components at x≥15),
# down left margin to U3G.pin14 level, then right to stub_end.
elements.append(wire(113.65, 20, 113.65, 3))      # up from Z_OSC1 junction to top margin
elements.append(wire(113.65, 3, 10, 3))           # left along top margin (y=3 clears spine+bus)
elements.append(wire(10, 3, 10, 132.76))          # down left margin (x=10 left of all components)
elements.append(wire(10, 132.76, 28, 132.76))     # right to U3G.pin14 stub_end
elements.append(junction(28, 132.76))             # T: bus + existing C_U3 local wire + U3G stub

# ── BLOCK G: DICKSON CHARGE PUMP (x=82..180, y=108..150) ─────────────────────

elements += component("Diode:BAT54S", "D1", "BAT54S",
    88, 113,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"1": "~V_OPA", "3": "N1", "2": "N2"},
    val_at=(2.54, 2.54))

elements += component("Diode:BAT54S", "D2", "BAT54S",
    118, 113,
    footprint="Package_TO_SOT_SMD:SOT-23",
    pins={"1": "~N2", "3": "N3", "2": "~VBOOST"},
    val_at=(2.54, 2.54))

elements += component("Device:C", "Cp1", "100n 100V X7R",
    88, 133,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "~N1", "2": "CLKA"},
    val_at=(-1, -5.08))

elements += component("Device:C", "Cp2", "100n 100V X7R",
    103, 133,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "~N2", "2": "~CLKB"},
    val_at=(2.54, -5.08))

elements += component("Device:C", "Cp3", "100n 100V X7R",
    118, 133,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "~N3", "2": "~CLKA"},
    val_at=(6, -5.08))

# N1: D1.pin3(COM,D) stub_end(88,120.62) → Cp1.pin1(N1,U) stub_end(88,126.65)
elements.append(wire(88, 120.62, 88, 126.65))

# N2: D1.pin2(K,R) stub_end(98.16,113) ↔ D2.pin1(A,L) stub_end(107.84,113)
#     branch at x=103 down to Cp2.pin1(N2,U) stub_end(103,126.65)
elements.append(wire(98.16, 113, 103, 113))        # N2 horiz seg1: D1.pin2 → branch junction
elements.append(wire(103, 113, 107.84, 113))       # N2 horiz seg2: junction → D2.pin1
elements.append(wire(103, 113, 103, 126.65))
elements.append(junction(103, 113))

# N3: D2.pin3(COM,D) stub_end(118,120.62) → Cp3.pin1(N3,U) stub_end(118,126.65)
elements.append(wire(118, 120.62, 118, 126.65))

# CLKA pump bus at y=145: connects Cp1.pin2(88,139.35) and Cp3.pin2(118,139.35)
# Cp2.pin2(CLKB) stub at (103,139.35) is between them — bus routed below to avoid crossing CLKB
elements.append(wire(88, 139.35, 88, 145))
elements.append(wire(118, 139.35, 118, 145))
elements.append(wire(88, 145, 118, 145))

# CLKB explicit wire: U3B.pin4 stub_end (62.16,118) → Cp2.pin2 stub_end (103,139.35)
# Routes below pump CLKA bus (y=145) at y=155 to avoid crossing N1/CLKA wires inside pump.
# U3B at (52,118): pin4(R) tip=(59.62,118), stub_end=(62.16,118)
elements.append(wire(62.16, 118, 62.16, 155))
elements.append(wire(62.16, 155, 103, 155))
elements.append(wire(103, 155, 103, 139.35))

elements += component("Device:C", "Cres1", "470n 100V X7R",
    150, 113,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "~VBOOST", "2": "GND"})

elements += component("Device:D_Zener", "DZ1", "68V BZT52C68",
    166, 128,
    footprint="Diode_SMD:D_SOD-123",
    pins={"1": "~VBOOST", "2": "GND"},
    val_at=(2.54, -5.08))

# VBOOST horizontal bus at y=106.65: D2 → Cres1 → DZ1 → L1
# Cres1.stub_end=(150,106.65), L1.stub_end=(188,106.65) already at this y level
elements.append(wire(128.16, 106.65, 150, 106.65))  # VBOOST bus seg1: D2 → Cres1 junction
elements.append(wire(150, 106.65, 159.65, 106.65)) # VBOOST bus seg2: Cres1 → DZ1 junction
elements.append(wire(159.65, 106.65, 188, 106.65)) # VBOOST bus seg3: DZ1 → L1
elements.append(wire(128.16, 113, 128.16, 106.65))  # D2.pin2 stub_end → bus
elements.append(wire(159.65, 128, 159.65, 106.65))  # DZ1.pin1 stub_end → bus
elements.append(junction(150, 106.65))              # T: bus + Cres1 stub
elements.append(junction(159.65, 106.65))           # T: bus + DZ1 branch

# ── BLOCK H: RC HV FILTER (x=183..215, y=108..140) ───────────────────────────

elements += component("Device:R", "R_HV", "1M 75V 0603",
    188, 113,
    footprint="Resistor_SMD:R_0603_1608Metric",
    pins={"1": "~VBOOST", "2": "~HV_FILT"})
elements.append(label("VBOOST", 150, 106.65, 180))  # horizontal label at left junction dot

elements += component("Device:C", "C9", "470n 100V X7R",
    204, 128,
    footprint="Capacitor_SMD:C_0805_2012Metric",
    pins={"1": "~HV_FILT", "2": "GND"})

# HV_FILT local wire: R_HV.pin2 stub_end (188,119.35) → C9.pin1 stub_end (204,121.65)
elements.append(wire(188, 119.35, 204, 119.35))  # horizontal
elements.append(wire(204, 119.35, 204, 121.65))  # down to C9.pin1 stub_end

# HV_FILT net label at R_HV.pin2 stub_end; connects to audio Block C R_GBIAS1.pin1 via net name.
elements.append(wire(180, 119.35, 188, 119.35))   # short segment left for label
elements.append(label("HV_FILT", 180, 119.35, 180))  # HV_FILT supply-side label
elements.append(junction(188, 119.35))            # T: label wire + C9 wire + R_HV.pin2 stub

# ── POWER FLAGS (upper-left area, x≈27–46mm y≈22–61mm) ───────────────────────
_SX = -78 + 6*1.27   # same x as before
_SY = -190

elements.append(power_sym("power:GND",      20, 172))
elements.append(power_sym("power:PWR_FLAG", 33, 172))
elements.append(wire(20, 172, 33, 172))

elements.append(label("V_OPA", 15, 185, 0))
elements.append(wire(15, 185, 33, 185))
elements.append(power_sym("power:PWR_FLAG", 33, 185))

elements.append(label("V_OPA_RAW", 15, 198, 0))
elements.append(wire(15, 198, 33, 198))
elements.append(power_sym("power:PWR_FLAG", 33, 198))

elements.append(label("V_OSC", 15, 211, 0))
elements.append(wire(15, 211, 33, 211))
elements.append(power_sym("power:PWR_FLAG", 33, 211))

# ─────────────────────────────────────────────────────────────────────────────
# ASSEMBLE AND WRITE
# ─────────────────────────────────────────────────────────────────────────────
def _body(elist):
    lines = []
    for e in elist:
        if isinstance(e, str):
            lines.append(e)
        elif isinstance(e, list):
            lines.extend(e)
    return "\n\n".join(lines)


def main():
    os.makedirs("pcb", exist_ok=True)

    body = _body(elements)

    schematic = f"""(kicad_sch (version 20230819) (generator kiutils)

  (uuid "{ROOT_UUID}")

  (paper "A3")

  {lib_symbols_section()}

{body}

  (sheet_instances (path "/" (page "1")))

)
"""
    with open(OUT, "w") as f:
        f.write(schematic)
    n_comp = schematic.count("(lib_id ")
    print(f"Written: {OUT}  ({n_comp} component instances)")


if __name__ == "__main__":
    main()
