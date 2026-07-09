#!/usr/bin/env python3
"""
Generate <name>.kicad_pcb using pcbnew Python API (KiCad 7).

Usage:
    python gen_pcb.py [--name PROJECT_NAME]

Board: 36x93mm, 2-layer, y=0 at capsule end (top), y=93 at XLR (bottom).
Transformer cutout: x=11..26, y=68.5..75.5 (body 14x6mm + 0.5mm per side).
Mount holes: (6,5),(34,5),(6,85),(34,85) M2.5 28mm span; zip-tie (8,72),(31,72) M3.

Routing is fully scripted (reproducible):
  - HV nets (VBOOST, HV_FILT, HV_MID, CAP_FP): 0.4mm width
  - Power nets (V_OPA, V_MID, V_OSC, PHANTOM, V_OPA_RAW): 0.3mm width
  - Signal/clock nets: 0.2mm width
  - GND: B.Cu zone + vias at each SMD GND pad; no F.Cu GND star
  - Capsule zone (y<17): B.Cu GND only, no F.Cu pour
"""

import argparse
import os, sys
import pcbnew

MM = pcbnew.FromMM

MX = pcbnew.FromMM
MY = pcbnew.FromMM
FP_LIB = "/usr/share/kicad/footprints"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _parse_args():
    p = argparse.ArgumentParser(description="Generate KiCad PCB file.")
    p.add_argument("--name", default="open-condenser-mic", help="Project name (default: open-condenser-mic)")
    return p.parse_args()

OUT = os.path.join(_SCRIPT_DIR, f"{_parse_args().name}.kicad_pcb")


def fp_load(lib_dir: str, name: str) -> pcbnew.FOOTPRINT:
    io = pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    path = os.path.join(FP_LIB, f"{lib_dir}.pretty")
    fp = io.FootprintLoad(path, name)
    if fp is None:
        raise FileNotFoundError(f"Footprint not found: {lib_dir}:{name}")
    return fp


def add_outline_rect(board: pcbnew.BOARD, x0, y0, x1, y1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pcbnew.VECTOR2I(MX(x0), MY(y0)))
    s.SetEnd(pcbnew.VECTOR2I(MX(x1), MY(y1)))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(MM(0.05))
    board.Add(s)


def get_or_create_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    netinfo = board.GetNetInfo()
    net = netinfo.GetNetItem(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        net = board.GetNetInfo().GetNetItem(name)
    return net


def place(board: pcbnew.BOARD,
          lib_dir: str, fp_name: str,
          ref: str, val: str,
          x_mm: float, y_mm: float,
          angle_deg: float = 0,
          pad_nets: dict = None):
    fp = fp_load(lib_dir, fp_name)
    fp.SetReference(ref)
    fp.SetValue(val)
    fp.SetPosition(pcbnew.VECTOR2I(MX(x_mm), MY(y_mm)))
    fp.SetOrientationDegrees(angle_deg)
    fp.SetLayer(pcbnew.F_Cu)
    fp.SetFPIDAsString(f"{lib_dir}:{fp_name}")
    board.Add(fp)

    if pad_nets:
        for pad in fp.Pads():
            pnum = pad.GetNumber()
            if pnum in pad_nets:
                net = get_or_create_net(board, pad_nets[pnum])
                pad.SetNet(net)

    return fp


def place_solder_pads(board: pcbnew.BOARD,
                      ref_base: str,
                      x_mm: float, y_mm: float,
                      nets: list,
                      axis: str = 'y',
                      pitch_mm: float = 2.54):
    """Place N bare THT solder pads at pitch_mm spacing.
    axis='y': pads step downward (default). axis='x': pads step rightward.
    Uses TestPoint_THTPad_D1.5mm_Drill0.7mm, courtyard stripped."""
    for i, net_name in enumerate(nets):
        px = x_mm + (i * pitch_mm if axis == 'x' else 0)
        py = y_mm + (i * pitch_mm if axis == 'y' else 0)
        ref = f"{ref_base}.{i + 1}"
        fp = fp_load("TestPoint", "TestPoint_THTPad_D1.5mm_Drill0.7mm")
        for item in list(fp.GraphicalItems()):
            if item.GetLayer() == pcbnew.F_CrtYd:
                fp.Remove(item)
        fp.SetReference(ref)
        fp.SetValue("")
        fp.SetPosition(pcbnew.VECTOR2I(MX(px), MY(py)))
        fp.SetOrientationDegrees(0)
        fp.SetLayer(pcbnew.F_Cu)
        fp.SetFPIDAsString("TestPoint:TestPoint_THTPad_D1.5mm_Drill0.7mm")
        board.Add(fp)
        if net_name:
            for pad in fp.Pads():
                net = get_or_create_net(board, net_name)
                pad.SetNet(net)


# ── Routing helpers ───────────────────────────────────────────────────────────

def get_pad_xy(board, ref, pad_num):
    """Return (x_mm, y_mm) of a pad by reference and pad number string."""
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            for pad in fp.Pads():
                if pad.GetNumber() == str(pad_num):
                    p = pad.GetPosition()
                    return p.x / 1e6, p.y / 1e6
    raise ValueError(f"Pad not found: {ref}.{pad_num}")


def seg(board, net_name, layer, w_mm, x1, y1, x2, y2):
    """Add a single copper track segment."""
    net = board.FindNet(net_name)
    t = pcbnew.PCB_TRACK(board)
    t.SetNet(net)
    t.SetLayer(layer)
    t.SetWidth(MM(w_mm))
    t.SetStart(pcbnew.VECTOR2I(MX(x1), MY(y1)))
    t.SetEnd(pcbnew.VECTOR2I(MX(x2), MY(y2)))
    board.Add(t)


def route(board, net_name, layer, w_mm, *pts):
    """Route a polyline through pts=[(x,y),...] on given layer."""
    for i in range(len(pts) - 1):
        seg(board, net_name, layer, w_mm, pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])


def via(board, net_name, x_mm, y_mm, drill_mm=0.3, size_mm=0.6):
    """Add a through-hole via."""
    net = board.FindNet(net_name)
    v = pcbnew.PCB_VIA(board)
    v.SetNet(net)
    v.SetPosition(pcbnew.VECTOR2I(MX(x_mm), MY(y_mm)))
    v.SetDrill(MM(drill_mm))
    v.SetWidth(MM(size_mm))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(v)


def add_zone(board, net_name, layer, pts_mm, clearance_mm=0.2, min_width_mm=0.2):
    """Add a filled copper zone with polygon outline pts_mm=[(x,y),...]."""
    net = board.FindNet(net_name)
    z = pcbnew.ZONE(board)
    z.SetNet(net)
    z.SetLayer(layer)
    z.SetLocalClearance(MM(clearance_mm))
    z.SetMinThickness(MM(min_width_mm))
    z.SetIsFilled(False)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in pts_mm:
        outline.Append(MX(x), MY(y))
    board.Add(z)
    return z


def add_keepout(board, layer, pts_mm):
    """Add a Rule Area that blocks copper pour on the given layer.

    Tracks, vias, and pads inside the keepout are still allowed.
    Use for high-Z nodes where GND copper causes leakage or stray capacitance.
    """
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowCopperPour(True)
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetLayer(layer)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in pts_mm:
        outline.Append(MX(x), MY(y))
    board.Add(z)
    return z


