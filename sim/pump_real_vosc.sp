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
*   - The oscillator becomes an ICM7555 (CMOS 555, U4, SOIC-8; 60 uA typ /
*     300 uA max at 15 V, no crowbar current) with R_OSC1 and C10 as its
*     timing parts. U3 (CD40106B) stays as the two inverters that make CLKA
*     and CLKB from its square wave; with a clean square wave at its inputs it
*     no longer sits mid-rail. I_OSC covers the 555, U3 and the pump drive:
*     0.42 mA typical, 0.69 mA max in clock_icm7555.sp; 0.75 mA is used as the
*     worst case and 0.1 mA as the least (the high corner).
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
*   nom:  V_OPA 23.4 V, all nominal, I_OSC 0.42 mA.
* Temperature corners, -20 and +60 C (ambient in a case; the zener figures are
* typical temperature coefficients, all positive): Z_OSC1 15 V +9..+13 mV/C
* (MMSZ47xx curve about +10), Z_REG1 24 V (BZT52C24) +18..+25 mV/C, DZ1 75 V
* about +75 mV/C, Q1's Vbe -2 mV/C (V_OPA follows Z_REG1 less Vbe). The diodes'
* own temperature comes from `option temp` (set after each reset, which clears
* it), with the BAT54 given a Schottky EG. Each corner takes the coefficients
* that are harshest for what it checks:
*   high-cold: DZ1 drops most, VBOOST least: does DZ1 starve Z_OSC1.
*   low-cold:  everything at its lowest: how low VBOOST, does Z_OSC1 keep a current.
*              I_OSC 0.85 mA: the ICM7555's 300 uA maximum is given at 25 C only, and
*              its supply current curve is about 30 % higher at -20 C (0.69 + 0.09).
*   high-hot:  everything at its highest: V_OSC under the ICM7555's 18 V, VBOOST.
*   low-hot:   the low corner warm, for the record.
* Each corner is a 40 ms transient (about 5 s).
* ────────────────────────────────────────────────────────────────────────────
.title Dickson pump with real V_OSC supply

.include params.inc

.param DZ1_BV  = 75      ; DZ1 actual breakdown (75 V +-5%: 71.25 / 75 / 78.75)
.param V_OPA_R = 23.4    ; V_OPA as delivered by the emitter follower
.param VZO     = 15      ; Z_OSC1 actual voltage at 50 uA (14.25 / 15 / 15.75)
.param I_OSC   = 0.42m   ; clock supply current from V_OSC (0.1m / 0.42m / 0.75m)
.param R_DRV   = 300     ; CD40106B output resistance at 15 V (estimate)

