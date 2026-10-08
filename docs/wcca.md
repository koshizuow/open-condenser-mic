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
| R1, R2 | RT0603BRD072K2L (YAGEO) | 2.2 kΩ | ±0.1% | −0.1% (maximizes current into V_OPA_RAW); changed from 6.8 kΩ for #95 |
| R_REG1 | 0402 thick film (LCSC C25879) | 2.2 kΩ | ±1% | −1% (maximizes current into Z_REG1); 2.2 kΩ → 1.2 kΩ in PR #75, back to 2.2 kΩ for #95 (see below) |
| Z_REG1 | BZT52C24 (MDD) | 24 V | ±5% (22.8–25.2 V) | 25.2 V (maximizes P = Vz·Iz at fixed Iz-driving network) |
| Z_OSC1 | MMSZ15T1G (onsemi) | 15 V | ±5% (14.25–15.75 V) | 15.75 V (drives Dickson pump harder) |
| DZ1 | MMSZ5266BT1G (onsemi) | 68 V | ±5% (64.6–71.4 V) | 64.6 V (lowest clamp voltage → most excess pump current shunted) |
| R_DZ1 | 0603WAF6800T5E (UNI-ROYAL) | 680 Ω | ±1% (673.2–686.8 Ω) | 673.2 Ω (lower resistance → more current reaches DZ1; see #67 Resolution below) |

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

Circuit: `XLR_HOT`/`XLR_COLD` (phantom) → R1‖R2 (2.2 kΩ each) → `V_OPA_RAW` →
R_REG1 (2.2 kΩ) → `V_BASE_REG` → Z_REG1 (K) → GND. Q1's base current is
negligible (high-hFE emitter follower), so nearly all current through
R_REG1 flows through Z_REG1.

Two questions are answered separately, because they need opposite
assumptions about the phantom source:

1. **Maximum dissipation**: assume the stiffest possible source and no load.
2. **Minimum bias current (does it stay in regulation?)**: assume the real
   source impedance and the heaviest load.

### 1. Maximum dissipation (stiff source, no load)

This bound applies the phantom voltage directly at the XLR pins, ignoring the
6.8 kΩ feed resistors that IEC 61938 requires in the supply, and ignores all
load current drawn from `V_OPA`. Both assumptions are deliberately
pessimistic: a compliant supply cannot deliver this much current.

I_z = (V_phantom − V_z) / (R1‖R2 + R_REG1), P_z = I_z × V_z

| Condition | V_phantom | R1‖R2 (−tol) | R_REG1 (−tol) | V_z (+tol) | I_z | P_z | % of P_D (500 mW) |
|---|---|---|---|---|---|---|---|
| Nominal | 48 V | 1098.9 Ω | 2178.0 Ω | 25.2 V | 6.958 mA | 175.3 mW | 35.1% |
| Worst-case low | 44 V | 1098.9 Ω | 2178.0 Ω | 25.2 V | 5.737 mA | 144.6 mW | 28.9% |
| **Worst-case high** | **52 V** | **1098.9 Ω** | **2178.0 Ω** | **25.2 V** | **8.178 mA** | **206.1 mW** | **41.2%** |

**Result: Z_REG1 worst-case dissipation is 206.1 mW, 41.2% of the 500 mW
package rating (>2.4× headroom).**

Thermal check (RθJA = 340 °C/W): ΔT_j = 0.2061 W × 340 °C/W ≈ 70.1 °C above
ambient. At an elevated in-enclosure ambient of 60 °C, T_j ≈ 130 °C, below
the 150 °C junction limit.

With a compliant source (6.8 kΩ feed resistors) the dissipation is far lower:
52 mW at 52 V, V_z +5%, light load (`sim/supply_dc_op.sp`, case 5).

### 2. Operating point and regulation headroom (real source, real load)

The real source is V_phantom behind 6.8 kΩ per leg in the interface, in
series with R1/R2. Loads on `V_OPA` are the op-amp quiescent current
(OPA1641: 1.8 mA typ, 2.3 mA max), the R4+R5 divider and R_ZEN1 into
Z_OSC1. Solved in `sim/supply_dc_op.sp`, which runs in CI with FAIL
thresholds on each row:

| Condition | V_phantom | Op-amp Iq | V_z | V_OPA_RAW | V_OPA | I_z | CI minimum |
|---|---|---|---|---|---|---|---|
| Nominal | 48 V | 1.8 mA | 24 V | 27.48 V | 23.42 V | 1.51 mA | 1.2 mA |
| Phantom low | 44 V | 1.8 mA | 24 V | 26.15 V | 23.39 V | 0.92 mA | 0.7 mA |
| Phantom low, Iq max | 44 V | 2.3 mA | 24 V | 25.41 V | 23.36 V | 0.59 mA | 0.4 mA |
| Phantom low, Iq max, V_z +5% | 44 V | 2.3 mA | 25.2 V | 25.95 V | 24.53 V | 0.30 mA | 0.15 mA |
| Phantom low, Iq max, DZ1 clamping | 44 V | 2.3 mA | 24 V | 24.79 V | 23.33 V | 0.31 mA | 0.2 mA |
| All four stacked (V_z +5% and DZ1 clamping) | 44 V | 2.3 mA | 25.2 V | 25.32 V | 24.46 V | 0.03 mA | V_OPA ≥ 24.2 V |

**DZ1 clamp current as a load (#112).** When DZ1's actual voltage is below the
pump's open-circuit voltage it clamps `VBOOST`, and the clamp current is drawn
from `V_OPA`: once through the diode chain and three times through the clock
drivers on `V_OSC`. `sim/pump_real_vosc.sp` models the pump with its real
`V_OSC` supply and gives 0.39 mA with DZ1 at −5%, limited by R_ZEN1's budget;
`V_OSC` sags to 14.96 V and `VBOOST` sits at DZ1's voltage. The last two rows
above add 0.4 mA for this. With all four tolerances stacked Z_REG1 is at its
knee (0.03 mA), but `V_OPA` has moved by only 0.07 V, so the rail still holds.
At 46 V phantom the same stack leaves 0.32 mA. No component change is made
for this corner.

Phantom draw at the nominal point is 4.56 mA (P48 rated maximum: 10 mA).

**History (#95).** With the earlier R1/R2 = 6.8 kΩ and R_REG1 = 1.2 kΩ the same
analysis gives I_z = 0.41 mA at nominal and zero (out of regulation) in all
three low-phantom rows. PR #75 lowered R_REG1 to raise I_z, but I_z is set by
the whole feed path (interface 6.8 kΩ + R1/R2 + R_REG1), and R1/R2 dominated.
Lowering R1/R2 to 2.2 kΩ supplies the headroom. R_REG1 goes back to 2.2 kΩ
because, with R1/R2 fixed, a larger R_REG1 both improves ripple rejection
into `V_BASE_REG` and keeps the stiff-source dissipation bound in section 1
inside the thermal limit (1.2 kΩ would give 295 mW and T_j ≈ 160 °C at 60 °C
ambient under that bound).

## DZ1 (68 V) — active Dickson charge-pump clamp, with R_DZ1 series resistor

DZ1 does not sit behind a large resistive bias network like Z_REG1 — it
clamps the Dickson pump's output (`VBOOST`) through a 680 Ω series resistor
(`R_DZ1`, 0603), ahead of the 1 MΩ `R_HV` filter resistor. `R_DZ1` sits
between the pump's raw output (net `N_PUMP`, D2 pin 2/K) and the `VBOOST`
rail (`Cres1`/`DZ1`/`R_HV`), and shifts most of the excess clamp current's
I²R dissipation off DZ1 and onto itself. The pump's characteristic drive
impedance and switching dynamics make a closed-form hand calculation
unreliable, so this case was evaluated by transient SPICE simulation
(`sim/boost_dickson.sp` topology plus `R_DZ1`, RC filter production config,
steady-state window 10–15 ms), using `.options savecurrents` and a 0 V
ammeter in series with DZ1 to measure its conduction current directly, with
`V_OPA`/`V_OSC` source amplitudes and the `DZ1`/`R_DZ1` tolerance bounds
from the table above all stacked in the direction that maximizes DZ1's
dissipation.

| Condition | V_OPA (Z_REG1 out) | V_OSC (Z_OSC1 out) | DZ1 Bv | R_DZ1 | I(DZ1) | P(DZ1) | % of P_D (500 mW) |
|---|---|---|---|---|---|---|---|
| Nominal | 24 V | 15 V | 68 V | 680 Ω | 0.27 mA | 18.4 mW | 3.7% |
| **Worst-case combined** | **25.2 V** | **15.75 V** | **64.6 V** | **673.2 Ω** | **4.40 mA** | **284.5 mW** | **56.9%** |

**Result: DZ1 worst-case combined dissipation is 284.5 mW, 56.9% of the
500 mW SOD-123 package rating — comfortable margin (>1.7× headroom).**

This 4.40 mA figure assumes ideal `V_OPA` and `V_OSC` sources. It is an upper
bound for dissipation, not an operating point: with the real `V_OSC` supply
(6.8 kΩ from `V_OPA`) the clamp current cannot exceed about 0.4 mA, which is
about 25 mW in DZ1 (`sim/pump_real_vosc.sp`, #112).

`R_DZ1` itself: worst-case dissipation 13.0 mW, 13.0% of its 100 mW 0603
rating — ample margin.

Downstream impact: at this worst-case corner, `HV_FILT` averages 67.21 V and
the capsule polarization voltage (`HV_FILT` − `V_MID`) is 55.21 V, consistent
with the ~55 V/67.3 V targets elsewhere in this document — `R_DZ1` adds no
material drop to the HV rail.

Thermal check (RθJA = 340 °C/W): ΔT_j = 0.2845 W × 340 °C/W ≈ 96.7 °C above
ambient — the same self-heating budget used for Z_REG1's check above. This
leaves headroom to an ambient of ~53 °C before T_j reaches the SOD-123's
150 °C junction limit at this specific combined worst-case corner (all four
independent tolerances stacked simultaneously, which is deliberately more
pessimistic than real-world piece-to-piece variation). Typical indoor use
stays well under this (room temperature plus a few degrees of enclosure
self-heating); sustained exposure above ~53 °C ambient — e.g. direct sun,
a car interior, or close proximity to incandescent stage lighting — would
erode this margin and should prompt re-checking with a larger R_DZ1 (which
trades a small amount of additional HV_FILT drop for lower DZ1 dissipation)
if that operating environment is expected.

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
2. Inserting `R_DZ1` (680 Ω nominal) in series between node `N3`'s output
   diode (D4) and DZ1's cathode, i.e. `R_DZ1_test N_PUMP VBOOST {R_DZ1}`
   then a 0 V series ammeter and DZ1 between `VBOOST` and ground
   (`Vamm_dz1 0 DZ1_A DC 0` then `DZ1 DZ1_A VBOOST BZX55C68`), measuring
   `i(Vamm_dz1)` in the `.control` block's RC section.
3. Overriding `VOPA`, `VCLKA`/`VCLKB` source amplitudes, `R_DZ1`, and/or
   adding a `BZX55C68_LO` model variant with `Bv=64.6` for the tolerance
   corners in the table above.
