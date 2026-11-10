* Amplifier DC operating point against input error (#123)
* ────────────────────────────────────────────────────────────────────────────
* The op-amp holds VINV at VPLUS + e, where e is the DC error at the input:
* the op-amp's offset, plus (bias current + board leakage into VPLUS) times
* R_BIAS1 (200 MΩ). 100 pA of leakage is already 20 mV.
*
* Up to v3.6, R3 returned straight to V_MID. V_MID is the R4/R5 divider, which
* is R4 || R5 = 235 kΩ at DC, so e pushed a current e / R3 into it and moved
* V_MID, and with it VPLUS, VINV and SIG_OUT, by 235k / 2.2k = 107 times e.
* 0.5 nA of leakage put SIG_OUT on the rail. A meter on V_MID did the same in
* the other direction, which is why V_MID and SIG_OUT read differently.
*
* C_G1 in series with R3 takes the DC out of that path: SIG_OUT moves by e and
* V_MID does not move. This deck solves the old and the new circuit side by
* side and checks the new one.
*
* Cases:
*   OLD   R3 straight to V_MID (C_G1 shorted)
*   NEW   C_G1, insulation resistance 10 GΩ
*   IR    C_G1 at the lowest insulation resistance a 10 µF X5R part may have
*         (50 Ω·F, so 5 MΩ): some DC returns through it, the gain is 1.05
*   H_*   the hi-gain variant (R6 = 47k)
*
* Not modelled: R_PRES1 + C_PRES1 (DNP by default; C_PRES1 blocks DC anyway).
*
* Checks (FAIL prefix triggers the CI gate in verify.yml):
*   - DC: SIG_OUT moves by no more than 1.2 times e, with 1 nA of leakage.
*   - Below the audio band an input error is never amplified by more than the
*     in-band gain (the old circuit: 41 dB at 1 mHz against 11 dB in band).
*   - C_G1 costs less than 1 dB at 20 Hz (corner with R3: 7.2 Hz).
* ────────────────────────────────────────────────────────────────────────────
.title Amplifier DC operating point against input error

.options TEMP=27
.include params.inc

* ── One amplifier: V_MID divider, input network, op-amp, gain network ───────
*   OUT   SIG_OUT
*   ERR   input error in volts, in series with IN+ (0 at DC; AC source for the sweep)
*   SIG   capsule signal in volts, in series with Cc
*   ILEAK leakage current into VPLUS; RCG the resistance across C_G1
.subckt AMP OUT ERR SIG params: ILEAK=0 RCG=10G R6v=5.6k
V_OPA   VOPA   0      DC {V_OPA}
R4      VOPA   MID    {R_MID}
R5      MID    0      {R_MID}
C45     MID    0      {C_MID}

* Polarisation and input network. The capsule's backplate is on V_MID.
V_HV    HV     0      DC {V_HV_clamp}
R_GBIAS HV     CAPFP  {R_GBIAS}
E_sig   CAPFP  CX     SIG 0 1
Cc      CX     MID    {Cc}
C8      CAPFP  VPLUS  {C8}
R_BIAS1 VPLUS  MID    {R_BIAS1}
I_leak  0      VPLUS  DC {ILEAK}
R_IN1   VPLUS  VPIN   {R_IN}
E_err   VPIN   VP     ERR 0 1

* Op-amp: gain 100k, pole at 110 Hz, output limited 0.5 V from each rail.
E_d     VD     0      VP VINV 1
R_gbw   VD     VPOLE  1k
C_gbw   VPOLE  0      1.447u
B_o     OUTI   0      V = max(0.5, min({V_OPA} - 0.5, {V_MID} + {OPA_OL_GAIN} * V(VPOLE)))
R_o     OUTI   OUT    50

* Gain network: V_MID - C_G1 - R3 - VINV - R6 - SIG_OUT
C_G1    MID    RG     {C_G}
R_cg    MID    RG     {RCG}
R3      RG     VINV   {R3}
R6      OUT    VINV   {R6v}
.ends AMP

V_err  ERR  0  DC 0  AC 0
V_sig  SIG  0  DC 0  AC 0

* DC: leakage 0, 100 pA, 1 nA
X_old_0  O_OLD_0  ERR SIG AMP ILEAK=0    RCG=1m
X_old_a  O_OLD_A  ERR SIG AMP ILEAK=100p RCG=1m
X_old_b  O_OLD_B  ERR SIG AMP ILEAK=1n   RCG=1m
X_new_0  O_NEW_0  ERR SIG AMP ILEAK=0
X_new_a  O_NEW_A  ERR SIG AMP ILEAK=100p
X_new_b  O_NEW_B  ERR SIG AMP ILEAK=1n
X_ir_b   O_IR_B   ERR SIG AMP ILEAK=1n   RCG=5Meg
* hi-gain variant
X_hold_0 H_OLD_0  ERR SIG AMP ILEAK=0    RCG=1m R6v={R6_hi_gain}
X_hnew_0 H_NEW_0  ERR SIG AMP ILEAK=0           R6v={R6_hi_gain}
X_hnew_b H_NEW_B  ERR SIG AMP ILEAK=1n          R6v={R6_hi_gain}

.control
* ── DC ──────────────────────────────────────────────────────────────────────
op
let e_a = 100p * 200Meg
let e_b = 1n * 200Meg
let old_a = v(o_old_a) - v(o_old_0)
let old_b = v(o_old_b) - v(o_old_0)
let new_a = v(o_new_a) - v(o_new_0)
let new_b = v(o_new_b) - v(o_new_0)
let ir_b  = v(o_ir_b)  - v(o_new_0)
let hi_b  = v(h_new_b) - v(h_new_0)
let dcg_new = new_b / e_b
let dcg_ir  = ir_b / e_b
let dcg_hi  = hi_b / e_b
let out_old_b = v(o_old_b)
echo ""
echo "========================================================"
echo "  amp_dc_offset: SIG_OUT shift for leakage into VPLUS"
echo "  (input error e = leakage x 200M: 20 mV at 100 pA, 200 mV at 1 nA)"
echo "                       100 pA          1 nA"
echo "  R3 to V_MID (old):   $&old_a V   $&old_b V  (SIG_OUT = $&out_old_b V: on the rail)"
echo "  with C_G1:           $&new_a V   $&new_b V"
echo "  C_G1 at 5 Mohm:                      $&ir_b V"
echo "  with C_G1, hi-gain:                  $&hi_b V"
echo "========================================================"
let dcg_limit = 1.2
if dcg_new > dcg_limit
  echo "FAIL amp_dc_offset: DC gain for an input error = $&dcg_new (limit 1.2)"
else
  echo "PASS amp_dc_offset: DC gain for an input error = $&dcg_new"
end
if dcg_ir > dcg_limit
  echo "FAIL amp_dc_offset: DC gain with C_G1 at 5 Mohm = $&dcg_ir (limit 1.2)"
else
  echo "PASS amp_dc_offset: DC gain with C_G1 at 5 Mohm = $&dcg_ir"
end
if dcg_hi > dcg_limit
  echo "FAIL amp_dc_offset: DC gain, hi-gain variant = $&dcg_hi (limit 1.2)"
else
  echo "PASS amp_dc_offset: DC gain, hi-gain variant = $&dcg_hi"
end

* ── Input error to SIG_OUT, 1 mHz to 2 kHz ──────────────────────────────────
alter v_err ac = 1
ac dec 20 1m 2k
meas ac err_old_1m find vdb(o_old_0) at=1m
meas ac err_new_1m find vdb(o_new_0) at=1m
meas ac err_new_max max vdb(o_new_0) from=1m to=1
meas ac err_band find vdb(o_new_0) at=1k
meas ac herr_new_max max vdb(h_new_0) from=1m to=1
meas ac herr_band find vdb(h_new_0) at=1k
echo ""
echo "  Input error to SIG_OUT: old $&err_old_1m dB at 1 mHz; with C_G1 $&err_new_1m dB at 1 mHz,"
echo "  at most $&err_new_max dB below 1 Hz; in band $&err_band dB"
if err_new_max > err_band
  echo "FAIL amp_dc_offset: an input error below 1 Hz is amplified by $&err_new_max dB, more than in band ($&err_band dB)"
else
  echo "PASS amp_dc_offset: an input error below 1 Hz is amplified by at most $&err_new_max dB (in band $&err_band dB)"
end
if herr_new_max > herr_band
  echo "FAIL amp_dc_offset: hi-gain, an input error below 1 Hz is amplified by $&herr_new_max dB, more than in band ($&herr_band dB)"
else
  echo "PASS amp_dc_offset: hi-gain, an input error below 1 Hz is amplified by at most $&herr_new_max dB (in band $&herr_band dB)"
end

* ── Capsule signal to SIG_OUT: what C_G1 costs at 20 Hz ─────────────────────
alter v_err ac = 0
alter v_sig ac = 1
ac dec 20 10 2k
meas ac s20_old find vdb(o_old_0) at=20
meas ac s20_new find vdb(o_new_0) at=20
meas ac h20_old find vdb(h_old_0) at=20
meas ac h20_new find vdb(h_new_0) at=20
let loss20 = s20_old - s20_new
let hloss20 = h20_old - h20_new
let loss_limit = 1.0
if loss20 > loss_limit
  echo "FAIL amp_dc_offset: C_G1 costs $&loss20 dB at 20 Hz (limit 1.0 dB)"
else
  echo "PASS amp_dc_offset: C_G1 costs $&loss20 dB at 20 Hz"
end
if hloss20 > loss_limit
  echo "FAIL amp_dc_offset: hi-gain, C_G1 costs $&hloss20 dB at 20 Hz (limit 1.0 dB)"
else
  echo "PASS amp_dc_offset: hi-gain, C_G1 costs $&hloss20 dB at 20 Hz"
end
.endc

.end
