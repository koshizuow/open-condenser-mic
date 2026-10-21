* Dickson pump with a real V_OSC supply, worst-case corners (#121)
* ────────────────────────────────────────────────────────────────────────────
* boost_dickson.sp drives the pump from ideal clock sources, so it cannot show
* what the clock and the pump cost the 15 V rail. Here the clock drivers are
* switches fed from a V_OSC node with its real source: V_OPA through R_ZEN1
* into Z_OSC1, less the clock's own supply current I_OSC.
*
* #121: on v3.5 the RC Schmitt oscillator (U3A, R_OSC1, C10) drew about 1.5 mA,
* all of R_ZEN1's current, so V_OSC sat at 13.8 V and VBOOST at 63 V. The fix
* modelled here:
*   - U3 becomes an ICM7556 (dual CMOS 555, SOIC-14 like the CD40106B, same
*     supply and ground pins; 120 uA typ / 600 uA max at 15 V, no crowbar
*     current). Timer A is the oscillator with R_OSC1 and C10, timer B an
*     inverter for CLKB. I_OSC covers both timers and the pump drive: 0.22 mA
*     typical, 0.75 mA worst, 0.1 mA least.
*   - Z_OSC1 a low-current 15 V zener (MMSZ4702, 15 V +-5% at 50 uA), so it
*     regulates on the few hundred uA left to it. Its slope resistance at a
*     few hundred uA is not in the data at hand; 300 ohm is assumed.
*   - DZ1 75 V (MMSZ5267B, +-5%) so that it only protects. At the high corner
*     with DZ1 at -5% it starts to conduct (about 0.1 mA); Z_OSC1 keeps its
*     current, so V_OSC holds. With the 68 V part it would clamp on most boards.
*
* Corners (V_OPA from supply_dc_op.sp):
*   high: V_OPA 24.6 V (52 V phantom, Z_REG1 +5%, light load), Z_OSC1 +5%,
*         I_OSC 0.1 mA, DZ1 -5% (71.25 V): does DZ1 conduct, how high VBOOST.
*   low:  V_OPA 22.2 V (44 V phantom, Z_REG1 -5%, op-amp max Iq), Z_OSC1 -5%,
*         I_OSC 0.75 mA: does Z_OSC1 keep a current, how low VBOOST.
*   nom:  V_OPA 23.4 V, all nominal, I_OSC 0.22 mA.
* Each corner is a 40 ms transient (about 5 s).
* ────────────────────────────────────────────────────────────────────────────
.title Dickson pump with real V_OSC supply

.include params.inc

.param DZ1_BV  = 75      ; DZ1 actual breakdown (75 V +-5%: 71.25 / 75 / 78.75)
.param V_OPA_R = 23.4    ; V_OPA as delivered by the emitter follower
.param VZO     = 15      ; Z_OSC1 actual voltage at 50 uA (14.25 / 15 / 15.75)
.param I_OSC   = 0.22m   ; clock supply current from V_OSC (0.1m / 0.22m / 0.75m)
.param R_DRV   = 300     ; CD40106B output resistance at 15 V (estimate)

.model BAT  D  (IS=1e-6 N=1.05 BV=100 RS=3)
.model ZOSC D  (Is=1n N=1 Rs=300 Bv={VZO} Ibv=50u)
.model ZHV  D  (Is=1n N=1 Rs=10 Bv={DZ1_BV} Ibv=10u)
.model SW   SW (Ron={R_DRV} Roff=1G Vt=0.5 Vh=0.1)

* V_OSC rail: V_OPA → R_ZEN1 → Z_OSC1, with C_U3
V_opa   VOPA  0     DC {V_OPA_R}
R_ZEN1  VOPA  VOSC  {R_ZEN1}
Vamm_o  VOSC  ZO    DC 0
D_zosc  0     ZO    ZOSC
I_osc   VOSC  0     DC {I_OSC}
C_U3    VOSC  0     100n IC={VZO}

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
set filetype=ascii
echo "========================================================"
echo "  pump_real_vosc: corners, steady state 35-40 ms (#121)"
echo "========================================================"
* ── high corner ──
alterparam V_OPA_R = 24.6
alterparam VZO = 15.75
alterparam I_OSC = 0.1m
alterparam DZ1_BV = 71.25
reset
tran 50n 40m 0 50n uic
meas tran vosc_high avg v(vosc)   from=35m to=40m
meas tran vb_high   avg v(vboost) from=35m to=40m
meas tran idz_high  avg i(Vamm)   from=35m to=40m
meas tran izo_high  avg i(Vamm_o) from=35m to=40m
echo "--- high: V_OPA 24.6 V, Z_OSC1 15.75 V, I_OSC 0.1m, DZ1 71.25 V ---"
echo "  V_OSC = $&vosc_high V   I(Z_OSC1) = $&izo_high A   VBOOST = $&vb_high V   I(DZ1) = $&idz_high A"
* ── low corner ──
alterparam V_OPA_R = 22.2
alterparam VZO = 14.25
alterparam I_OSC = 0.75m
alterparam DZ1_BV = 78.75
reset
tran 50n 40m 0 50n uic
meas tran vosc_low avg v(vosc)   from=35m to=40m
meas tran vb_low   avg v(vboost) from=35m to=40m
meas tran idz_low  avg i(Vamm)   from=35m to=40m
meas tran izo_low  avg i(Vamm_o) from=35m to=40m
echo "--- low: V_OPA 22.2 V, Z_OSC1 14.25 V, I_OSC 0.75m, DZ1 78.75 V ---"
echo "  V_OSC = $&vosc_low V   I(Z_OSC1) = $&izo_low A   VBOOST = $&vb_low V   I(DZ1) = $&idz_low A"
* ── nom corner ──
alterparam V_OPA_R = 23.4
alterparam VZO = 15
alterparam I_OSC = 0.22m
alterparam DZ1_BV = 75
reset
tran 50n 40m 0 50n uic
meas tran vosc_nom avg v(vosc)   from=35m to=40m
meas tran vb_nom   avg v(vboost) from=35m to=40m
meas tran idz_nom  avg i(Vamm)   from=35m to=40m
meas tran izo_nom  avg i(Vamm_o) from=35m to=40m
echo "--- nom: V_OPA 23.4 V, Z_OSC1 15 V, I_OSC 0.22m, DZ1 75 V ---"
echo "  V_OSC = $&vosc_nom V   I(Z_OSC1) = $&izo_nom A   VBOOST = $&vb_nom V   I(DZ1) = $&idz_nom A"
* ── checks ── (each corner's measurements live in its own plot: tran1 high, tran2 low, tran3 nom)
* DZ1 may start to conduct in the high corner (0.11 mA simulated with DZ1 at -5%). That is harmless as long as
* Z_OSC1 keeps its current, so the checks are on V_OSC, not on DZ1 staying off.
if tran1.izo_high < 100u
  echo "FAIL pump_real_vosc: high corner I(Z_OSC1) = $&tran1.izo_high A (min 100 uA: DZ1's current must not starve V_OSC)"
else
  echo "PASS pump_real_vosc: high corner I(Z_OSC1) = $&tran1.izo_high A"
end
if tran1.vosc_high > 17
  echo "FAIL pump_real_vosc: high corner V_OSC = $&tran1.vosc_high V (max 17 V: ICM7556 18 V absolute)"
else
  echo "PASS pump_real_vosc: high corner V_OSC = $&tran1.vosc_high V"
end
if tran1.vb_high > 74
  echo "FAIL pump_real_vosc: high corner VBOOST = $&tran1.vb_high V (max 74 V)"
else
  echo "PASS pump_real_vosc: high corner VBOOST = $&tran1.vb_high V"
end
if tran2.izo_low < 100u
  echo "FAIL pump_real_vosc: low corner I(Z_OSC1) = $&tran2.izo_low A (min 100 uA, twice its 50 uA test current)"
else
  echo "PASS pump_real_vosc: low corner I(Z_OSC1) = $&tran2.izo_low A"
end
if tran2.vosc_low < 14.0
  echo "FAIL pump_real_vosc: low corner V_OSC = $&tran2.vosc_low V (min 14.0 V)"
else
  echo "PASS pump_real_vosc: low corner V_OSC = $&tran2.vosc_low V"
end
.endc

.end
