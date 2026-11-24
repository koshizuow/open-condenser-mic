* Active Dickson Charge Pump — Transient Simulation
* Replaces boost_tran.sp (Villard/1N4148, now obsolete)
*
* Topology : 3-stage active Dickson, BAT54S Schottky
* Diode input : V_OPA = 24V (regulated)
* Clock       : V_OSC = 15V, 100 kHz, 50% duty (CD40106B on V_OSC rail)
* Expected SS : V_BOOST = V_OPA + N*V_OSC - (N+1)*V_F
*             = 24 + 3*15 - 4*0.2 = 68.2V  (before DZ1 clamp)
* DZ1 clamp   : MMSZ5267B (75V, #121): does not conduct at this nominal point
* HV filter   : mode-selectable LC or RC (see .control block)
*   LC default: L1=10mH (DCR 8Ω), C=470nF, fc≈2.3kHz, Q≈18
*   RC alt    : R=1MΩ (C22935),   C=470nF, fc≈0.34Hz
* Load        : 100MOhm to GND (~0.7µA). Conservative stand-in: in the real
*               circuit R_GBIAS1 feeds the capsule and C8, so HV_FILT has no
*               DC load and settles at VBOOST (#101)
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
* DZ1: 75V zener clamp on V_BOOST (anode=GND, cathode=VBOOST)
* ---------------------------------------------------------------------------
DZ1   0   VBOOST   MMSZ5267B

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
*   RC case: 68V ≈ VBOOST − I_load×R_HV (minimises settling drift in 15ms window)
.param C_LC_IC = 60

R_HV  VBOOST   LNODE   {R_HV}
L_HV  LNODE    HVFILT  {L_HV}
C_LC  HVFILT   0       {C_LC}  IC={C_LC_IC}

* ---------------------------------------------------------------------------
* LOAD: 100MOhm to GND (~0.7µA). The real circuit has no DC path here (see header);
* this load makes HV_FILT sit ~0.67V below VBOOST in the sim only.
* ---------------------------------------------------------------------------
R_load  HVFILT  0  100Meg

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

* ── LC filter (default params: R_HV=8Ω, L_HV=10mH) — for ripple comparison only ──
echo ""
echo "--- LC filter: L=10mH DCR=8Ω, C=470nF, fc≈2.3kHz, Q≈18 ---"
reset
tran 100n 15m 0 100n uic
meas tran VBOOST_avg    avg V(VBOOST)  from=10m to=15m
meas tran HV_avg_LC     avg V(HVFILT)  from=10m to=15m
* Ripple over the last two clock periods (20 us), with the slope between the window's ends taken
* out. Without the 68 V clamp (#121) VBOOST is still creeping up at 15 ms, and max - min would
* read that drift as ripple.
meas tran vb_a find V(VBOOST) at=14.97m
meas tran vb_b find V(VBOOST) at=14.99m
let vb_det = V(VBOOST) - (vb_b - vb_a) / 20u * (time - 14.97m)
meas tran vb_max max vb_det from=14.97m to=14.99m
meas tran vb_min min vb_det from=14.97m to=14.99m
meas tran lc_a find V(HVFILT) at=14.97m
meas tran lc_b find V(HVFILT) at=14.99m
let lc_det = V(HVFILT) - (lc_b - lc_a) / 20u * (time - 14.97m)
meas tran lc_max max lc_det from=14.97m to=14.99m
meas tran lc_min min lc_det from=14.97m to=14.99m
let VBOOST_ripple = vb_max - vb_min
let LC_ripple     = lc_max - lc_min
echo "  VBOOST_avg    = $&VBOOST_avg V"
echo "  VBOOST_ripple = $&VBOOST_ripple V p-p"
echo "  HV_avg  (LC)  = $&HV_avg_LC V"
echo "  HV_ripple(LC) = $&LC_ripple V p-p"

* ── VBOOST assertion: check here before reset clears the meas result ────────
* VBOOST settles near 68.7 V, below the 75 V DZ1; bounds allow ±5V for model/param variation.
let vboost_lo = 63
let vboost_hi = 73
if VBOOST_avg < vboost_lo
  echo "FAIL boost_dickson: VBOOST_avg = $&VBOOST_avg V (min 63 V)"
else
  if VBOOST_avg > vboost_hi
    echo "FAIL boost_dickson: VBOOST_avg = $&VBOOST_avg V (max 73 V)"
  else
    echo "PASS boost_dickson: VBOOST_avg = $&VBOOST_avg V"
  end
end

* ── RC filter (R=1MΩ, L≈0, C=470nF, fc≈0.34Hz) — production PCB config ───────
echo ""
echo "--- RC filter: R=1MΩ (C22935), C=470nF, fc≈0.34Hz ---"
alterparam R_HV = 1Meg
alterparam L_HV = 1p
* IC=68.0: ≈ SS (VBOOST_avg 68.67V − 0.68µA×1MΩ); avoids 470ms settling ramp masking ripple
alterparam C_LC_IC = 68.0
reset
tran 100n 15m 0 100n uic
* write transient data for plot_all.py — RC run (production config)
wrdata _hv_tran.dat v(vboost) v(hvfilt)
meas tran HV_avg_RC     avg V(HVFILT)  from=10m to=15m
meas tran rc_a find V(HVFILT) at=14.97m
meas tran rc_b find V(HVFILT) at=14.99m
let rc_det = V(HVFILT) - (rc_b - rc_a) / 20u * (time - 14.97m)
meas tran rc_max max rc_det from=14.97m to=14.99m
meas tran rc_min min rc_det from=14.97m to=14.99m
let RC_ripple = rc_max - rc_min
echo "  HV_avg  (RC)  = $&HV_avg_RC V"
echo "  HV_ripple(RC) = $&RC_ripple V p-p"

* ── HV_avg_RC assertion ──────────────────────────────────────────────────────
* 1MΩ drop across R_HV into 100MΩ R_GBIAS → ≈0.68V below VBOOST (~68.0V).
let hvrc_lo = 61
let hvrc_hi = 73
if HV_avg_RC < hvrc_lo
  echo "FAIL boost_dickson: HV_avg_RC = $&HV_avg_RC V (min 61 V)"
else
  if HV_avg_RC > hvrc_hi
    echo "FAIL boost_dickson: HV_avg_RC = $&HV_avg_RC V (max 73 V)"
  else
    echo "PASS boost_dickson: HV_avg_RC = $&HV_avg_RC V"
  end
end
.endc

.end
