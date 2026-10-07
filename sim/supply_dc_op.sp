* Supply DC operating point — phantom source → R1/R2 → Z_REG1/Q1 → V_OPA
* ────────────────────────────────────────────────────────────────────────────
* Solves the regulator's DC operating point with the REAL phantom source:
* V_phantom behind the interface's 6.8 kΩ per leg (IEC 61938 P48), in series
* with the on-board tap resistors R1/R2. Earlier analysis assumed a stiff
* source at the XLR pins, which overstated Z_REG1's current by ~3x (#95).
*
* Loads on V_OPA:
*   - Op-amp quiescent current (I_OP; OPA1641 1.8 mA typ, 2.3 mA max)
*   - R4 + R5 V_MID divider (940 kΩ)
*   - R_ZEN1 into Z_OSC1 (15 V). U3 and the pump draw from Z_OSC1's share,
*     so they add nothing to V_OPA's load while V_OSC stays in regulation.
*
* Checks (FAIL prefix triggers the CI gate in verify.yml):
*   - Z_REG1 stays in regulation, with margin, at the low end of the phantom
*     range and with the op-amp at maximum quiescent current.
*   - Z_REG1 dissipation at the high end of the phantom range stays small.
* ────────────────────────────────────────────────────────────────────────────
.title Supply DC operating point

.options TEMP=27
.include params.inc

.param V_PH  = 48      ; phantom open-circuit voltage (44 / 48 / 52)
.param I_OP  = 1.8m    ; op-amp quiescent current
.param VZ    = 24      ; Z_REG1 breakdown (22.8 / 24 / 25.2 for ±5%)

* Phantom source: two feed legs in the interface, two tap legs on the board
V_ph    PH      0        DC {V_PH}
R_fh    PH      XLR_HOT  {R_PH_FEED}
R_fc    PH      XLR_COLD {R_PH_FEED}
R1      XLR_HOT  RAW     {R_PH_TAP}
R2      XLR_COLD RAW     {R_PH_TAP}

* Z_REG1 + R_REG1 + Q1 emitter follower. Vamm_z measures zener current.
.model ZREG D (Is=1n N=1 Rs=40 Bv={VZ} Ibv=250u)
.model ZOSC D (Is=1n N=1 Rs=20 Bv={V_OSC} Ibv=250u)
.model QN   NPN (Bf=100 Is=1e-14)
R_REG1  RAW     BASE     {R_REG1}
Vamm_z  BASE    ZK       DC 0
D_zreg  0       ZK       ZREG
Q1      RAW     BASE     VOPA   QN

* Loads
I_op    VOPA    0        DC {I_OP}
R4      VOPA    MID      470k
R5      MID     0        470k
R_ZEN1  VOPA    VOSC     {R_ZEN1}
D_zosc  0       VOSC     ZOSC

.control
set filetype=ascii

echo "========================================================"
echo "  supply_dc_op: Z_REG1 operating point, real phantom source"
echo "========================================================"

* ── Case 1: nominal ──────────────────────────────────────────────────────
alterparam V_PH = 48
alterparam I_OP = 1.8m
alterparam VZ   = 24
reset
op
let iz1 = i(Vamm_z)
let it1 = -i(V_ph)
echo "--- nominal: 48V, Iq 1.8mA, Vz 24V ---"
echo "  V_XLR = $&v(xlr_hot) V   V_OPA_RAW = $&v(raw) V   V_OPA = $&v(vopa) V   V_OSC = $&v(vosc) V"
echo "  I(Z_REG1) = $&iz1 A   phantom draw = $&it1 A"

* ── Case 2: phantom low ──────────────────────────────────────────────────
alterparam V_PH = 44
reset
op
let iz2 = i(Vamm_z)
echo "--- 44V, Iq 1.8mA, Vz 24V ---"
echo "  V_OPA_RAW = $&v(raw) V   V_OPA = $&v(vopa) V   I(Z_REG1) = $&iz2 A"

* ── Case 3: phantom low + op-amp max Iq ──────────────────────────────────
alterparam I_OP = 2.3m
reset
op
let iz3 = i(Vamm_z)
echo "--- 44V, Iq 2.3mA, Vz 24V ---"
echo "  V_OPA_RAW = $&v(raw) V   V_OPA = $&v(vopa) V   I(Z_REG1) = $&iz3 A"

* ── Case 4: phantom low + op-amp max Iq + Vz +5% ─────────────────────────
alterparam VZ = 25.2
reset
op
let iz4 = i(Vamm_z)
echo "--- 44V, Iq 2.3mA, Vz 25.2V ---"
echo "  V_OPA_RAW = $&v(raw) V   V_OPA = $&v(vopa) V   I(Z_REG1) = $&iz4 A"

* ── Case 5: phantom high, light load, Vz +5% (max dissipation) ───────────
alterparam V_PH = 52
alterparam I_OP = 1.4m
reset
op
let iz5 = i(Vamm_z)
let pz5 = i(Vamm_z) * v(base)
echo "--- 52V, Iq 1.4mA, Vz 25.2V ---"
echo "  V_OPA_RAW = $&v(raw) V   I(Z_REG1) = $&iz5 A   P(Z_REG1) = $&pz5 W"

* ── Pass/fail assertions ─────────────────────────────────────────────────
* Limits sit below the simulated values (1.51 / 0.92 / 0.59 / 0.30 mA and
* 52 mW) so a change that erodes the headroom fails before regulation is lost.
setplot op1
let a1 = i(Vamm_z)
setplot op2
let a2 = i(Vamm_z)
setplot op3
let a3 = i(Vamm_z)
setplot op4
let a4 = i(Vamm_z)
setplot op5
let a5 = i(Vamm_z) * v(base)

if op1.a1 < 1.2m
  echo "FAIL supply_dc_op: nominal I(Z_REG1) = $&op1.a1 A (min 1.2 mA)"
else
  echo "PASS supply_dc_op: nominal I(Z_REG1) = $&op1.a1 A"
end
if op2.a2 < 0.7m
  echo "FAIL supply_dc_op: 44V I(Z_REG1) = $&op2.a2 A (min 0.7 mA)"
else
  echo "PASS supply_dc_op: 44V I(Z_REG1) = $&op2.a2 A"
end
if op3.a3 < 0.4m
  echo "FAIL supply_dc_op: 44V/Iq-max I(Z_REG1) = $&op3.a3 A (min 0.4 mA)"
else
  echo "PASS supply_dc_op: 44V/Iq-max I(Z_REG1) = $&op3.a3 A"
end
if op4.a4 < 0.15m
  echo "FAIL supply_dc_op: 44V/Iq-max/Vz+5% I(Z_REG1) = $&op4.a4 A (min 0.15 mA)"
else
  echo "PASS supply_dc_op: 44V/Iq-max/Vz+5% I(Z_REG1) = $&op4.a4 A"
end
if op5.a5 > 100m
  echo "FAIL supply_dc_op: 52V P(Z_REG1) = $&op5.a5 W (max 100 mW)"
else
  echo "PASS supply_dc_op: 52V P(Z_REG1) = $&op5.a5 W"
end

.endc

.end
