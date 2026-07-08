* OPA1641 Mic Preamp — AC Frequency Response
* Behavioral op-amp: gain 100k open-loop, single pole at 110Hz (GBW~11MHz)
* For audio band (10Hz-200kHz) closed-loop bandwidth = GBW/60 ~183kHz, well above audio
* Input network: R_GBIAS=94MΩ (47M+47M in series) to AC-ground HV rail
* Output DC block: C_DC=4.7µF (C_DC in PCB)
* ---------------------------------------------------------------------------
.title OPA1641 Mic AC Frequency Response

.options TEMP=27
.include models/passives.lib

* ---------------------------------------------------------------------------
* POWER (DC bias for proper op-amp operating point)
* ---------------------------------------------------------------------------
V48   N48_SRC  0  DC 48
R1    N48_SRC  NET_48V  6.81k
R2    N48_SRC  NET_48V  6.81k
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
Cc    CAP_BOT  0         55p

* ---------------------------------------------------------------------------
* HIGH-Z INPUT NODE (Pin3)
* R_GBIAS: 94MΩ (R_GBIAS1 + R_GBIAS2, 47M+47M) to HV rail (AC ground, decoupled)
* R_BIAS1: 100MΩ bootstrapped (VPLUS = output-following) -> AC-invisible, omitted
* ---------------------------------------------------------------------------
R_GBIAS  0  PIN3_NODE  94Meg

Rconn  CAP_HOT  PIN3_NODE  1   ; capsule hot wire to Pin3

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
Eamp  NET_OPA_IDEAL  MIDPOINT_DC  VPOLE  0  100k
Vmid  MIDPOINT_DC  0  DC 12    ; DC operating point for output

* Output resistor (OPA1641 output impedance ~50Ω)
R_oout  NET_OPA_IDEAL  NET_OPA_OUT  50

* Feedback: output to IN-
R4    NET_VBIAS  PIN2_NODE  2.2k     ; R3 in schematic: gain resistor, keep small for low noise
R7    NET_OPA_OUT  PIN2_NODE  5.6k   ; R6 in schematic: feedback, changed 130k→5.6k for -38 dBV/Pa target

* ---------------------------------------------------------------------------
* OUTPUT: R7 (series protection) + C_DC (DC block, 4.7µF) + NTE10/3 Transformer
* ---------------------------------------------------------------------------
R8    NET_OPA_OUT  OPA_OUT_R8  100
C6    OPA_OUT_R8  XFMR_PRI_IN  4.7u

* NTE10/3 transformer (reversed: red-blue as primary, white-yellow as secondary)
* Load: 600Ω typical XLR/preamp input (differential, so 600Ω across HOT/COLD)
X_XFMR  XFMR_PRI_IN  0  XLR_P2  XLR_P3  NTE10_3
R_load  XLR_P2  XLR_P3  600

* Common-mode bleed — prevents floating secondary node in SPICE
* 10MΩ >> 600Ω load, negligible effect on signal
R_cm1  XLR_P2  0  10Meg
R_cm2  XLR_P3  0  10Meg

* Differential output node (XLR_P2 – XLR_P3)
Ediff_out  XLR_DIFF  0  XLR_P2  XLR_P3  1

* ---------------------------------------------------------------------------
* ANALYSIS: AC sweep 10Hz to 200kHz
* ---------------------------------------------------------------------------
.ac dec 50 10 200k

.print ac db(V(XLR_DIFF)) db(V(NET_OPA_OUT)) db(V(XLR_P2)) db(V(XLR_P3))

.end
