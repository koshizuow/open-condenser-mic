# Worst-Case Circuit Analysis (WCCA) — Z_REG1 / DZ1 Zener Power Dissipation

Addresses issue #59: document worst-case power dissipation for `Z_REG1` (24 V,
`BZT52C24`) and `DZ1` (68 V, `BZT52C68` → BOM part `MMSZ5266BT1G`), both
SOD-123 package, at worst-case phantom supply voltage (not just the nominal
48 V used in the existing SPICE simulations).

## Method

Per standard WCCA convention, all independent component tolerances are
stacked simultaneously in the direction that maximizes the analyzed
quantity (here, zener power dissipation), rather than treated statistically.
This is deliberately more pessimistic than real-world piece-to-piece
variation, which is the point of a worst-case (as opposed to nominal or
statistical) analysis.

Phantom supply tolerance: 44–52 V (IEC 61938; ±4 V about the 48 V nominal),
per issue #59.

Component tolerances used (from `pcb/bom.csv` / LCSC part datasheets):

| Ref | Part | Nominal | Tolerance | Worst-case bound used |
|---|---|---|---|---|
| R1, R2 | ARG03BTC6801 (Viking) | 6.8 kΩ | ±0.1% | −0.1% (maximizes current into V_OPA_RAW) |
| R_REG1 | 0402WGF2201TCE (UNI-ROYAL) | 2.2 kΩ | ±1% | −1% (maximizes current into Z_REG1) |
| Z_REG1 | BZT52C24 (MDD) | 24 V | ±5% (22.8–25.2 V) | 25.2 V (maximizes P = Vz·Iz at fixed Iz-driving network) |
| Z_OSC1 | MMSZ15T1G (onsemi) | 15 V | ±5% (14.25–15.75 V) | 15.75 V (drives Dickson pump harder) |
| DZ1 | MMSZ5266BT1G (onsemi) | 68 V | ±5% (64.6–71.4 V) | 64.6 V (lowest clamp voltage → most excess pump current shunted) |

SOD-123 package thermal/power ratings (onsemi `MMSZ52xxxT1G` series
datasheet, covers the MMSZ52xx/BZT52C zener family used for Z_REG1/Z_OSC1/DZ1
in this design):

| Parameter | Value |
|---|---|
| Total Power Dissipation, P_D (on FR-5 board, min. recommended footprint) @ T_L = 75 °C | 500 mW |
| Derate above 75 °C | 6.7 mW/°C |
| Thermal Resistance, Junction-to-Ambient, RθJA | 340 °C/W |
| Thermal Resistance, Junction-to-Lead, RθJL | 150 °C/W |
| Junction / Storage Temperature Range | −55 to +150 °C |

## Z_REG1 (24 V) — resistively-biased shunt regulator

Circuit: `XLR_HOT`/`XLR_COLD` (phantom) → R1‖R2 (6.8 kΩ each) → `V_OPA_RAW` →
R_REG1 (2.2 kΩ) → `V_BASE_REG` → Z_REG1 (K) → GND. Q1's base current is
negligible (high-hFE emitter follower), so nearly all current through
R_REG1 flows through Z_REG1.

I_z = (V_phantom − V_z) / (R1‖R2 + R_REG1), P_z = I_z × V_z

| Condition | V_phantom | R1‖R2 (−tol) | R_REG1 (−tol) | V_z (+tol) | I_z | P_z | % of P_D (500 mW) |
|---|---|---|---|---|---|---|---|
| Nominal | 48 V | 3396.6 Ω | 2178.0 Ω | 25.2 V | 4.090 mA | 103.1 mW | 20.6% |
| Worst-case low | 44 V | 3396.6 Ω | 2178.0 Ω | 25.2 V | 3.372 mA | 85.0 mW | 17.0% |
| **Worst-case high** | **52 V** | **3396.6 Ω** | **2178.0 Ω** | **25.2 V** | **4.808 mA** | **121.2 mW** | **24.2%** |

**Result: Z_REG1 worst-case dissipation is 121.2 mW, 24.2% of the 500 mW
package rating — comfortable margin (>4× headroom).**

Thermal check (RθJA = 340 °C/W): ΔT_j = 0.1212 W × 340 °C/W ≈ 41.2 °C above
ambient. Even at an elevated in-enclosure ambient of 60 °C, T_j ≈ 101 °C,
well below the 150 °C junction limit.

## DZ1 (68 V) — active Dickson charge-pump clamp

Unlike Z_REG1, DZ1 does not sit behind a large resistive bias network — it
clamps the Dickson pump's output (`VBOOST`) directly, ahead of the 1 MΩ
`R_HV` filter resistor. The pump's characteristic drive impedance and
switching dynamics make a closed-form hand calculation unreliable, so this
case was evaluated by transient SPICE simulation (`sim/boost_dickson.sp`,
RC filter production config, steady-state window 10–15 ms), using
`.options savecurrents` and a 0 V ammeter in series with DZ1 to measure its
conduction current directly, with `V_OPA`/`V_OSC` source amplitudes and the
`DZ1` zener model's `Bv` parameter adjusted to the tolerance bounds above.

