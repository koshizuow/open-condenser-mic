* OPA1641 Mic Preamp — AC Frequency Response
* Behavioral op-amp: gain 100k open-loop, single pole at 110Hz (GBW~11MHz)
* For audio band (10Hz-200kHz) closed-loop bandwidth = GBW/60 ~183kHz, well above audio
* Input network: R_GBIAS1 (200MΩ) to AC-ground HV rail
* Output DC block: C_DC=4.7µF (C_DC in PCB)
* ---------------------------------------------------------------------------
.title OPA1641 Mic AC Frequency Response

.options TEMP=27
.include params.inc
.include models/passives.lib

* ---------------------------------------------------------------------------
* POWER (DC bias for proper op-amp operating point)
* ---------------------------------------------------------------------------
V48   N48_SRC  0  DC 48
R1    N48_SRC  NET_48V  {R_PH_TAP}
R2    N48_SRC  NET_48V  {R_PH_TAP}
Vreg  NET_24V  0  DC 24
R5    NET_24V  NET_VBIAS  470k
R6    NET_VBIAS  0  470k
C3    NET_VBIAS  0  10u  IC=12

* ---------------------------------------------------------------------------
* CAPSULE MODEL
* Vcap: 13.07mV/Pa at 1Pa reference (AC=1 means 1V; scale by 13.07m for 1Pa)
* In series with Cc=55pF (capsule self-capacitance)
* ---------------------------------------------------------------------------
Vcap  CAP_HOT  CAP_BOT  AC 13.07m   DC 0
Cc    CAP_BOT  0         {Cc}