def route_all(board):
    F = pcbnew.F_Cu
    B = pcbnew.B_Cu

    # Width constants
    HV  = 0.4
    PWR = 0.3
    SIG = 0.2

    # ── GND: F.Cu zone + B.Cu zone (full plane) + 6 stitching vias ─────────
    # F.Cu GND zone connects all SMD GND pads directly — no per-pad vias needed.
    # Stitching vias tie F.Cu and B.Cu GND together at corners and mid-board.
    # Both zones use 0.3mm clearance from other nets.
    # F.Cu GND zone starts at y=17: no copper above that line.
    # The capsule zone (y<17) has B.Cu GND plane only; no F.Cu pour.
    add_zone(board, "GND", F,
             [(2,17),(38,17),(38,93),(2,93)],
             clearance_mm=0.3)
    add_zone(board, "GND", B,
             [(2,0),(38,0),(38,93),(2,93)],
             clearance_mm=0.3)
    for vx, vy in [(3,18),(36,18),(3,40),(36,40),(3,60),(36,60),(3,91),(37,91)]:
        via(board, "GND", vx, vy)
    # Extra via inside isolated Island 0 (CLKA L-shape cuts off C_OSC.2 from main zone).
    # Connects Island 0 F.Cu fill to B.Cu GND plane.
    via(board, "GND", 18.5, 53)
    # Island 1: V_OPA C-shape (x=30.75→34, y=40.8-57) + C5-pad2 (V_MID) narrows GND zone corridor
    # to <0.2mm between pad2 right (33.1) and V_OPA (33.85). Via at (33,45) stitches isolated fill
    # inside the C-shape to B.Cu GND plane.
    via(board, "GND", 33.0, 45.0)
    # Upper section (y<30.3): stitch at y=18 row alongside corner vias (3,18)/(36,18).
    # x=18.5 > VPLUS keepout right edge (14.5); SIG_OUT starts at x=19.975 so the
    # strip y=27.635..30.3 connects leftward and is not isolated.
    via(board, "GND", 18.5, 18.0)
    # V_OSC F.Cu horizontal at y=30.3 (x=10.475..30) splits lower GND pour from upper.
    # Stitch mid-board lower section (y>30.3).
    via(board, "GND", 18.5, 40.0)

    # ════════════════════════════════════════════════════════════════════════
    # HV NETS  (0.4mm)
    # ════════════════════════════════════════════════════════════════════════

    # ── VBOOST: D2-pad2 → Cres-pad1 → DZ1-pad1, also Cres-pad1 → L1-pad1 ──
    # D2 pad2 (VBOOST) at (26.0625, 49.95)
    # Cres pad1 at (28.05, 67.0); Cres pad2 (GND) at (29.95, 67.0)
    # DZ1 pad1 at (32.0, 67.15); L1 pad1 at (30.15, 78.5)
    # Route D2-pad2 to horizontal bus at y=65.5 to stay clear of Cres pad2 at y=67
    # x=26.9: Cp2-pad2(25.95,64) right copper=26.3mm; gap=26.9-0.2-26.3=0.4mm
    route(board, "VBOOST", F, HV,
          (26.0625, 49.95),
          (26.9,    49.95),
          (26.9,    65.5 ),
          (28.05,   65.5 ),
          (28.05,   67.0 ))
    # Cres → DZ1: go up to y=65.5, right to x=32, down to DZ1 (avoids Cres pad2 at x=29.95,y=67)
    route(board, "VBOOST", F, HV,
          (28.05, 67.0 ),
          (28.05, 65.5 ),
          (32.0,  65.5 ),
          (32.0,  67.15))
    # Cres → L1: x=27.15 stays left of ZT2 hole (r=1.6mm) until y=75, then jog right to pad1
    # Track ends at y=75→78.5, never reaching V_OPA_RAW F.Cu at y=79.2 (no crossing)
    # At (30.15,75): dist to ZT2(31,72)=3.12mm > 1.6+0.2+0.25=2.05mm hole clearance OK
    route(board, "VBOOST", F, HV,
          (28.05, 67.0),
          (27.15, 67.0),
          (27.15, 75.0),
          (30.15, 75.0),
          (30.15, 78.5))

    # ── HV_FILT: L1-pad2 → C9-pad1 ───────────────────────────────────────
    # L1 pad2 at (33.85, 78.5); C9 pad1 at (36.5, 78.0625) [rot=-90, pad1 at top]
    # Approach from left at y=78.5 then up to pad1 — never crosses pad2(GND) at y=79.94
    route(board, "HV_FILT", F, HV,
          (33.85, 78.5),
          (36.5,  78.5),
          (36.5,  78.0625))

    # ── HV_FILT: C9-pad1 → R_GBIAS1-pad2  (long HV rail up right edge) ───
    # R_GBIAS1 pad2 (HV_FILT) at (33.4625, 8); run x=37 to avoid everything
    # x=37.2: board edge gap 0.6mm ✓; MH2 pad right=36.7mm, trace left=37.0mm, gap=0.3mm ✓
    # horizontal at y=9 (not y=8): dist to MH2(34,5)=4mm, gap=4-2.7-0.2=1.1mm ✓
    route(board, "HV_FILT", F, HV,
          (36.5,    78.0625),
          (37.2,    78.0625),
          (37.2,    9.0    ),
          (30.4625, 9.0    ))

    # ── HV_MID: R_GBIAS1-pad1 → R_GBIAS2-pad1 ──────────────────────────────
    # R_GBIAS1 pad1 at (27.5375,9); R_GBIAS2 pad1 at (27.5,14): near-vertical
    route(board, "HV_MID", F, HV,
          (27.5375, 9.0 ),
          (27.5375, 14.0),
          (27.5,    14.0))

    # ── CAP_FP: R_GBIAS2-pad2 → C8-pad1 → J2-pad1 ───────────────────────
    # R_GBIAS2 pad2 (CAP_FP) at (24.575,14); horizontal left to C8.pad1 (15.23,14)
    route(board, "CAP_FP", F, HV,
          (24.575, 14.0),
          (15.23,  14.0))
    route(board, "CAP_FP", F, HV,
          (15.23,  14.0),
          (15.23,   3.0))

    # ════════════════════════════════════════════════════════════════════════
    # POWER NETS  (0.3mm)
    # ════════════════════════════════════════════════════════════════════════


    # ── V_OPA_RAW: R1-pad2 → R2-pad2 → U2-pad3 → C1-pad1 ──────────────────
    # R1(12,80) rot=90: pad1(XLR_HOT)=(12,80.825), pad2(V_OPA_RAW)=(12,79.175)
    # R2(12,83) rot=90: pad1(XLR_COLD)=(12,83.825), pad2(V_OPA_RAW)=(12,82.175)
    # Bypass R1.pad1 (XLR_HOT at y=80.825) on RIGHT side at x=13.0
    # R1.pad1 X half=0.475mm → right edge=12.475mm; bypass left=12.85mm → gap=0.375mm ✓
    route(board, "V_OPA_RAW", F, PWR, (12.0, 82.2), (13.0, 82.2))
    route(board, "V_OPA_RAW", F, PWR, (13.0, 82.2), (13.0, 79.2))
    route(board, "V_OPA_RAW", F, PWR, (13.0, 79.2), (12.0, 79.2))
    # F.Cu right to x=28.5 (clears HV_FILT at x=29.3625 with 0.51mm gap); via to B.Cu
    route(board, "V_OPA_RAW", F, PWR, (12.0, 79.2), (28.5, 79.2))
    via(board, "V_OPA_RAW", 28.5, 79.2)
    # B.Cu: up to U2 tap level y=46.9; C1 tapped via via on the vertical at y=54
    route(board, "V_OPA_RAW", B, PWR,
          (28.5, 79.2), (28.5, 46.9))
    # Tap stub: jog LEFT from (28.5,46.9) to x=25 (clear of C5 courtyard), then down to via
    route(board, "V_OPA_RAW", B, PWR, (28.5, 46.9), (25.0, 46.9), (25.0, 45.5))
    via(board, "V_OPA_RAW", 25.0, 45.5)
    route(board, "V_OPA_RAW", F, PWR, (25.0, 45.5), (21.05, 45.5))
    # C1-pad1 (V_OPA_RAW) at (30.49,54): via on B.Cu vertical; 1.99mm F.Cu stub right
    via(board, "V_OPA_RAW", 28.5, 54.0)
    route(board, "V_OPA_RAW", F, PWR, (28.5, 54.0), (30.49, 54.0))

    # ── V_OPA: vertical bus at x=31, individual branches to each consumer ────
    # U2 pad1 (21.05,42.5) → bus at x=31, y=21.48..42.5
    # Bus extends: C3(27.51,21), C2(28.52,38), R_ZEN(30,34.51), U1-pin7(19.975,26.365)
    # Separate: R4 branch up from U2, D1 branch left then down, C6 branch right then down
    # Main bus: UP from U2-pad1 to y=40.8 (clears C5 SMD pad top at ~42.2mm),
    # RIGHT to x=30.75 (clears V_OSC right end x=30.0 by 0.3mm; Z_OSC-pad2 x=31.65 by 0.45mm).
    route(board, "V_OPA", F, PWR,
          (21.05, 42.5 ),
          (21.05, 40.8 ),
          (30.75,  40.8 ),
          (30.75,  21.0 ),
          (27.51,  21.0 ))
    # C2 tap: angle=180 puts pad1(V_OPA) at right (29.51,38); direct stub from bus
    route(board, "V_OPA", F, PWR,
          (30.75, 38.0),
          (29.51, 38.0))
    # R_ZEN tap at y=33.5 (pad1(V_OPA) at right x=30.12)
    route(board, "V_OPA", F, PWR,
          (30.75, 33.5),
          (30.12, 33.5))
    # U1 pin7 tap: RIGHT to x=21.5 (clears pad8 right edge 20.95),
    # UP to y=24.5 (clears R6.pad1 top 25.965; clears SIG_PROT via at (27,25.5)),
    # RIGHT to bus at x=30.75.
    route(board, "V_OPA", F, PWR,
          (19.975, 26.365),
          (21.5,   26.365),
          (21.5,   24.5  ),
          (30.75,  24.5  ))
    # R4 pad1 (8.02,40.8): via at F.Cu main bus corner (21.05,40.8); B.Cu at same y
    via(board, "V_OPA", 21.05, 40.8)
    route(board, "V_OPA", B, PWR,
          (21.05, 40.8),
          (9.5,   40.8))
    via(board, "V_OPA", 9.5, 40.8)
    route(board, "V_OPA", F, PWR,
          (9.5,  40.8),
          (8.02, 40.8))
    # D1 pad1 (21.0625,51.05): B.Cu via. F.Cu area blocked by U2 pads (y=44/45.5),
    # V_OPA_RAW vertical (x=15.5, y=40-47), V_OSC (y=51.19), N2 (x=22).
    # Via at (19,44): B.Cu clears V_MID B.Cu (y=43, gap=0.55mm), TX_DRV B.Cu (x=5.0).
    # Via at (21.0625,49): 1mm above D1 silk outline top (~y=50.5), clears pin-1 indicator.
    route(board, "V_OPA", F, PWR,
          (21.05, 42.5),
          (19.0,  42.5),
          (19.0,  44.0))
    via(board, "V_OPA", 19.0, 44.0)
    route(board, "V_OPA", B, PWR,
          (19.0,    44.0 ),
          (19.0,    49.0 ),
          (21.0625, 49.0 ))
    via(board, "V_OPA", 21.0625, 49.0)
    route(board, "V_OPA", F, PWR,
          (21.0625, 49.0 ),
          (21.0625, 51.05))
    # C6 pad2(V_OPA) at (32.8,60.0): branch from bus at (30.75,40.8), right to x=34, down to pad2
    route(board, "V_OPA", F, PWR,
          (30.75, 40.8),
          (34.0,  40.8),
          (34.0,  57.0),
          (32.8,  57.0),
          (32.8,  60.0))

    # ── V_MID: bus at x=7 (left of R_BIAS1 VPLUS pad at x=9.925) ───────────
    # R5 pad1 (7.0,48) on bus; C4 via stub; C5 via B.Cu branch
    # R4 pad2 (7.0,41) on bus; R3 pad1 (7.0,29.7) on bus; R_BIAS1 pad2 (7.0,27.5) on bus
    route(board, "V_MID", F, PWR,
          (7.0, 44.775),
          (4.0, 44.775))
    route(board, "V_MID", F, PWR,
          (7.0, 48.0),
          (7.0, 27.5))
    # C5 pad2(V_MID) at (31.8,43): via at bus x=7, B.Cu trace, via below pad, F.Cu stub up to pad
    via(board, "V_MID", 7.0, 43.0)
    route(board, "V_MID", B, PWR,
          (7.0,  43.0),
          (31.8, 43.0),
          (31.8, 44.5))
    via(board, "V_MID", 31.8, 44.5)
    route(board, "V_MID", F, PWR,
          (31.8, 44.5),
          (31.8, 43.0))

    # ── V_OSC: R_ZEN-pad2 → Z_OSC-pad1 → U3-pad14 → C_U3-pad1 ─────────────
    # R_ZEN pad2 (29.1,33.5) aligned to Z_OSC pad1 (29.1,28.5): straight vertical.
    # Horizontal bus at y=30 taps off the vertical at (29.1,30).
    # U3 pad14 (10.475,51.19); C_U3 pad1 (13.52,52.0)
    route(board, "V_OSC", F, PWR,
          (29.1,   33.5 ),
          (29.1,   28.5 ))
    route(board, "V_OSC", F, PWR,
          (29.1,   30.0 ),
          (10.475, 30.0 ),
          (10.475, 51.19))
    # C_U3 tap: go RIGHT from U3 pad14 to avoid U3 pads below y=51.19
    route(board, "V_OSC", F, PWR,
          (10.475, 51.19),
          (13.52,  51.19),
          (13.52,  52.0 ))

    # ════════════════════════════════════════════════════════════════════════
    # SIGNAL NETS  (0.2mm)
    # ════════════════════════════════════════════════════════════════════════

    # ── VPLUS: R_BIAS1-pad1 → U1-pin3 → C8-pad2 (all F.Cu, within keepout) ──
    # R_BIAS1 pad1 (9.925,27.5); U1 pin3 (15.025,27.635); C8 pad2 (13.33,14.0)
    # Entire path in keepout/capsule zone: no adjacent F.Cu GND copper.
    route(board, "VPLUS", F, SIG,
          (9.925,  27.5  ),
          (9.925,  27.635),
          (15.025, 27.635))
    route(board, "VPLUS", F, SIG,
          (13.33, 14.0),
          (13.33, 27.635))

    # ── VINV: three F.Cu stubs → vias → B.Cu backbone ───────────────────────
    # R6.pad1(VINV) at (25,26.49): stub UP to via (25,25.5).
    # U1.pad2 (15.025,26.365): stub RIGHT to via (16.6,26.365);
    #   x=16.6 clears pad3(VPLUS) right edge (16.0) + via radius (0.3) + clearance (0.2) = 16.5.
    # R3.pad2 (8.02,29.7): stub RIGHT 1mm to via (9.02,29.7).
    # B.Cu L-route connects all three vias.
    route(board, "VINV", F, SIG, (25.0,   26.49 ), (25.0,   25.5  ))
    via(board, "VINV", 25.0, 25.5)
    route(board, "VINV", F, SIG, (15.025, 26.365), (16.6,   26.365))
    via(board, "VINV", 16.6, 26.365)
    route(board, "VINV", F, SIG, (8.02,   29.7  ), (9.02,   29.7  ))
    via(board, "VINV", 9.02, 29.7)
    route(board, "VINV", B, SIG,
          (25.0, 25.5  ),
          (25.0, 26.365),
          (16.6, 26.365),
          (16.6, 29.7  ),
          (9.02, 29.7  ))

    # ── Presence peak: V_MID tap + RS_MID link + VINV branch ─────────────────
    # V_MID bus at x=7; V_OSC blocks F.Cu at x=10.475, so tap via B.Cu
    via(board, "V_MID", 7.0, 33.0)
    route(board, "V_MID", B, PWR, (7.0, 33.0), (14.0, 33.0))
    via(board, "V_MID", 14.0, 33.0)
    route(board, "V_MID", F, PWR, (14.0, 33.0), (15.49, 33.0))
    # RS_MID: R_PRES1.pad2 → C_PRES1.pad1 direct stub
    route(board, "RS_MID", F, SIG, (16.51, 33.0), (18.49, 33.0))
    # VINV: F.Cu stub right, via, B.Cu L-route up to VINV backbone corner (16.6,29.7)
    route(board, "VINV", F, SIG, (19.51, 33.0), (20.51, 33.0))
    via(board, "VINV", 20.51, 33.0)
    route(board, "VINV", B, SIG,
          (20.51, 33.0),
          (16.6,  33.0),
          (16.6,  29.7))

    # ── SIG_OUT: U1-pin6 → R7-pad1 (RIGHT), short stub down to R6-pad2 ──────
    # U1 pin6 (19.975,27.635); R7 pad1 (27.0,27.51); R6 pad2(SIG_OUT) at (25,27.51)
    # R6 at (25,27,−90°): pad2(SIG_OUT) at (25,27.51). Same net — no mask bridge.
    route(board, "SIG_OUT", F, SIG,
          (19.975, 27.635),
          (27.0,   27.635),
          (27.0,   27.51 ))
    route(board, "SIG_OUT", F, SIG,
          (25.0, 27.635),
          (25.0, 27.51 ))

    # ── SIG_PROT: R7-pad2 → C_DC-pad1 ──────────────────────────────────────
    # R7 pad2 (27.0,26.49); C7 (C_DC) pad1 (27.0,33.55) — C7 at (27,35.025,−90°).
    # Both pads at x=27: B.Cu straight vertical at x=27.
    # Stub UP from pad2 to via (27,25.5); B.Cu down to (27,32.05); via → F.Cu stub to pad1.
    route(board, "SIG_PROT", F, SIG,
          (27.0, 26.49),
          (27.0, 25.5 ))
    via(board, "SIG_PROT", 27.0, 25.5)
    route(board, "SIG_PROT", B, SIG,
          (27.0, 25.5),
          (27.0, 32.05))
    via(board, "SIG_PROT", 27.0, 32.05)
    route(board, "SIG_PROT", F, SIG,
          (27.0, 32.05),
          (27.0, 33.55))

    # ── TX_DRV: C_DC-pad2 → T1A-pad1 ───────────────────────────────────────
    # C7 pad2 (27.0,36.5); T1A pad1 (8.0,62.0)
    # Stub LEFT from pad2 to via (24.0,36.5); clears pad left edge (~26.15) by 2.15mm.
    # B.Cu horizontal at y=36.5 then down to T1A.
    # x=5.0 clears V_MID B.Cu (starts x=7) and CLKA_IN B.Cu (starts x=7.0).
    route(board, "TX_DRV", F, SIG,
          (27.0, 36.5),
          (24.0, 36.5))
    via(board, "TX_DRV", 24.0, 36.5)
    route(board, "TX_DRV", B, SIG,
          (24.0, 36.5),
          (5.0,  36.5),
          (5.0,  62.0),
          (8.0,  62.0))
    # S3 (TP1.3) is floating — no GND connection to (18,62)

    # ── XLR_HOT: T1B-pad1 → R_RFI1-pad2 ────────────────────────────────
    # T1B pad1 (17.0,82.0); R_RFI1 pad2 (10.0,85.47)
    # Jog down to y=83 before going left: V_OPA_RAW horizontal at y=82.2 (x=12-13, w=0.3mm)
    # would overlap XLR_HOT at y=82.0 (w=0.2mm); y=83 gives 0.55mm gap ✓
    # y=83 vs R2.pad1 (XLR_COLD, y=83.825 top=83.35): gap=0.25mm ✓
    # y=83 vs R2.pad2 (V_OPA_RAW, y=82.175 top=82.65): gap=0.25mm ✓
    # XLR_HOT vertical at x=10: MH3 copper edge at x=7.55; gap=2.45mm ✓
    route(board, "XLR_HOT", F, SIG,
          (17.0,  82.0),
          (17.0,  83.0),
          (10.0,  83.0),
          (10.0,  80.8))
    route(board, "XLR_HOT", F, SIG, (10.0, 80.8), (12.0, 80.8))  # R1 tap
    route(board, "XLR_HOT", F, SIG,
          (10.0,  83.0),
          (10.0,  85.47))   # to R_RFI1 pad2

    # ── XLR_HOT_F: R_RFI1-pad1 → C_RFI1-pad1 + J3-pad2 ─────────────
    # R_RFI1 pad1 (10.0,86.53); T-junction at (10,87); C_RFI1 pad1 (12.47,87)
    # GND: C_RFI1 pad2 (13.53,87) → 1mm stub RIGHT → via; clears courtyard right edge (13.98)
    route(board, "XLR_HOT_F", F, SIG, (10.0, 86.53), (10.0, 87.0), (12.47, 87.0))
    route(board, "XLR_HOT_F", F, SIG, (10.0, 87.0), (10.0, 88.54), (20.0, 88.54), (20.0, 90.0))
    route(board, "GND", F, SIG, (13.53, 87.0), (14.53, 87.0))
    via(board, "GND", 14.53, 87.0)

    # ── XLR_COLD: T1B-pad2 → R_RFI2-pad2 ───────────────────────────────
    # T1B pad2 (22.0,82.0); R_RFI2 pad2 (22.0,85.47)
    # P2 below transformer cutout — simple F.Cu; no CLKB/VBOOST conflicts below y=77.3
    # R2 tap at (12,83.8) approached from x=22; XLR_HOT vertical at x=10 stays left of x=12 ✓
    route(board, "XLR_COLD", F, SIG,
          (22.0,  82.0),
          (22.0,  83.8),
          (12.0,  83.8))   # R2 tap
    route(board, "XLR_COLD", F, SIG,
          (22.0,  83.8),
          (22.0,  85.47))   # to R_RFI2 pad2

    # ── XLR_COLD_F: R_RFI2-pad1 → C_RFI2-pad1 + J3-pad3 ───────────
    # R_RFI2 pad1 (22.0,86.53); T-junction at (22,87); C_RFI2 pad1 (24.47,87)
    # GND: C_RFI2 pad2 (25.53,87) → 1mm stub RIGHT → via; clears courtyard right edge (25.98)
    route(board, "XLR_COLD_F", F, SIG, (22.0, 86.53), (22.0, 87.0), (24.47, 87.0))
    route(board, "XLR_COLD_F", F, SIG, (22.0, 87.0), (22.0, 89.0), (22.54, 89.0), (22.54, 90.0))
    route(board, "GND", F, SIG, (25.53, 87.0), (26.53, 87.0))
    via(board, "GND", 26.53, 87.0)


    # ── Dickson pump nodes ───────────────────────────────────────────────────
    # N1: D1-pad3 (22.9375,52.0) → Cp1-pad1 (21.05,55.5)
    # Jog LEFT to x=20 to avoid N2 which will use x=22 column
    route(board, "N1", F, SIG,
          (22.9375, 52.0),
          (20.0,    52.0),
          (20.0,    55.5),
          (21.05,   55.5))

    # N2: D1-pad2 (21.0625,52.95) → D2-pad1 (26.0625,48.05) and → Cp2-pad1 (24.05,64.0)
    # Use x=22 column (D1 pad1 V_OPA right edge at 21.66, x=22 left edge at 21.9 → 0.24mm gap)
    # D1 pad3 N1 bottom at y=52.6; N2 horizontal at y=52.95 top at y=52.85 → 0.25mm gap OK
    # Rerouted: D1 pad half-x≈0.74mm; D1-pad3 right copper=23.6775; x=24.05 gap=0.2725mm ✓
    # Go below D1 (y=53.7) then use x=24.05 column
    route(board, "N2", F, SIG,
          (21.0625, 52.95),
          (21.0625, 53.7 ),
          (24.05,   53.7 ),
          (24.05,   48.05),
          (26.0625, 48.05))
    # Cp2 branch from junction at (24.05,53.7) — simple vertical
    route(board, "N2", F, SIG,
          (24.05, 53.7 ),
          (24.05, 60.5 ))

    # N3: D2-pad3 (27.9375,49.0) → Cp3-pad1 (30.05,49.0) — Cp3 at (31,49), direct horizontal
    route(board, "N3", F, SIG,
          (27.9375, 49.0),
          (30.05,   49.0))

    # ── Clock nets (B.Cu — shielded under U3) ───────────────────────────────
    # CLKA_IN: U3-pad1 (5.525,51.19) → R_OSC-pad2 (16.0,55.49) → C_OSC-pad1 (18.0,59.48)
    # Route on B.Cu to shield from input; vias offset from pads with F.Cu stubs.
    # U3 pad1: via moved right to (7.0,51.19); F.Cu stub to pad.
    # R_OSC1 pad2: via moved right to (17.5,55.49); F.Cu stub to pad.
    via(board, "CLKA_IN", 7.0, 51.19)
    route(board, "CLKA_IN", F, SIG, (7.0, 51.19), (5.525, 51.19))
    route(board, "CLKA_IN", B, SIG,
          (7.0,  51.19),
          (16.0, 51.19),
          (16.0, 55.49),
          (15.0, 55.49))
    via(board, "CLKA_IN", 15.0, 55.49)
    route(board, "CLKA_IN", F, SIG, (15.0, 55.49), (16.0, 55.49))
    # B.Cu bypass; via at x=15 avoids CLKA F.Cu Seg-C at x=17 (y=47-56.51)
    route(board, "CLKA_IN", B, SIG,
          (15.0, 55.49),
          (15.0, 57.0 ),
          (18.0, 57.0 ),
          (18.0, 59.48))
    via(board, "CLKA_IN", 18.0, 59.48)

    # CLKA: U3-pad2 (5.525,52.46) → U3-pad3 (5.525,53.73) → R_OSC-pad1 (16.0,56.51)
    #       → Cp1-pad2 (22.95,59.0) → Cp3-pad2 (32.95,52.0)
    # Connect pad2→pad3 on F.Cu, then jog RIGHT to x=8 before going down.
    # Avoids x=5.525 below y=53.73 (CLKB pad4 at y=55); x=8 clears CLKB at x=7 by 0.8mm.
    # Seg A: B.Cu bypass under U3-pad10; via at x=12.0 (gap to pad10 right copper 11.442mm: 0.258mm)
    route(board, "CLKA", F, SIG,
          (5.525, 52.46),
          (5.525, 53.73),
          (8.0,   53.73),
          (8.0,   56.51),
          (9.0,   56.51))
    via(board, "CLKA", 9.0, 56.51)
    route(board, "CLKA", B, SIG, (9.0, 56.51), (12.0, 56.51))
    via(board, "CLKA", 12.0, 56.51)
    route(board, "CLKA", F, SIG, (12.0, 56.51), (17.0, 56.51))
    # Seg B: via at (22.95,57.5) above Cp1 pad2; B.Cu detour at y=60.15 clears CLKA_IN via
    # (18,59.48) bottom copper (59.78) by 0.27mm. Cannot use F.Cu at x=22.95,y>60.3 (CLKB
    # horizontal at y=60.3) so approach from above via (22.95,57.5) with B.Cu coming from below.
    route(board, "CLKA", F, SIG, (17.0, 56.51), (17.0, 58.0))
    via(board, "CLKA", 17.0, 58.0)
    route(board, "CLKA", B, SIG,
          (17.0, 58.0 ),
          (17.0, 60.15),
          (22.95, 60.15),
          (22.95, 57.5))
    via(board, "CLKA", 22.95, 57.5)
    route(board, "CLKA", F, SIG, (22.95, 57.5), (22.95, 55.5))
    # Seg C: x=17 avoids CLKA_IN via/pad at (16,55.49); y=47 above N2(y=48.05), VBOOST(y=49.95)
    # Cp3 at (31,49): pad2(CLKA) at (31.95,49)
    route(board, "CLKA", F, SIG,
          (17.0,  56.51),
          (17.0,  47.0 ),
          (31.95, 47.0 ),
          (31.95, 49.0 ))

    # CLKB: U3-pad4 (5.525,55.0) → Cp2-pad2 (22.15,64.0)
    # Cp2 flipped 180°: pad2(CLKB) now at left (22.15,64) — no y=65.5 detour needed
    # y=60.3 horizontal: T1A pads top=61.25mm; gap=61.25-60.45=0.8mm ✓
    # x=6.875: U3 pad right edge=6.5mm; gap=6.875-0.15-6.5=0.225mm ✓
    #           T1A.2 left edge=7.25mm; gap=7.25-6.875-0.15=0.225mm ✓
    route(board, "CLKB", F, SIG,
          (5.525,  55.0),
          (6.875,  55.0),
          (6.875,  60.3),
          (22.15,  60.3),
          (22.15,  60.5))


