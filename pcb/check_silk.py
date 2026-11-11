#!/usr/bin/env python3
"""Silkscreen against vias and pads, by geometry.

KiCad's DRC flags silk only over exposed copper. The vias on this board are tented, so silk across one passes
DRC, but the ink over the drill is lost and a reference loses part of a character. This turns every visible
silkscreen item into polygons and fails if any of them touches a via (drill or pad) or a pad's mask opening.

    python3 pcb/check_silk.py [board.kicad_pcb] [margin_mm]

Exit 1 on any overlap at the given margin (default 0). Run from the repo root after gen_pcb.py.
"""
import math
import os
import sys

import pcbnew

BOARD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "open-condenser-mic.kicad_pcb")
MARGIN = pcbnew.FromMM(float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
ERR = pcbnew.FromMM(0.005)
TEXT = (pcbnew.PCB_TEXT, pcbnew.PCB_FIELD)


def poly_of(item, layer):
    ps = pcbnew.SHAPE_POLY_SET()
    if isinstance(item, TEXT):
        item.TransformTextToPolySet(ps, 0, ERR, pcbnew.ERROR_INSIDE)
    else:
        item.TransformShapeToPolygon(ps, layer, 0, ERR, pcbnew.ERROR_INSIDE)
    return ps


def circle(x, y, r):
    ps = pcbnew.SHAPE_POLY_SET()
    ps.NewOutline()
    for k in range(32):
        ps.Append(int(x + r * math.cos(2 * math.pi * k / 32)), int(y + r * math.sin(2 * math.pi * k / 32)))
    return ps


def overlap_mm2(a, b):
    c = pcbnew.SHAPE_POLY_SET(a)
    c.BooleanIntersection(b)
    return c.Area() / 1e12


def main():
    board = pcbnew.LoadBoard(BOARD)
    mm = pcbnew.ToMM
    silk = []
    for layer, side, mask in ((pcbnew.F_SilkS, "F", pcbnew.F_Mask), (pcbnew.B_SilkS, "B", pcbnew.B_Mask)):
        for fp in board.GetFootprints():
            for it in list(fp.GraphicalItems()) + [fp.Reference(), fp.Value()]:
                if it.GetLayer() != layer:
                    continue
                if isinstance(it, TEXT):
                    if not it.IsVisible():
                        continue
                    name = f"{fp.GetReference() or fp.GetValue()} text '{it.GetText()}'"
                else:
                    name = f"{fp.GetReference() or fp.GetValue()} outline"
                silk.append((side, mask, name, poly_of(it, layer)))
        for it in board.GetDrawings():
            if it.GetLayer() == layer:
                silk.append((side, mask, "board " + (f"text '{it.GetText()}'" if isinstance(it, TEXT) else "graphic"), poly_of(it, layer)))
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    found = []
    for side, mask, name, ps in silk:
        if ps.OutlineCount() == 0:
            continue
        box = ps.BBox()
        box.Inflate(pcbnew.FromMM(2.0))
        for v in vias:
            p = v.GetPosition()
            if not box.Contains(p):
                continue
            for what, r in (("drill", v.GetDrillValue() / 2), ("pad", v.GetWidth(pcbnew.F_Cu) / 2)):
                a = overlap_mm2(ps, circle(p.x, p.y, r + MARGIN))
                if a > 1e-4:
                    found.append((a, f"{side}.Silk {name} over via {what} {v.GetNetname()} at ({mm(p.x):.2f}, {mm(p.y):.2f})"))
                    break
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if not pad.IsOnLayer(mask) or not box.Intersects(pad.GetBoundingBox()):
                    continue
                pp = pcbnew.SHAPE_POLY_SET()
                pad.TransformShapeToPolygon(pp, mask, MARGIN, ERR, pcbnew.ERROR_OUTSIDE)
                a = overlap_mm2(ps, pp)
                if a > 1e-4:
                    q = pad.GetPosition()
                    found.append((a, f"{side}.Silk {name} over pad {fp.GetReference() or fp.GetValue()}.{pad.GetNumber()} "
                                     f"{pad.GetNetname()} at ({mm(q.x):.2f}, {mm(q.y):.2f})"))
    for a, line in sorted(found, reverse=True):
        print(f"  {line}  ({a:.3f} mm2)")
    if found:
        print(f"FAIL — {len(found)} silkscreen overlaps with vias or pads (margin {mm(MARGIN):g} mm, {len(silk)} silk items)")
        sys.exit(1)
    print(f"OK — no silkscreen over vias or pads ({len(silk)} silk items, {len(vias)} vias, margin {mm(MARGIN):g} mm)")


if __name__ == "__main__":
    main()
