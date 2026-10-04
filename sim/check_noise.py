#!/usr/bin/env python3
"""Check amp_noise_opa1641 SPICE output for input-referred noise threshold.

Reads ngspice batch stdout captured from amp_noise_opa1641.sp and asserts
that the input-referred noise at 1kHz is below LIMIT_NV nV/rtHz.

Usage: python3 check_noise.py <path-to-ngspice-stdout>

Exit 0 on pass, 1 on fail.
"""

import sys
import re
import numpy as np

LIMIT_NV = 60  # nV/rtHz; expected ~40.8 from R_GBIAS Johnson + OPA1641 Vn


def parse_table(output):
    rows = []
    in_table = False
    for line in output.splitlines():
        line = line.strip()
        if re.match(r"^Index\s+frequency", line):
            in_table = True
            continue
        if in_table and re.match(r"^-{10}", line):
            continue
        if in_table and re.match(r"^\d+\s", line):
            parts = line.split()
            try:
                rows.append([float(x) for x in parts[1:]])
            except ValueError:
                pass
    return np.array(rows) if rows else np.zeros((0, 2))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/amp_noise_out.txt"
    with open(path) as f:
        output = f.read()

    data = parse_table(output)
    if data.shape[0] == 0:
        print("FAIL amp_noise: no table data found in ngspice output")
        sys.exit(1)

    freq = data[:, 0]
    inoise = data[:, 1]  # V/rtHz

    idx = int(np.argmin(np.abs(freq - 1000)))
    inoise_nv = inoise[idx] * 1e9

    if inoise_nv > LIMIT_NV:
        print(f"FAIL amp_noise: input-referred noise at {freq[idx]:.0f} Hz = "
              f"{inoise_nv:.1f} nV/rtHz (limit {LIMIT_NV})")
        sys.exit(1)
    else:
        print(f"PASS amp_noise: input-referred noise at {freq[idx]:.0f} Hz = "
              f"{inoise_nv:.1f} nV/rtHz")
        sys.exit(0)


if __name__ == "__main__":
    main()