* ---------------------------------------------------------------------------
* HIGH-Z INPUT NETWORK
* R_GBIAS1 (200MΩ): from CAP_FP to the HV rail (AC ground, decoupled)
* C8 (1nF): CAP_FP → VPLUS
* R_BIAS1 (200MΩ): VPLUS → V_MID. V_MID is AC ground (C4 + C5 = 20µF), so
* R_BIAS1 is NOT bootstrapped. At audio frequencies C8 is a short and the
* capsule sees R_GBIAS1 || R_BIAS1 = 100MΩ, giving a corner of ~29Hz with
* Cc = 55pF. Earlier revisions omitted C8 and R_BIAS1 on the assumption that
* R_BIAS1 was bootstrapped (#101). Both resistors were 100MΩ until #109.
* ---------------------------------------------------------------------------
Rconn    CAP_HOT  CAP_FP     1   ; capsule hot wire to CAP_FP
R_GBIAS  0        CAP_FP     {R_GBIAS}
C8       CAP_FP   PIN3_NODE  {C8}
R_BIAS1  PIN3_NODE  NET_VBIAS  {R_BIAS1}

* ---------------------------------------------------------------------------
* BEHAVIORAL OPA1641 (single-supply, V_MID=12V bias)
* Open-loop gain = 100k (100dB), dominant pole = 110Hz -> GBW = 11MHz
* Single pole modeled as: ideal VCVS * 1st-order lowpass
* ---------------------------------------------------------------------------
* Input differencing:
Ediff  VDIFF  0  PIN3_NODE  PIN2_NODE  1  ; VDIFF = V(in+) - V(in-)

* First-order lowpass (dominant pole at 110Hz -> GBW = 100k * 110Hz = 11MHz)
R_gbw  VDIFF  VPOLE  1k
C_gbw  VPOLE  0  1.447u   ; f_pole = 1/(2π*1k*1.447µ) ≈ 110Hz

* Gain stage: 100k (to represent 100dB open-loop gain)
* Output centered on VBIAS=12V (single supply midpoint)
Eamp  NET_OPA_IDEAL  MIDPOINT_DC  VPOLE  0  {OPA_OL_GAIN}
Vmid  MIDPOINT_DC  0  DC 12    ; DC operating point for output

* Output resistor (OPA1641 output impedance ~50Ω)
R_oout  NET_OPA_IDEAL  NET_OPA_OUT  50

* Feedback: output to IN-
R4    NET_VBIAS  PIN2_NODE  {R3}          ; R3 in schematic: gain resistor
R7    NET_OPA_OUT  PIN2_NODE  {R6_default} ; R6 in schematic: default flat/hi-SPL variant (5.6k)

* ---------------------------------------------------------------------------
* OUTPUT: R7 (series protection) + C_DC (DC block, 4.7µF) + NTE10/3 Transformer
* ---------------------------------------------------------------------------
R8    NET_OPA_OUT  OPA_OUT_R8  100
C6    OPA_OUT_R8  XFMR_PRI_IN  {C_DC}

* NTE10/3 transformer (reversed: red-blue as primary, white-yellow as secondary)
X_XFMR  XFMR_PRI_IN  0  XLR_P2  XLR_P3  NTE10_3

* RFI filter: 100Ω series + 100pF C0G shunt on each XLR leg (fc ~16 MHz)
* Creates -2.5 dB drop at 600Ω load; negligible at typical 2k+ preamp input
R_RFI1  XLR_P2  XLR_HOT_F  100
R_RFI2  XLR_P3  XLR_COLD_F  100
C_RFI1  XLR_HOT_F  0  100p
C_RFI2  XLR_COLD_F  0  100p

* Load: 600Ω typical XLR/preamp input (differential, so 600Ω across HOT/COLD)
R_load  XLR_HOT_F  XLR_COLD_F  600

* Common-mode bleed — prevents floating secondary node in SPICE
* 10MΩ >> 600Ω load, negligible effect on signal
R_cm1  XLR_HOT_F  0  10Meg
R_cm2  XLR_COLD_F  0  10Meg

* Differential output node (XLR_HOT_F – XLR_COLD_F)
Ediff_out  XLR_DIFF  0  XLR_HOT_F  XLR_COLD_F  1

* ---------------------------------------------------------------------------
* ANALYSIS: AC sweep 10Hz to 200kHz
* ---------------------------------------------------------------------------
.ac dec 50 10 200k

.print ac db(V(XLR_DIFF)) db(V(NET_OPA_OUT)) db(V(XLR_P2)) db(V(XLR_P3))

.control
run
* Write differential output AC data for plot_all.py
let xlr_db = db(v(xlr_diff))
wrdata _ac.dat xlr_db

* ── Passband flatness measurements ─────────────────────────────────────────
* Relative gains: all measurements against 1kHz mid-band reference.
* LF note: NTE10/3 primary (0.5H, Rp=521Ω) + C_DC(4.7µF) form a 2nd-order HPF
* with ω₀≈104Hz, Q≈0.49 → ~15dB drop at 100Hz in this model. That depends on
* Lp=0.5H, an unverified estimate (#99, see passives.lib), so it is not a
* confirmed property of the hardware. Check at 500Hz instead (~1.1dB drop
* including the ~29Hz input corner), where the model is less sensitive to Lp.
meas ac G_1K   find v(xlr_diff) at=1000
meas ac G_500  find v(xlr_diff) at=500
meas ac G_10K  find v(xlr_diff) at=10000
let gain_1k  = 20*log10(abs(G_1K))
let gain_500 = 20*log10(abs(G_500))
let gain_10k = 20*log10(abs(G_10K))
let drop_500 = gain_1k - gain_500
let drop_10k = gain_1k - gain_10k

echo ""
echo "========================================================"
echo "  amp_ac: passband flatness (normalized to 1kHz)"
echo "  Gain at   500Hz: $&gain_500 dBV  (drop $&drop_500 dB)"
echo "  Gain at  1kHz:   $&gain_1k dBV  (reference)"
echo "  Gain at 10kHz:  $&gain_10k dBV  (drop $&drop_10k dB)"
echo "========================================================"

* ── Sensitivity assertion (#111) ───────────────────────────────────────────
* Vcap is 13.07mV (1 Pa), so the 1kHz output in dBV is the sensitivity in
* dBV/Pa into this deck's 600Ω load: expected -40.2 (default gain). The README
* quotes -38 into 1.5kΩ, which is the same result at a lighter load.
let sens_lo = -41.5
let sens_hi = -38.5
if gain_1k < sens_lo
  echo "FAIL amp_ac: sensitivity = $&gain_1k dBV/Pa into 600R (min -41.5)"
else
  if gain_1k > sens_hi
    echo "FAIL amp_ac: sensitivity = $&gain_1k dBV/Pa into 600R (max -38.5)"
  else
    echo "PASS amp_ac: sensitivity = $&gain_1k dBV/Pa into 600R"
  end
end

* ── Pass/fail assertions ────────────────────────────────────────────────────
* 500Hz limit 3.0dB: expected ~0.4dB (2.6dB margin); catches C_DC/transformer changes.
* 10kHz limit 1.5dB: catches HF rolloff regressions from transformer or output cap.
let flat_lo_limit = 3.0
let flat_hi_limit = 1.5
if drop_500 > flat_lo_limit
  echo "FAIL amp_ac: gain drop at 500Hz = $&drop_500 dB (limit 3.0 dB)"
else
  echo "PASS amp_ac: gain flat at 500Hz ($&drop_500 dB from 1kHz)"
end
if drop_10k > flat_hi_limit
  echo "FAIL amp_ac: gain drop at 10kHz = $&drop_10k dB (limit 1.5 dB)"
else
  echo "PASS amp_ac: gain flat at 10kHz ($&drop_10k dB from 1kHz)"
end
.endc

.end
