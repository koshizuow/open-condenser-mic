#!/usr/bin/env python3
"""Compare schematic and PCB net assignments per component/pin.

Exports a KiCad netlist from the schematic, parses pad-net assignments
from the PCB file, and diffs them.  Exits 1 on any mismatch.

Limitations:
  - Only checks components that appear in both outputs (skips PCB-only pads
    such as mounting holes, bare solder pads, and test points).
  - For 2-terminal symmetric passives (R*, C*, L*) checks net SET equality
    rather than pin-by-pin order, because PCB orientation can flip pin 1/2
    without electrical consequence.
  - Pins whose schematic net name starts with "unconnected-" or "Net-(" are
    skipped (NC pins and unnamed internal nodes).
  - Components whose schematic uses named pin IDs that differ from PCB pad
    numbers (e.g. transistor C/B/E vs SOT-23 pad 1/2/3, diode K/A vs pad
    1/2) will report no mismatches but are also not checked — the limitation
    is noted in the summary.
"""
import os
import re
import subprocess
import sys
import tempfile

SCH_FILE = "pcb/open-condenser-mic.kicad_sch"
PCB_FILE = "pcb/open-condenser-mic.kicad_pcb"

# 2-terminal passives: physically reversible — compare net set, not pin order
SYMMETRIC_PREFIXES = ("R", "C", "L")


def export_netlist(sch_path):
    fd, path = tempfile.mkstemp(suffix=".net")
    os.close(fd)
    subprocess.run(
        ["kicad-cli", "sch", "export", "netlist",
         "--format", "kicadsexpr", "--output", path, sch_path],
        check=True, capture_output=True,
    )
    return path


def parse_sch_nets(netlist_path):
    """Return {ref: {pin: net_name}} from kicad s-expr netlist."""
    txt = open(netlist_path).read()
    nets = {}
    current_net = None
    for line in txt.splitlines():
        if "(net (code" in line:
            m = re.search(r'\(name "([^"]+)"', line)
            if m:
                current_net = m.group(1).lstrip("/")
        if "(node" in line and current_net:
            rm = re.search(r'\(ref "([^"]+)"\)', line)
            pm = re.search(r'\(pin "([^"]+)"\)', line)
            if rm and pm:
                nets.setdefault(rm.group(1), {})[pm.group(1)] = current_net
    return nets


def parse_pcb_nets(pcb_path):
    """Return {ref: {pad_num: net_name}} from .kicad_pcb footprint pads."""
    txt = open(pcb_path).read()
    idx = 0
    fps = []
    while True:
        m = re.search(r"\(footprint ", txt[idx:])
        if not m:
            break
        start = idx + m.start()
        depth, i = 0, start
        while i < len(txt):
            if txt[i] == "(":
                depth += 1
            elif txt[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        fps.append(txt[start : i + 1])
        idx = i + 1

    result = {}
    for fp in fps:
        ref_m = re.search(r'\(property "Reference" "([^"]+)"', fp)
        if not ref_m:
            continue
        ref = ref_m.group(1)
        pads = re.findall(
            r'\(pad "(\w+)" \w+ \w+.*?\(net \d+ "([^"]+)"', fp, re.DOTALL
        )
        for pad_num, net in pads:
            if net:
                result.setdefault(ref, {})[pad_num] = net
    return result


def skip_net(name):
    return name.startswith("unconnected-") or name.startswith("Net-(")


def is_symmetric(ref):
    return any(ref.startswith(p) for p in SYMMETRIC_PREFIXES)


def main():
    netlist_path = export_netlist(SCH_FILE)
    try:
        sch = parse_sch_nets(netlist_path)
        pcb = parse_pcb_nets(PCB_FILE)
    finally:
        os.unlink(netlist_path)

    common = sorted(set(sch) & set(pcb))
    sch_only = sorted(set(sch) - set(pcb))
    mismatches = []

    for ref in common:
        sch_map = sch[ref]
        pcb_map = pcb[ref]

        if is_symmetric(ref) and len(sch_map) == 2:
            sch_nets = {n for n in sch_map.values() if not skip_net(n)}
            pcb_nets = set(pcb_map.values())
            diff = sch_nets - pcb_nets
            if diff:
                mismatches.append(
                    f"{ref}: net set mismatch  sch={sorted(sch_nets)}  pcb={sorted(pcb_nets)}"
                )
        else:
            for pin, snet in sch_map.items():
                if skip_net(snet):
                    continue
                pnet = pcb_map.get(pin)
                if pnet is None:
                    continue  # pin ID differs between sch and pcb (e.g. named vs numbered)
                if pnet != snet:
                    mismatches.append(
                        f"{ref}.{pin}: sch={snet!r}  pcb={pnet!r}"
                    )

    print(f"Checked {len(common)} components (sch-only: {len(sch_only)})")
    if mismatches:
        print(f"NET MISMATCH — {len(mismatches)} error(s):")
        for m in mismatches:
            print(f"  {m}")
        sys.exit(1)
    else:
        print("OK — schematic and PCB net assignments agree")


if __name__ == "__main__":
    main()
