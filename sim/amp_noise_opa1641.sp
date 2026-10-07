* OPA1641 Mic Preamp — Noise Analysis
* Behavioral op-amp noise model for OPA1641:
*   Voltage noise: 2.5 nV/rtHz (OPA1641 datasheet)
*   Current noise: ~0.8 fA/rtHz (JFET input, negligible vs resistor noise)
*   GBW: 11 MHz (behavioral single-pole at 110Hz -> GBW=11MHz with gain 100k)
* Input network: R_GBIAS=100MΩ and R_BIAS1=100MΩ both contribute; they
*   dominate the noise floor below a few kHz. R_BIAS1 returns to V_MID, which
*   is AC ground, so it is not bootstrapped (#101).
* ---------------------------------------------------------------------------
.title OPA1641 Mic Noise Analysis

.options TEMP=27
.include params.inc
.include models/passives.lib

* ---------------------------------------------------------------------------
* POWER
* ---------------------------------------------------------------------------
V48   N48_SRC  0  DC 48
R1    N48_SRC  NET_48V  {R_PH_TAP}
R2    N48_SRC  NET_48V  {R_PH_TAP}
Vreg  NET_24V  0  DC 24
R5    NET_24V  NET_VBIAS  470k
R6    NET_VBIAS  0  470k
C3    NET_VBIAS  0  10u  IC=12

* ---------------------------------------------------------------------------
* CAPSULE MODEL FOR NOISE
* Signal source = 0 (measuring noise, not signal)
* ---------------------------------------------------------------------------
Vcap  CAP_HOT  CAP_BOT  AC 0  DC 0
Cc    CAP_BOT  0  {Cc}
Rconn CAP_HOT  CAP_FP  1

* High-Z bias network
* R_GBIAS = 100MΩ (single resistor) to HV rail (AC ground, decoupled)
* C8 = 1nF couples CAP_FP to VPLUS
* R_BIAS1 = 100MΩ from VPLUS to V_MID (AC ground). Earlier revisions omitted
* C8 and R_BIAS1 as "bootstrapped", which left out half of the bias network's
* noise current and understated the noise below a few kHz by about 3 dB (#101).
R_GBIAS  NET_HV  CAP_FP  {R_GBIAS}
C8       CAP_FP  PIN3_NODE  {C8}
R_BIAS1  PIN3_NODE  NET_VBIAS  {R_BIAS1}
Vhv   NET_HV  0  DC 68

* ---------------------------------------------------------------------------
* BEHAVIORAL OPA1641 — voltage noise + input current noise sources
* Voltage noise: 2.5 nV/rtHz → Req = (2.5e-9)^2/(4kT) = 6.25e-18/1.656e-20 ≈ 377Ω
* Current noise: ~0.8 fA/rtHz at IN+ and IN- (negligible vs resistor noise)
* ---------------------------------------------------------------------------

* R_IN1 (680R, #96): series resistor into IN+; its Johnson noise adds here.
R_in  PIN3_NODE  PIN3_IN  {R_IN}
R_vn  PIN3_IN    PIN3_VN  {OPA_VN_REQ}

* Current noise at IN+ (0.8fA/rtHz modeled as 320GΩ shunt)
*   R_in_noise = 4kT / I_noise^2 = 4*1.38e-23*300 / (0.8e-15)^2 = 32e18 Ω
* This is impractically large for SPICE; IN+ current noise is negligible vs 1GΩ
* Current noise at IN- through R4/R7 creates a Johnson noise via (I_n * R4):
*   V_noise_in-minus = I_n * R_source_at_in- = 0.8e-15 * 2200 = 1.76e-12 V/rtHz (negligible)
* These are omitted for clarity - dominant noise sources are R_vn and R_1G

* Ideal differential VCVS open-loop
Ediff  VDIFF  0  PIN3_VN  PIN2_NODE  1

* Single-pole dominant at 110 Hz (GBW = 100k * 110 = 11 MHz for OPA1641)
R_gbw  VDIFF  VPOLE  1k
C_gbw  VPOLE  0  1.447u   ; f_pole = 1/(2π*1k*1.447µ) = 110 Hz

Eamp  NET_OPA_IDEAL  MIDPOINT_DC  VPOLE  0  {OPA_OL_GAIN}
Vmid  MIDPOINT_DC  0  DC 12
R_oout  NET_OPA_IDEAL  NET_OPA_OUT  50

* Feedback and bias resistors (they also contribute Johnson noise)
R4    NET_VBIAS  PIN2_NODE  {R3}
R7    NET_OPA_OUT  PIN2_NODE  {R6_hi_gain}

* ---------------------------------------------------------------------------
* OUTPUT PATH
* ---------------------------------------------------------------------------
R8    NET_OPA_OUT  OPA_OUT_R8  100
C6    OPA_OUT_R8  XFMR_PRI_IN  {C_DC}
X_XFMR  XFMR_PRI_IN  0  XLR_P2  XLR_P3  NTE10_3
R_load   XLR_P2  XLR_P3  600
R_cm1  XLR_P2  0  10Meg
R_cm2  XLR_P3  0  10Meg
Ediff_out  XLR_DIFF  0  XLR_P2  XLR_P3  1
C5    NET_24V  0  10u  IC=24

* ---------------------------------------------------------------------------
* NOISE ANALYSIS: input-referred noise at Vcap (capsule)
* inoise_spectrum gives the equivalent input noise density (V/rtHz at capsule input)
* ---------------------------------------------------------------------------
.noise V(XLR_DIFF) Vcap dec 50 10 20k

.control
run
setplot noise1
print inoise_spectrum onoise_spectrum
* Pass/fail for inoise checked by check_noise.py in CI (meas noise unsupported here).
.endc

.end
