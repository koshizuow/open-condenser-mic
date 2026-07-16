* Active Dickson Charge Pump — Transient Simulation
* Replaces boost_tran.sp (Villard/1N4148, now obsolete)
*
* Topology : 3-stage active Dickson, BAT54S Schottky
* Diode input : V_OPA = 24V (regulated)
* Clock       : V_OSC = 15V, 100 kHz, 50% duty (CD40106B on V_OSC rail)
* Expected SS : V_BOOST = V_OPA + N*V_OSC - (N+1)*V_F
*             = 24 + 3*15 - 4*0.2 = 68.2V  (before DZ1 clamp)
* DZ1 clamp   : BZX55C68 (68V) -> clamped to ~68V
* LC filter   : L1=10mH (DCR 8Ω), C_LC=470nF -> corner ~2.3kHz
* Load        : R_GBIAS1+R_GBIAS2 = 94MOhm (capsule at DC ~0.7µA)
* ---------------------------------------------------------------------------
.title Active Dickson Boost — Dickson/BAT54S

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
* LC HV FILTER (L1 10mH + DCR 8Ω, C_LC 470nF)
* ---------------------------------------------------------------------------
R_DCR  VBOOST   LNODE   {L1_DCR}
L1     LNODE    HVFILT  {L1_val}
C_LC   HVFILT   0       {C_LC}  IC=60

* ---------------------------------------------------------------------------
* LOAD: R_GBIAS1 + R_GBIAS2 in series = 94MOhm (capsule DC load ~0.7µA)
* ---------------------------------------------------------------------------
R_load  HVFILT  0  {R_GBIAS}

* ---------------------------------------------------------------------------
* TRANSIENT ANALYSIS
* 15ms total; measure window 10-15ms (settled)
* Max timestep 100ns resolves 100kHz clock and fast diode switching
* ---------------------------------------------------------------------------
.tran 100n 15m 0 100n uic

* ---------------------------------------------------------------------------
* MEASUREMENTS
* ---------------------------------------------------------------------------
.measure tran VBOOST_avg  avg V(VBOOST)  from=10m to=15m
.measure tran VBOOST_max  max V(VBOOST)  from=10m to=15m
.measure tran VBOOST_min  min V(VBOOST)  from=10m to=15m
.measure tran VBOOST_ripple  param='VBOOST_max - VBOOST_min'

.measure tran HV_avg  avg V(HVFILT)  from=10m to=15m
.measure tran HV_max  max V(HVFILT)  from=10m to=15m
.measure tran HV_min  min V(HVFILT)  from=10m to=15m
.measure tran HV_ripple  param='HV_max - HV_min'

.end