.model BAT  D  (IS=1e-6 N=1.05 BV=100 RS=3 EG=0.69 XTI=2)   ; Schottky barrier: leakage x19 at 60 C, not the silicon default x96
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
* A few pF on the switch-driven clock nodes so that they are never without capacitance: ngspice 44.2 (CI, KLU)
* aborted the high-cold run with "Timestep too small" at clka without them. The real 50 pF line load is already in
* I_OSC (clock_icm7555.sp charges it from U3's supply), so only 5 pF here (about 15 uA more, well inside the margin).
C_clka CLKA 0 5p
C_clkb CLKB 0 5p

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
alterparam I_OSC = 0.42m
alterparam DZ1_BV = 75
reset
tran 50n 40m 0 50n uic
meas tran vosc_nom avg v(vosc)   from=35m to=40m
meas tran vb_nom   avg v(vboost) from=35m to=40m
meas tran idz_nom  avg i(Vamm)   from=35m to=40m
meas tran izo_nom  avg i(Vamm_o) from=35m to=40m
echo "--- nom: V_OPA 23.4 V, Z_OSC1 15 V, I_OSC 0.42m, DZ1 75 V ---"
echo "  V_OSC = $&vosc_nom V   I(Z_OSC1) = $&izo_nom A   VBOOST = $&vb_nom V   I(DZ1) = $&idz_nom A"
* ── temperature corners (tran4 high-cold, tran5 low-cold, tran6 high-hot, tran7 low-hot) ──
* high-cold, -20 C: V_OPA 24.6 - 45*0.018 - 0.09, Z_OSC1 15.75 - 45*0.009, DZ1 71.25 - 45*0.075
alterparam V_OPA_R = 23.70
alterparam VZO = 15.345
alterparam I_OSC = 0.1m
alterparam DZ1_BV = 67.875
reset
option temp=-20
tran 50n 40m 0 50n uic
meas tran vosc_hc avg v(vosc)   from=35m to=40m
meas tran vb_hc   avg v(vboost) from=35m to=40m
meas tran idz_hc  avg i(Vamm)   from=35m to=40m
meas tran izo_hc  avg i(Vamm_o) from=35m to=40m
echo "--- high-cold -20 C: V_OPA 23.70 V, Z_OSC1 15.35 V, I_OSC 0.1m, DZ1 67.88 V ---"
echo "  V_OSC = $&vosc_hc V   I(Z_OSC1) = $&izo_hc A   VBOOST = $&vb_hc V   I(DZ1) = $&idz_hc A"
* low-cold, -20 C: V_OPA 22.2 - 45*0.025 - 0.09, Z_OSC1 14.25 - 45*0.013, DZ1 78.75 - 45*0.075
alterparam V_OPA_R = 20.985
alterparam VZO = 13.665
alterparam I_OSC = 0.85m
alterparam DZ1_BV = 75.375
reset
option temp=-20
tran 50n 40m 0 50n uic
meas tran vosc_lc avg v(vosc)   from=35m to=40m
meas tran vb_lc   avg v(vboost) from=35m to=40m
meas tran idz_lc  avg i(Vamm)   from=35m to=40m
meas tran izo_lc  avg i(Vamm_o) from=35m to=40m
echo "--- low-cold -20 C: V_OPA 20.99 V, Z_OSC1 13.67 V, I_OSC 0.85m, DZ1 75.38 V ---"
echo "  V_OSC = $&vosc_lc V   I(Z_OSC1) = $&izo_lc A   VBOOST = $&vb_lc V   I(DZ1) = $&idz_lc A"
* high-hot, +60 C: V_OPA 24.6 + 35*0.025 + 0.07, Z_OSC1 15.75 + 35*0.013, DZ1 71.25 + 35*0.075
alterparam V_OPA_R = 25.545
alterparam VZO = 16.205
alterparam I_OSC = 0.1m
alterparam DZ1_BV = 73.875
reset
option temp=60
tran 50n 40m 0 50n uic
meas tran vosc_hh avg v(vosc)   from=35m to=40m
meas tran vb_hh   avg v(vboost) from=35m to=40m
meas tran idz_hh  avg i(Vamm)   from=35m to=40m
meas tran izo_hh  avg i(Vamm_o) from=35m to=40m
echo "--- high-hot +60 C: V_OPA 25.55 V, Z_OSC1 16.21 V, I_OSC 0.1m, DZ1 73.88 V ---"
echo "  V_OSC = $&vosc_hh V   I(Z_OSC1) = $&izo_hh A   VBOOST = $&vb_hh V   I(DZ1) = $&idz_hh A"
* low-hot, +60 C: V_OPA 22.2 + 35*0.018 + 0.07, Z_OSC1 14.25 + 35*0.009, DZ1 78.75 + 35*0.075
alterparam V_OPA_R = 22.90
alterparam VZO = 14.565
alterparam I_OSC = 0.75m
alterparam DZ1_BV = 81.375
reset
option temp=60
tran 50n 40m 0 50n uic
meas tran vosc_lh avg v(vosc)   from=35m to=40m
meas tran vb_lh   avg v(vboost) from=35m to=40m
meas tran idz_lh  avg i(Vamm)   from=35m to=40m
meas tran izo_lh  avg i(Vamm_o) from=35m to=40m
echo "--- low-hot +60 C: V_OPA 22.90 V, Z_OSC1 14.57 V, I_OSC 0.75m, DZ1 81.38 V ---"
echo "  V_OSC = $&vosc_lh V   I(Z_OSC1) = $&izo_lh A   VBOOST = $&vb_lh V   I(DZ1) = $&idz_lh A"
option temp=27
* ── checks ── (each corner's measurements live in its own plot: tran1 high, tran2 low, tran3 nom)
* DZ1 may start to conduct in the high corner (0.11 mA simulated with DZ1 at -5%). That is harmless as long as
* Z_OSC1 keeps its current, so the checks are on V_OSC, not on DZ1 staying off.
if tran1.izo_high < 100u
  echo "FAIL pump_real_vosc: high corner I(Z_OSC1) = $&tran1.izo_high A (min 100 uA: DZ1's current must not starve V_OSC)"
else
  echo "PASS pump_real_vosc: high corner I(Z_OSC1) = $&tran1.izo_high A"
end
if tran1.vosc_high > 17
  echo "FAIL pump_real_vosc: high corner V_OSC = $&tran1.vosc_high V (max 17 V: ICM7555 18 V absolute)"
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
* Temperature corners: Z_OSC1 keeps 100 uA in all four; V_OSC under 17 V and VBOOST under 80 V (the HV parts are
* rated 100 V or more; DZ1 holds it at about 74 V when hot) at high-hot; VBOOST over 60 V at low-cold (polarisation
* about 0.9 dB below nominal, the v3.5 boards run at 63 V today).
if tran4.izo_hc < 100u
  echo "FAIL pump_real_vosc: high-cold I(Z_OSC1) = $&tran4.izo_hc A (min 100 uA)"
else
  echo "PASS pump_real_vosc: high-cold I(Z_OSC1) = $&tran4.izo_hc A"
end
if tran5.izo_lc < 100u
  echo "FAIL pump_real_vosc: low-cold I(Z_OSC1) = $&tran5.izo_lc A (min 100 uA)"
else
  echo "PASS pump_real_vosc: low-cold I(Z_OSC1) = $&tran5.izo_lc A"
end
if tran6.izo_hh < 100u
  echo "FAIL pump_real_vosc: high-hot I(Z_OSC1) = $&tran6.izo_hh A (min 100 uA)"
else
  echo "PASS pump_real_vosc: high-hot I(Z_OSC1) = $&tran6.izo_hh A"
end
if tran7.izo_lh < 100u
  echo "FAIL pump_real_vosc: low-hot I(Z_OSC1) = $&tran7.izo_lh A (min 100 uA)"
else
  echo "PASS pump_real_vosc: low-hot I(Z_OSC1) = $&tran7.izo_lh A"
end
if tran6.vosc_hh > 17
  echo "FAIL pump_real_vosc: high-hot V_OSC = $&tran6.vosc_hh V (max 17 V: ICM7555 18 V absolute)"
else
  echo "PASS pump_real_vosc: high-hot V_OSC = $&tran6.vosc_hh V"
end
if tran6.vb_hh > 80
  echo "FAIL pump_real_vosc: high-hot VBOOST = $&tran6.vb_hh V (max 80 V)"
else
  echo "PASS pump_real_vosc: high-hot VBOOST = $&tran6.vb_hh V"
end
if tran5.vb_lc < 60
  echo "FAIL pump_real_vosc: low-cold VBOOST = $&tran5.vb_lc V (min 60 V)"
else
  echo "PASS pump_real_vosc: low-cold VBOOST = $&tran5.vb_lc V"
end
.endc

.end
