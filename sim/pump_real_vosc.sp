* Dickson pump with a real V_OSC supply — DZ1 clamp current and V_OSC sag
* ────────────────────────────────────────────────────────────────────────────
* boost_dickson.sp drives the pump from ideal clock sources, so it cannot show
* what the pump costs the 15 V rail. Here the clock drivers are switches fed
* from a V_OSC node that has its real source: V_OPA through R_ZEN1 into Z_OSC1.
*
* Question answered (#112): when DZ1's actual voltage is below the pump's
* open-circuit voltage, how much current does the clamp take, where does it
* come from, and does V_OSC hold?
*
* Result: the clamp current is limited by R_ZEN1's budget to about 0.4 mA with
* DZ1 at -5%. VBOOST then sits at DZ1's voltage and V_OSC sags by ~0.1 V.
*
* Runs in CI at the DZ1 -5% corner (about 5 s). The FAIL limits guard the
* 0.4 mA clamp-current assumption used in supply_dc_op.sp.
* Change DZ1_BV below for other corners: 71.4 / 68 / 66 / 64.6.
* ────────────────────────────────────────────────────────────────────────────
.title Dickson pump with real V_OSC supply

.include params.inc

.param DZ1_BV  = 64.6    ; DZ1 actual breakdown (68 V ±5%)
.param V_OPA_R = 23.4    ; V_OPA as delivered by the emitter follower
.param R_DRV   = 300     ; CD40106B output resistance at 15 V (estimate)

.model BAT  D  (IS=1e-6 N=1.05 BV=100 RS=3)
.model ZOSC D  (Is=1n N=1 Rs=20 Bv={V_OSC} Ibv=250u)
.model ZHV  D  (Is=1n N=1 Rs=10 Bv={DZ1_BV} Ibv=50u)
.model SW   SW (Ron={R_DRV} Roff=1G Vt=0.5 Vh=0.1)

* V_OSC rail: V_OPA → R_ZEN1 → Z_OSC1, with C_U3
V_opa   VOPA  0     DC {V_OPA_R}
R_ZEN1  VOPA  VOSC  {R_ZEN1}
D_zosc  0     VOSC  ZOSC
C_U3    VOSC  0     100n IC={V_OSC}

* Clock drivers as complementary switches between V_OSC and GND, 100 kHz
V_p  P  0  PULSE(0 1 0 20n 20n 4.96u 10u)
V_n  N  0  PULSE(1 0 0 20n 20n 4.96u 10u)
S_ah VOSC CLKA P 0 SW
S_al CLKA 0    N 0 SW
S_bh VOSC CLKB N 0 SW
S_bl CLKB 0    P 0 SW

* 3-stage pump, R_DZ1, DZ1, reservoir and HV filter
D1    VOPA  N1     BAT
Cp1   N1    CLKA   {Cp}   IC=10
D2    N1    N2     BAT
Cp2   N2    CLKB   {Cp}   IC=25
D3    N2    N3     BAT
Cp3   N3    CLKA   {Cp}   IC=40
D4    N3    NPUMP  BAT
R_DZ1 NPUMP VBOOST 680
Cres  VBOOST 0     {Cres} IC=60
Vamm  VBOOST ZK    DC 0
DZ1   0     ZK     ZHV
R_HV  VBOOST HVF   1Meg
C9    HVF   0      {C_LC} IC=60

.control
tran 50n 40m 0 50n uic
meas tran vosc_avg avg v(vosc)   from=35m to=40m
meas tran vb_avg   avg v(vboost) from=35m to=40m
meas tran idz_avg  avg i(Vamm)   from=35m to=40m
meas tran iopa_avg avg i(V_opa)  from=35m to=40m
let iopa = -iopa_avg
echo "========================================================"
echo "  pump_real_vosc: steady state, 35-40 ms"
echo "  V_OSC   = $&vosc_avg V"
echo "  VBOOST  = $&vb_avg V"
echo "  I(DZ1)  = $&idz_avg A"
echo "  I drawn from V_OPA by the V_OSC/pump branch = $&iopa A"
echo "========================================================"

* supply_dc_op.sp assumes the clamp takes at most ~0.4 mA and that V_OSC
* stays near 15 V. Simulated here: 0.39 mA and 14.96 V.
if idz_avg > 0.5m
  echo "FAIL pump_real_vosc: I(DZ1) = $&idz_avg A (max 0.5 mA; supply_dc_op.sp assumes 0.4 mA)"
else
  echo "PASS pump_real_vosc: I(DZ1) = $&idz_avg A"
end
if vosc_avg < 14.5
  echo "FAIL pump_real_vosc: V_OSC = $&vosc_avg V (min 14.5 V)"
else
  echo "PASS pump_real_vosc: V_OSC = $&vosc_avg V"
end
.endc

.end