def fix_ref(board, ref, new_text=None, x_mm=None, y_mm=None, angle_deg=None, hide=False):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            if new_text is not None:
                fp.Reference().SetText(new_text)
            if x_mm is not None and y_mm is not None:
                fp.Reference().SetPosition(pcbnew.VECTOR2I(MX(x_mm), MY(y_mm)))
            if angle_deg is not None:
                fp.Reference().SetTextAngle(
                    pcbnew.EDA_ANGLE(angle_deg, pcbnew.DEGREES_T))
            if hide:
                fp.Reference().SetVisible(False)
            return


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    board = pcbnew.BOARD()

    # Design settings
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = MM(0.15)

    # Board outline: 36x93mm (shrunk 2mm each side + 2mm bottom; housing internal dia ~45mm)
    add_outline_rect(board, 2, 0, 38, 93)

    # Transformer cutout (body 15x6mm + 0.5mm each side = 15x7mm)
    add_outline_rect(board, 11.0, 68.5, 26.0, 75.5)

    # ── Mechanical footprints ────────────────────────────────────────────────
    # Mount hole pattern: 30mm horizontal x 80mm vertical (per housing bosses)
    # Centred on 40mm wide board: x=5 and x=35 (5mm margins each side)

    # MH1/MH2 in capsule zone: NPTH (no F.Cu copper) so guard ring can enclose the zone.
    for ref, x, y in [("MH1",6,5),("MH2",34,5)]:
        place(board, "MountingHole", "MountingHole_2.7mm_M2.5", ref, ref, x, y)
    # MH3/MH4 in XLR zone: PTH with GND pad for housing grounding.
    for ref, x, y in [("MH3",6,85),("MH4",34,85)]:
        place(board, "MountingHole", "MountingHole_2.7mm_M2.5_Pad_TopBottom",
              ref, ref, x, y, pad_nets={"1": "GND"})
    for ref, x, y in [("ZT1",8,72),("ZT2",31,72)]:
        place(board, "MountingHole", "MountingHole_3.2mm_M3", ref, ref, x, y)

    # ── Capsule input zone (y=5..20) ─────────────────────────────────────────
    # F.Cu GND copper pour exclusion around all high-Z nodes.
    # L-shape covers CAP_FP trace network (J2/C8/R_GBIAS1/2, x=6..36.5, y=0..17)
    # and VPLUS trace + R_BIAS1 (x=6..14.5, y=17..30).
    # B.Cu GND plane is retained: THT pads (J2-GND) stay connected;
    # MH1/MH2 are NPTH (no copper) so the guard ring can fully enclose the zone.
    # Through-board stray capacitance is small (<1 pF, through 1.6 mm FR4).
    # Keepout: only the VPLUS trace corridor (x=6..14.5, y=17..30).
    # The y<17 portion is now redundant: F.Cu GND zone no longer extends above y=17.
    add_keepout(board, pcbnew.F_Cu,
                [(6, 17), (14.5, 17), (14.5, 30), (6, 30)])

    # J2: bare THT solder pads for capsule wires
    place_solder_pads(board, "J2", 15.23, 3, ["CAP_FP", "GND"], axis='x')

    # angle=180: pad1(CAP_FP) at right (15.23,14); pad2(VPLUS) at left (13.33,14)
    # pad1 aligns with J2-pad1 x=15.23; shortens CAP_FP HV trace vs old x=11.05
    place(board, "Capacitor_SMD", "C_0805_2012Metric",
          "C8", "10n X7R", 14.28, 14, 180,
          {"1": "CAP_FP", "2": "VPLUS"})

    # R_GBIAS1/2 in series: HV_FILT -> HV_MID -> CAP_FP (2x47M = 94M total)
    # Horizontal at x=32: pad1(left)=HV_MID, pad2(right)=HV_FILT/CAP_FP
    # pad1 at (30.5375,y), pad2 at (33.4625,y)
    place(board, "Resistor_SMD", "R_1206_3216Metric",
          "R_GBIAS1", "47M 1206", 29, 9, 0,
          {"1": "HV_MID", "2": "HV_FILT"})

    # angle=180: pad1(HV_MID) at right (27.5,14); pad2(CAP_FP) at left (24.575,14)
    place(board, "Resistor_SMD", "R_1206_3216Metric",
          "R_GBIAS2", "47M 1206", 26.0375, 14, 180,
          {"1": "HV_MID", "2": "CAP_FP"})

    # ── OPA1641 amplifier zone (y=18..42) ────────────────────────────────────

    u1_fp = place(board, "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm",
                  "U1", "OPA1641", 17.5, 27, 0,
                  {"2": "VINV", "3": "VPLUS", "4": "GND", "6": "SIG_OUT", "7": "V_OPA"})
    for _pad in u1_fp.Pads():
        if _pad.GetNumber() == "4":
            _pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
            break

    # R_BIAS: VPLUS -> V_MID  (100M, establishes DC operating point for IN+)
    # angle=180: pad1(VPLUS) at right (9.925,27.5); pad2(V_MID) at left (7.0,27.5) on bus
    place(board, "Resistor_SMD", "R_1206_3216Metric",
          "R_BIAS1", "100M 1206", 8.4625, 27.5, 180,
          {"1": "VPLUS", "2": "V_MID"})

    # R3: V_MID -> VINV  (2.2k, sets IN- DC level = IN+ for balance)
    # angle=0: pad1(V_MID) at left (7.0,29.7) on bus; pad2(VINV) at right (8.02,29.7)
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R3", "2.2k", 7.51, 29.7, 0,
          {"1": "V_MID", "2": "VINV"})

    # Presence-peak network: Rs (6.2k) + C (12nF) in series, parallel with R3
    # At DC: C blocks → Z = R3 = 2.2k, gain = 22.4x (0 dB reference)
    # At HF: C shorts → Z = R3‖Rs = 1.61k, gain = 30.2x (+2.6 dB)
    # Corner f = 1/(2π·6.2k·12nF) ≈ 2.1 kHz — targets M149-style presence peak
    # R_PRES1 at x=16 clears V_OSC F.Cu at x=10.475 (y=30..51); C_PRES1 at x=19
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R_PRES1", "6.2k", 16, 33, 0,
          {"1": "V_MID", "2": "RS_MID"})
    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C_PRES1", "12n 25V C0G", 19, 33, 0,
          {"1": "RS_MID", "2": "VINV"})

    # R6: SIG_OUT -> VINV  (47k feedback, sets gain = 1 + 47k/2.2k = 22.4x → -22 dBV/Pa)
    # angle=-90: pad1(VINV) at (25,26.49) above; pad2(SIG_OUT) at (25,27.51) below
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R6", "47k", 25, 27, -90,
          {"1": "VINV", "2": "SIG_OUT"})

    # R7: SIG_OUT -> SIG_PROT  (100R output series protection)
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R7", "100R", 27, 27, 90,
          {"1": "SIG_OUT", "2": "SIG_PROT"})

    # C3: V_OPA -> GND  (100n, HF bypass within 5mm of U1 pin 7)
    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C3", "100n 25V X7R", 27, 21, 180,
          {"1": "V_OPA", "2": "GND"})

    # C_DC: SIG_PROT -> TX_DRV  (4.7u DC block to transformer primary)
    # angle=-90: pad1(SIG_PROT) at (27,33.55) above; pad2(TX_DRV) at (27,36.5) below
    place(board, "Capacitor_SMD", "C_1206_3216Metric",
          "C7", "4.7u 50V X7R", 27, 35.025, -90,
          {"1": "SIG_PROT", "2": "TX_DRV"})

    # ── Power supply zone (y=36..58) ─────────────────────────────────────────

    # R1/R2: phantom extraction resistors 6.8k 0.1% (matched pair)
    place(board, "Resistor_SMD", "R_0603_1608Metric",
          "R1", "6.8k 0.1%", 12, 80, 90,
          {"1": "XLR_HOT", "2": "V_OPA_RAW"})

    place(board, "Resistor_SMD", "R_0603_1608Metric",
          "R2", "6.8k 0.1%", 12, 83, 90,
          {"1": "XLR_COLD", "2": "V_OPA_RAW"})

    # RFI filter: 100R series + 100pF C0G shunt on each XLR leg (fc ~16 MHz)
    # Placed in-line with XLR_HOT/COLD verticals (x=10, x=22) at y=86
    # Shunt caps at y=87, 1.5mm right of series R; GND via below each cap
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R_RFI1", "100R", 10, 86, 90,
          {"1": "XLR_HOT_F", "2": "XLR_HOT"})

    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R_RFI2", "100R", 22, 86, 90,
          {"1": "XLR_COLD_F", "2": "XLR_COLD"})

    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C_RFI1", "100p C0G", 13, 87, 0,
          {"1": "XLR_HOT_F", "2": "GND"})

    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C_RFI2", "100p C0G", 25, 87, 0,
          {"1": "XLR_COLD_F", "2": "GND"})

    # U2: 78L24 linear regulator SOT-89  (OUT=pad1, GND=pad2, IN=pad3)
    place(board, "Package_TO_SOT_SMD", "SOT-89-3",
          "U2", "L78L24", 23, 44, 0,
          {"1": "V_OPA", "2": "GND", "3": "V_OPA_RAW"})

    # C1/C2: input and output bypass for U2
    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C1", "100n 63V X7R", 31, 54, 0,
          {"1": "V_OPA_RAW", "2": "GND"})

    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C2", "100n 25V X7R", 29, 38, 180,
          {"1": "V_OPA", "2": "GND"})

    # R4/R5: V_MID = V_OPA/2 = 12V divider
    # angle=180: pad1(V_OPA) at right (8.02,40.8); pad2(V_MID) at left (7.0,40.8) on bus
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R4", "470k", 7.51, 40.8, 180,
          {"1": "V_OPA", "2": "V_MID"})

    # angle=0: pad1(V_MID) at left (7.0,48) on bus; pad2(GND) at right (8.02,48) into GND pour
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R5", "470k", 7.51, 48, 0,
          {"1": "V_MID", "2": "GND"})

    # C4/C5: V_MID bypass (0603 SMD + SMD electrolytic)
    place(board, "Capacitor_SMD", "C_0603_1608Metric",
          "C4", "10u 25V X5R", 4, 44, 90,
          {"1": "V_MID", "2": "GND"})

    # CP_Elec_4x5.4: pad1(−) at (−1.8,0), pad2(+) at (+1.8,0)
    # Component at (30,43) → pad2(V_MID) at (31.8,43), pad1(GND) at (28.2,43)
    place(board, "Capacitor_SMD", "CP_Elec_4x5.4",
          "C5", "10u 25V", 30, 43, 0,
          {"1": "GND", "2": "V_MID"})

    # C6 at (31,60): pad1(GND) at (29.2,60) left=27.9mm; VBOOST right=27.1mm → gap 0.8mm ✓
    # pad2(V_OPA) at (32.8,60)
    place(board, "Capacitor_SMD", "CP_Elec_4x5.4",
          "C6", "10u 25V", 31, 60, 0,
          {"1": "GND", "2": "V_OPA"})

    # Z_OSC shunt regulator: V_OPA -> R_ZEN -> V_OSC -> Z_OSC -> GND (15V supply for U3)
    # SOD-123 pad1=K, pad2=A; K=V_OSC (high side of zener), A=GND
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R_ZEN1", "6.8k", 29.61, 33.5, 180,
          {"1": "V_OPA", "2": "V_OSC"})

    place(board, "Diode_SMD", "D_SOD-123",
          "Z_OSC1", "15V MMSZ15", 30.75, 28.5, 0,
          {"1": "V_OSC", "2": "GND"})

    # ── Boost section (y=48..66, above transformer cutout) ───────────────────

    # U3: CD40106B SOIC-14 oscillator
    # Pads: 1=CLKA_IN, 2=CLKA, 3=CLKA(2nd gate in), 4=CLKB, 7=GND, 14=V_OSC
    # Pins 5,6,8-13 are unused gate I/O — left unconnected in schematic
    place(board, "Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm",
          "U3", "CD40106B", 8, 55, 0,
          {"1": "CLKA_IN", "2": "CLKA",
           "3": "CLKA",    "4": "CLKB",
           "7": "GND",     "14": "V_OSC"})

    # C_U3: 100n bypass on V_OSC (U3 VDD rail)
    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C_U3", "100n 25V X7R", 14, 52, 0,
          {"1": "V_OSC", "2": "GND"})

    # R_OSC / C_OSC: RC timing network (47k + 100pF ~ 100 kHz)
    place(board, "Resistor_SMD", "R_0402_1005Metric",
          "R_OSC1", "47k", 16, 56, 90,
          {"1": "CLKA", "2": "CLKA_IN"})

    # C_OSC moved to x=18 to clear T1A courtyard (T1A x_max=15.80, C_OSC x_min=17.54)
    place(board, "Capacitor_SMD", "C_0402_1005Metric",
          "C10", "100p C0G", 18, 59, 90,
          {"1": "CLKA_IN", "2": "GND"})

    # D1/D2: BAT54S series dual Schottky (SOT-23 pad1=A, pad2=K, pad3=COM)
    # 3-stage active Dickson: V_OPA(24V) -> N1 -> N2 -> VBOOST
    place(board, "Package_TO_SOT_SMD", "SOT-23",
          "D1", "BAT54S", 22, 52, 0,
          {"1": "V_OPA", "2": "N2", "3": "N1"})

    place(board, "Package_TO_SOT_SMD", "SOT-23",
          "D2", "BAT54S", 27, 49, 0,
          {"1": "N2", "2": "VBOOST", "3": "N3"})

    # Cp1-3: pump capacitors 100n 100V (0805 PP film)
    place(board, "Capacitor_SMD", "C_0805_2012Metric",
          "Cp1", "100n 100V X7R", 22, 55.5, 0,
          {"1": "N1", "2": "CLKA"})

    # angle=180: pad1(N2) at right (24.05,60.5); pad2(CLKB) at left (22.15,60.5)
    place(board, "Capacitor_SMD", "C_0805_2012Metric",
          "Cp2", "100n 100V X7R", 23.1, 60.5, 180,
          {"1": "N2", "2": "CLKB"})

    place(board, "Capacitor_SMD", "C_0805_2012Metric",
          "Cp3", "100n 100V X7R", 31, 49, 0,
          {"1": "N3", "2": "CLKA"})

    # Transformer wire solder pads — bare THT holes
    # T1A horizontal 5mm pitch: pads at (8,62),(13,62),(18,62) — x=8 keeps S1 inboard of MH column (x=5)
    place_solder_pads(board, "TP1", 8, 62, ["TX_DRV", "GND", ""], axis='x', pitch_mm=5.0)

    # T1B horizontal 5mm pitch: pads at (17,82),(22,82) — below transformer cutout, close to J3
    place_solder_pads(board, "TS1", 17, 82, ["XLR_HOT", "XLR_COLD"], axis='x', pitch_mm=5.0)

    # ── HV filter + VBOOST clamp (right of transformer cutout, x=26..34) ──────

    # Cres: 470n reservoir cap on VBOOST
    # At (29,67): pad1 left edge=27.55 vs cutout right x=26.0, gap=1.55mm OK
    # Courtyard nearest corner (30.7,67.95) to ZT2 center (31,72): 4.06mm > r=3.455mm OK
    cres = place(board, "Capacitor_SMD", "C_0805_2012Metric",
                 "Cres1", "470n 100V X7R", 29, 67, 0,
                 {"1": "VBOOST", "2": "GND"})
    for pad in cres.Pads():
        if pad.GetNumber() == "2":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # DZ1: 68V zener clamp on VBOOST (K=pad1=VBOOST, A=pad2=GND)
    # At (32,65.5): nearest courtyard corner (31.15,67.5) to ZT2 center (31,72): 4.50mm > r=3.455mm OK
    place(board, "Diode_SMD", "D_SOD-123",
          "DZ1", "68V BZT52C68", 32, 65.5, 90,
          {"1": "VBOOST", "2": "GND"})

    # L1: 10mH LC filter inductor (FNR5040S, 5x5mm, courtyard ±2.8×±2.75mm)
    # L1 at cy=78.5: top edge at y=75.75 is 3.75mm below ZT2(31,72), clears courtyard r=3.455mm
    # Pad1 at (30.15,78.5): left edge x=29.45, gap to V_OPA_RAW via right(28.8)=0.65mm OK
    place(board, "Inductor_SMD", "L_Changjiang_FNR5040S",
          "L1", "10mH FNR5040S", 32.0, 78.5, 0,
          {"1": "VBOOST", "2": "HV_FILT"})

    # C9: rot=-90 puts pad1(HV_FILT) at TOP (y=78.06) so HV_FILT track approaches from above
    # without passing through pad2(GND) at bottom (y=79.94)
    place(board, "Capacitor_SMD", "C_0805_2012Metric",
          "C9", "470n 100V X7R", 36.5, 79.0, -90,
          {"1": "HV_FILT", "2": "GND"})

    # ── XLR output solder pads (bare THT, horizontal row) ────────────────────
    # J3.1=(17.46,90)=GND, J3.2=(20,90)=XLR_HOT_F, J3.3=(22.54,90)=XLR_COLD_F
    # XLR_HOT_F approaches J3.2 from above at x=20; XLR_COLD_F approaches J3.3 from above at x=22.54
    place_solder_pads(board, "J3", 17.46, 90, ["GND", "XLR_HOT_F", "XLR_COLD_F"], axis='x')

    # ── Route all nets + zones ────────────────────────────────────────────────
    route_all(board)

    # ── Silk label fixes ──────────────────────────────────────────────────────
    # TP1: labels at y=64 (below pads at y=62, clear of cutout top at y=66.7)
    # TS1: labels at y=84 (below pads at y=82, above J3 at y=92)
    for old, new, x, y in [("TP1.1","S1",8,64),("TP1.2","S2",13,64),("TP1.3","S3",18,64),
                            ("TS1.1","P1",17,80),("TS1.2","P2",22,80)]:
        fix_ref(board, old, new_text=new, x_mm=x, y_mm=y)

    # J3: shorten + move below pads (pitch 2.54mm needs ≤2mm labels)
    for old, new, x in [("J3.1","1",17.46),("J3.2","2",20.0),("J3.3","3",22.54)]:
        fix_ref(board, old, new_text=new, x_mm=x, y_mm=92)

    # J2: label front plate pad "FP" and body ground "GND"
    for old, new, x in [("J2.1","FP",15.23),("J2.2","GND",17.77)]:
        fix_ref(board, old, new_text=new, x_mm=x, y_mm=5)

    # R_OSC1: footprint at 90° rotates silk vertical — force horizontal (angle=0).
    # Place above component at (16,54): clears top pad (~y=55.5) and via(15,55.49).
    fix_ref(board, "R_OSC1", x_mm=16, y_mm=54.0, angle_deg=0)

    # D1: default silk lands left of component; move right of body (SOT-23 right edge ~x=23.8).
    fix_ref(board, "D1", x_mm=25, y_mm=52)

    # C10 (osc timing cap): place directly above component at (18,59); old
    # position (25,56.5) was 7mm away and appeared disconnected from component.
    fix_ref(board, "C10", x_mm=18, y_mm=56.5)

    # Z_OSC1: default ref text at ~(30,27.5) sits over R7 pad2 at (27,27.8).
    # Shift slightly right; keep above pads (pad2 copper reaches y=28.35).
    fix_ref(board, "Z_OSC1", x_mm=31.5, y_mm=26.5)
    # C3: angle=180 rotates silk; force horizontal above component (body top ~y=20.5)
    fix_ref(board, "C3", x_mm=27.0, y_mm=20.0, angle_deg=0)

    # R6/R7: angle rotates silk; force horizontal and place above component,
    # above SIG_PROT via at (27,25.5) copper top ~y=25.0; both at y=24.5
    fix_ref(board, "R6", x_mm=25.0, y_mm=24.5, angle_deg=0)
    fix_ref(board, "R7", x_mm=27.0, y_mm=24.5, angle_deg=0)
    # R4: angle=180 rotates silk; force horizontal and place above component
    fix_ref(board, "R4", x_mm=7.51, y_mm=39.5, angle_deg=0)
    # R3: place below component (center y=29.7, body bottom ~29.95)
    fix_ref(board, "R3", x_mm=7.51, y_mm=31.2)
    # R_PRES1 above, C_PRES1 below — staggered to avoid silk_overlap
    fix_ref(board, "R_PRES1", x_mm=16.0, y_mm=31.5, angle_deg=0)
    fix_ref(board, "C_PRES1", x_mm=19.0, y_mm=34.5, angle_deg=0)
    # R_BIAS1: angle=180 rotates silk; force horizontal and place above component
    # (body top at y=26.7, 1206 half-height=0.8mm)
    fix_ref(board, "R_BIAS1", x_mm=8.4625, y_mm=25.5, angle_deg=0)

    # C2: move left, clear of R_ZEN1 area
    fix_ref(board, "C2",     x_mm=31, y_mm=38, angle_deg=0)
    # R_ZEN1: angle=180 rotates silk; force horizontal above component (body top ~y=32.77)
    fix_ref(board, "R_ZEN1", x_mm=31.0, y_mm=32.2, angle_deg=0)

    # Cp1/Cp2: silk below body
    fix_ref(board, "Cp1", x_mm=25.0, y_mm=55.5, angle_deg=0)
    fix_ref(board, "Cp2", x_mm=23.1, y_mm=62.0, angle_deg=0)

    # DZ1: right silk line at x=32.94..33.06 — move label to x=35 to clear it
    fix_ref(board, "DZ1", x_mm=35, y_mm=65.5)
    # Cres1: default ref is above body (y=65.3), overlaps DZ1 silk — move below body
    fix_ref(board, "Cres1", x_mm=29, y_mm=69)

    # C4: rotated 90°, default ref near board left edge (x=2); move above top pad
    fix_ref(board, "C4", x_mm=4, y_mm=41)

    # R_GBIAS1: place below component (body bottom y=9.8), matching R_GBIAS2 style
    fix_ref(board, "R_GBIAS1", x_mm=29, y_mm=10.83, angle_deg=0)

    # R1/R2: rotated 90°, align silk to same x=14 so labels form a vertical straight line
    fix_ref(board, "R1", x_mm=14, y_mm=80)
    fix_ref(board, "R2", x_mm=14, y_mm=83)

    # R_RFI1: rotated 90°, default silk (8.83,86) overlaps C_RFI1 and is near MH3 copper.
    # x=10 aligns with component body; y=82 clears R2 top pad (y=82.47) and stays left of R1/R2 silk (x=14).
    fix_ref(board, "R_RFI1", x_mm=10, y_mm=82)

    # R_RFI2: rotated 90°, default silk (20.83,86) overlaps C_RFI2 ref and P2 silk.
    # x=20 is right of previous x=18, still clear of P2 (x=22,y=84) and C_RFI2 (x=25).
    fix_ref(board, "R_RFI2", x_mm=20, y_mm=86)

    fix_ref(board, "C_RFI1", x_mm=14.5, y_mm=85.5)
    fix_ref(board, "C_RFI2", x_mm=26.5, y_mm=85.5)

    # C9: default ref at x=38.18 cut by new board edge (x=38); move above pads
    fix_ref(board, "C9", x_mm=36.5, y_mm=75.5)

    # ZT1/ZT2 and MH1-MH4: no label needed on silk
    for ref in ("ZT1", "ZT2", "MH1", "MH2", "MH3", "MH4"):
        fix_ref(board, ref, hide=True)

    # ── Save ─────────────────────────────────────────────────────────────────
    pcbnew.SaveBoard(OUT, board)

    # ── Fill copper zones ───────────────────────────────────────────────────────
    # ZONE_FILLER segfaults when run against a freshly-constructed in-memory
    # BOARD() (a long-standing upstream pcbnew scripting issue); reloading the
    # just-saved file first avoids it.
    board = pcbnew.LoadBoard(OUT)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(OUT, board)

    print(f"Written: {OUT}")

    # Summary
    fps = list(board.GetFootprints())
    nets = [n.GetNetname() for n in board.GetNetInfo().NetsByName().values()
            if n.GetNetname() != ""]
    print(f"Footprints: {len(fps)}")
    print(f"Nets ({len(nets)}): {sorted(nets)}")


if __name__ == "__main__":
    main()
