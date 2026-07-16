* Active Dickson Charge Pump — Transient Simulation
* Replaces boost_tran.sp (Villard/1N4148, now obsolete)
*
* Topology : 3-stage active Dickson, BAT54S Schottky
* Diode input : V_OPA = 24V (regulated)
* Clock       : V_OSC = 15V, 100 kHz, 50% duty (CD40106B on V_OSC rail)
* Expected SS : V_BOOST = V_OPA + N*V_OSC - (N+1)*V_F
*             = 24 + 3*15 - 4*0.2 = 68.2V  (before DZ1 clamp)
* DZ1 clamp   : BZX55C68 (68V) -> clamped to ~68V
* HV filter   : mode-selectable LC or RC (see .control block)
*   LC default: L1=10mH (DCR 8Ω), C=470nF, fc≈2.3kHz, Q≈18
*   RC alt    : R=1MΩ (C22935),   C=470nF, fc≈0.34Hz
* Load        : R_GBIAS1 = 100MOhm (capsule at DC ~0.7µA)
* ---------------------------------------------------------------------------
.title Active Dickson Boost — LC vs RC HV filter comparison

.include params.inc
.include models/passives.lib

* ---------------------------------------------------------------------------
* SUPPLIES
* ---------------------------------------------------------------------------
VOPA   VOPA   0   DC {V_OPA}
* V_OSC modeled as ideal 15V (Z_OSC shunt reg)
* Clock sources drive the pump caps directly

* ---------------------------------------------------------------------------
* CLOCKS  (CD40106B output: 0 <-> 15V, 100kHz, 50% duty)
* CLKA: low-to-high at t=0
* CLKB: complement (high-to-low at t=0)
* ---------------------------------------------------------------------------
VCLKA  CLKA  0  PULSE(0 {V_OSC} 0 10n 10n 4.99u 10u)
VCLKB  CLKB  0  PULSE({V_OSC} 0 0 10n 10n 4.99u 10u)

* ---------------------------------------------------------------------------
* 3-STAGE ACTIVE DICKSON MULTIPLIER
*
*   VOPA --D1--> N1 --D2--> N2 --D3--> N3 --D4--> VBOOST
*                |           |           |
*              Cp1(CLKA)  Cp2(CLKB)  Cp3(CLKA)
*
* On CLKA high: N1 and N3 are pumped up; D1/D3 conduct
* On CLKB high: N2 is pumped up; D2/D4 conduct
* ---------------------------------------------------------------------------
D1   VOPA    N1      BAT54S
Cp1  N1      CLKA    {Cp}
D2   N1      N2      BAT54S
Cp2  N2      CLKB    {Cp}
D3   N2      N3      BAT54S
Cp3  N3      CLKA    {Cp}
D4   N3      VBOOST  BAT54S

* Reservoir cap (IC near expected SS to speed convergence)
Cres  VBOOST  0  {Cres}  IC=60

* ---------------------------------------------------------------------------
* DZ1: 68V zener clamp on V_BOOST (anode=GND, cathode=VBOOST)
* ---------------------------------------------------------------------------
DZ1   0   VBOOST   BZX55C68

* ---------------------------------------------------------------------------
* HV FILTER — parameterised; defaults to LC mode
*   LC: R_HV=L1_DCR (8Ω),  L_HV=L1_val (10mH)
*   RC: R_HV=1MΩ,           L_HV=1pH (≈wire)
* alterparam switches between modes in the .control block below.
* ---------------------------------------------------------------------------
.param R_HV    = {L1_DCR}
.param L_HV    = {L1_val}
* C_LC_IC: initial condition for HVFILT capacitor
*   LC case: 60V (settles within ~5ms via resonance)
*   RC case: 67V ≈ VBOOST_clamp − I_load×R_HV (minimises settling drift in 15ms window)
.param C_LC_IC = 60

R_HV  VBOOST   LNODE   {R_HV}
L_HV  LNODE    HVFILT  {L_HV}
C_LC  HVFILT   0       {C_LC}  IC={C_LC_IC}

* ---------------------------------------------------------------------------
* LOAD: R_GBIAS1 = 100MOhm (capsule DC load ~0.7µA)
* ---------------------------------------------------------------------------
R_load  HVFILT  0  {R_GBIAS}

* ---------------------------------------------------------------------------
* CONTROL: run LC then RC, print ripple comparison
* 15ms sim / 10-15ms measure window (LC settles in <5ms; IC=60 pre-charges
* C_LC so RC ripple is measurable even though RC time constant is 470ms)
* ---------------------------------------------------------------------------
.control
set filetype=ascii

echo "========================================================"
echo "  boost_dickson: LC vs RC HV filter comparison"
echo "========================================================"

* ── LC filter (default params: R_HV=8Ω, L_HV=10mH) ──────────
echo ""
echo "--- LC filter: L=10mH DCR=8Ω, C=470nF, fc≈2.3kHz, Q≈18 ---"
reset
tran 100n 15m 0 100n uic
meas tran VBOOST_avg    avg V(VBOOST)  from=10m to=15m
meas tran VBOOST_max    max V(VBOOST)  from=10m to=15m
meas tran VBOOST_min    min V(VBOOST)  from=10m to=15m
meas tran HV_avg_LC     avg V(HVFILT)  from=10m to=15m
meas tran HV_max_LC     max V(HVFILT)  from=10m to=15m
meas tran HV_min_LC     min V(HVFILT)  from=10m to=15m
let VBOOST_ripple = VBOOST_max - VBOOST_min
let LC_ripple     = HV_max_LC  - HV_min_LC
echo "  VBOOST_avg    = $&VBOOST_avg V"
echo "  VBOOST_ripple = $&VBOOST_ripple V p-p"
echo "  HV_avg  (LC)  = $&HV_avg_LC V"
echo "  HV_ripple(LC) = $&LC_ripple V p-p"

* ── RC filter (R=1MΩ, L≈0, C=470nF, fc≈0.34Hz) ──────────────
echo ""
echo "--- RC filter: R=1MΩ (C22935), C=470nF, fc≈0.34Hz ---"
alterparam R_HV = 1Meg
alterparam L_HV = 1p
* IC=67.3: ≈ SS (VBOOST_avg 67.97V − 0.67µA×1MΩ); avoids 470ms settling ramp masking ripple
alterparam C_LC_IC = 67.3
reset
tran 100n 15m 0 100n uic
meas tran HV_avg_RC     avg V(HVFILT)  from=10m to=15m
meas tran HV_max_RC     max V(HVFILT)  from=10m to=15m
meas tran HV_min_RC     min V(HVFILT)  from=10m to=15m
let RC_ripple = HV_max_RC - HV_min_RC
echo "  HV_avg  (RC)  = $&HV_avg_RC V"
echo "  HV_ripple(RC) = $&RC_ripple V p-p"
.endc

.end