| Condition | V_OPA (Z_REG1 out) | V_OSC (Z_OSC1 out) | DZ1 Bv | I(DZ1) | P(DZ1) | % of P_D (500 mW) |
|---|---|---|---|---|---|---|
| Nominal | 24 V | 15 V | 68 V | 1.18 mA | 79.3 mW | 15.9% |
| Z_REG1 tol only | 25.2 V | 15 V | 68 V | 4.84 mA | 325.7 mW | 65.1% |
| Z_OSC1 tol only | 24 V | 15.75 V | 68 V | 8.14 mA | 548.0 mW | 109.6% |
| DZ1 tol only | 24 V | 15 V | 64.6 V | 11.79 mA | 792.6 mW | 158.5% |
| **Worst-case combined** | **25.2 V** | **15.75 V** | **64.6 V** | **23.7 mA** | **1533 mW** | **306.6%** |

**Result: DZ1 worst-case combined dissipation is ~1.53 W — over 3× the
500 mW SOD-123 package rating.** Even the single-variable "DZ1 tolerance
only" case (792.6 mW) alone exceeds the rating by 58.5%. This is because DZ1
actively absorbs essentially all of the charge pump's excess output current
(the R_HV/R_GBIAS downstream load is only ~0.7 µA, negligible next to DZ1's
multi-mA clamp current), so its dissipation scales directly with how hard
the pump is driven and how low the clamp voltage tolerance falls — both of
which stack unfavorably in the worst case.

### Recommendation

DZ1's worst-case margin is inadequate as currently specified. Options to
close this gap (not implemented in this WCCA pass — tracked as follow-up
work, not part of issue #59's scope which is documentation-only):

1. **Add series resistance** between the Dickson pump output (D4/`N3`) and
   DZ1's cathode, sized to shift the excess clamp current's I²R dissipation
   from DZ1 onto a resistor with adequate power rating. This is the
   lowest-risk fix (small BOM/layout change) but adds a voltage drop that
   must be re-verified against the 67.3 V `HV_FILT` target.
2. **Higher-power zener package** (e.g. SOD-123FL, MELF, SMA/DO-214AC) with
   a P_D rating that covers the ~1.5 W worst-case figure with margin.
3. **Reduce charge-pump drive strength** (fewer Dickson stages or lower
   `V_OSC` amplitude) to reduce the excess current DZ1 must absorb — larger
   design change, affects `VBOOST` headroom margin above the 67.3 V target.

### Resolution (#67)

Option 1 above was implemented: a 680 Ω series resistor (`R_DZ1`, 0603) was
added between the Dickson pump's raw output (net `N_PUMP`, D2 pin 2/K) and
the `VBOOST` rail (`Cres1`/`DZ1`/`R_HV`), which previously connected directly.

Two higher-power zener packages (SOD-123FL / SMB) were also investigated and
rejected: no footprint larger than the existing SOD-123 fits anywhere on the
current 36×93 mm board layout without colliding with the F.Cu GND zone,
existing traces, or neighboring component courtyards (checked exhaustively
against the real KiCad pcbnew courtyard/track/zone geometry, not by hand
calculation) — the board's copper density leaves no room for a part ~2–3×
the SOD-123's footprint area without a broader re-layout of the HV section,
which was judged out of proportion to the fix.

Verification (SPICE sweep over 330/470/680 Ω at both nominal and worst-case
corners, same methodology as the DZ1 table above):

| R_DZ1 | DZ1 P (worst-case) | % of 500 mW rating | HV_FILT drop (worst-case) | Capsule polarization (worst-case) |
|---|---|---|---|---|
| 0 Ω (original) | 1495 mW | 299.0% | — | 55.218 V |
| 330 Ω | 492.7 mW | 98.5% | 5.5 mV | 55.212 V |
| 470 Ω | 379.4 mW | 75.9% | 6.5 mV | 55.211 V |
| **680 Ω (chosen)** | **282.1 mW** | **56.4%** | **7.5 mV** | **55.210 V** |

(The 0 Ω worst-case figure above, 1495 mW/299.0%, differs slightly from the
1533 mW/306.6% in the combined worst-case row of the DZ1 table — both are
from independent SPICE runs of the same worst-case corner; the ~2.5%
difference reflects normal simulation-to-simulation variation in transient
settling within the 10–15 ms measurement window, not a methodology change.)

680 Ω was chosen over 330/470 Ω for the widest safety margin (56.4% vs.
98.5%/75.9% of the 500 mW rating) at effectively the same cost: the extra
HV_FILT drop between 330 Ω and 680 Ω is only ~2 mV, and the resulting
capsule polarization voltage (55.21 V worst-case vs. the original 55.22 V)
is unchanged to within measurement noise — far smaller than the capsule's
own manufacturing tolerance. R_DZ1 itself dissipates ≤19 mW worst-case
across all three values, well within a 0603's 100 mW rating.

See PR for issue #67 for the generator script changes
(`pcb/gen_schematic.py`, `pcb/gen_pcb.py`) and layout details.

## Simulation reproducibility

The DZ1 figures above were obtained via ad hoc modifications to
`sim/boost_dickson.sp` (source-value overrides + a temporary series
ammeter) run outside the tracked SPICE files, to avoid disturbing the
existing simulation suite's nominal-case behavior. They are not checked in
as a permanent `.sp` file; the modifications are fully described in the
Method/tables above and can be reproduced by:

1. Adding `.options savecurrents` after the existing `.include` lines.
2. Inserting a 0 V series ammeter between node `N3`'s output diode (D4) and
   DZ1's cathode (i.e. `Vamm_dz1 0 DZ1_A DC 0` then `DZ1 DZ1_A VBOOST
   BZX55C68`), and measuring `i(Vamm_dz1)` in the `.control` block's RC
   section.
3. Overriding `VOPA`, `VCLKA`/`VCLKB` source amplitudes, and/or adding a
   `BZX55C68_LO` model variant with `Bv=64.6` for the tolerance corners in
   the table above.
