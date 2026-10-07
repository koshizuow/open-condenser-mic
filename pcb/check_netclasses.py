#!/usr/bin/env python3
"""Check that the generated .kicad_pro still carries gen_project's net classes.

gen_pcb.py's SaveBoard() rewrites the project file. If it ever stops
re-applying the net classes, the HV clearance rule disappears and DRC
silently falls back to Default (#98). Run after gen_pcb.py, before DRC:

    python3 pcb/check_netclasses.py [--name PROJECT_NAME]
"""

import argparse
import json
import os
import sys

import gen_project


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", default="open-condenser-mic")
    name = p.parse_args().name

    want = gen_project.build_project(name)["net_settings"]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.kicad_pro")
    with open(path) as f:
        got = json.load(f)["net_settings"]

    errors = []
    got_classes = {c["name"]: c for c in got["classes"]}
    for c in want["classes"]:
        g = got_classes.get(c["name"])
        if g is None:
            errors.append(f"net class {c['name']!r} missing")
        elif abs(g["clearance"] - c["clearance"]) > 1e-6:
            errors.append(f"net class {c['name']!r} clearance {g['clearance']} != {c['clearance']}")

    got_patterns = {(x["pattern"], x["netclass"]) for x in got.get("netclass_patterns") or []}
    for x in want["netclass_patterns"]:
        if (x["pattern"], x["netclass"]) not in got_patterns:
            errors.append(f"pattern {x['pattern']!r} -> {x['netclass']!r} missing")

    if errors:
        print(f"FAIL — {os.path.basename(path)} net classes differ from gen_project.py:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"OK — {len(want['classes'])} net classes, {len(want['netclass_patterns'])} patterns present")


if __name__ == "__main__":
    main()
